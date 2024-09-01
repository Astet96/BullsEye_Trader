from __future__ import annotations

import requests
import psycopg2


from multiprocessing import get_context

import re
import pdfplumber
from typing import Pattern, Generator
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .db_helpers import db_get_last_known_year, KnownHouseMembers, HouseMember, PTRreport


DIGITAL_PTR_DATASTREAM_REGEX: str = r"(?<=\\n)(.. |)(?P<asset>([^\[\\]+?))( | \[..\] )(?P<transaction_type>(?<= )(S ?\(partial\)|[PSE])(?= )) (?P<transaction_date>(\d{1,2}\/\d{1,2}\/\d{4})) (?P<notification_date>(\d{1,2}\/\d{1,2}\/\d{4})) (?P<amount>((\$?)[^- \\n]+))"
DIGITAL_PTR_ENTRY = re.compile(DIGITAL_PTR_DATASTREAM_REGEX)


def get_all_new_reporting_years(last_known_year: int) -> Generator[tuple[int, bytes], None, None]:
    while (yearly_reports_list_zip := requests.get(f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{last_known_year}FD.zip")).status_code == 200:
        yield last_known_year, yearly_reports_list_zip.content
        last_known_year += 1

async def scrape_ptr_reports():
    """
    Entry function for the fed_crawler module.
    This function controls and orchestrates the
    webcrawlers that will be used to retreive
    US House members' trading history from their filings
    at `disclosures-clerk`. Records processed by the ETL
    will be saved to the PostgreSQL backend provided
    """
    # need to have postgress container running
    db_backend = psycopg2.connect(
        database="fed_crawler_db",
        host="postgres",
        user="fed_crawler",  # use secrets
        password="pass",  # use secrets
        port="5433"  # update port mappings
    )

    last_known_year = db_get_last_known_year(db_backend)

    payload: Generator[tuple[int, bytes]] = get_all_new_reporting_years(last_known_year)

    await process_yearly_returns(payload)

    db_backend.commit()
    db_backend.close()

class PtrParser(object):
    def __init__(self, year: int) -> None:
        self.digital_ptr_entry: Pattern[str] = DIGITAL_PTR_ENTRY
        self.year: int = year

    def __call__(self, house_member: HouseMember) -> None:
        return self.parse_ptr_entries(house_member)

    def parse_ptr_entries(self, house_member: HouseMember) -> None:
        db_backend = psycopg2.connect(
            database="fed_crawler_db",
            host="postgres",
            user="fed_crawler",  # use secrets
            password="pass",  # use secrets
            port="5433"  # update port mappings
        )

        for new_report in house_member.new_doc_ids.copy():
            ptr_pdf_url = f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{self.year}/{new_report}.pdf"
            ptr_pdf_request = requests.get(ptr_pdf_url)

            # TODO: see if this is really required
            if ptr_pdf_request.status_code != 200:
                continue

            raw_ptr_string = r""
            with pdfplumber.open(BytesIO(ptr_pdf_request.content)) as pdf:
                for page in pdf.pages:
                    raw_ptr_string += repr(page.extract_text_simple())

            if raw_ptr_string:
                # this is a digital ptr
                self.process_digital_ptr(raw_ptr_string, house_member, new_report, db_backend)
                continue

            # this is an analog ptr
            self.process_analog_ptr()

        print(f"processing PTR entries for {house_member.first_name} {house_member.last_name}")

        house_member.db_update_parsed_docs(db_backend)
        db_backend.commit()
        db_backend.close()

        return

    def process_digital_ptr(self, raw_ptr_string: str, house_member: HouseMember, new_report: str, db_backend: psycopg2.extensions.connection) -> None:
        i = 0
        all_matches = self.digital_ptr_entry.finditer(raw_ptr_string)
        for match in all_matches:
            ptr_entry = PTRreport(
                *(
                    house_member.id,
                    new_report,
                    match.group("asset"),
                    match.group("transaction_type"),
                    match.group("transaction_date"),
                    match.group("notification_date"),
                    match.group("amount"),
                    i,
                )
            )
            ptr_entry.log_to_db(db_backend, house_member)
            i += 1
        house_member.parse_doc(new_report)
        return

    def process_analog_ptr(self):
        # TODO:
        # parse analog files
        pass

def yearly_returns_parser(year_to_parse: int, yearly_reports_zip: bytes) -> tuple[int, KnownHouseMembers]:

    print(f"parsing xml for {year_to_parse} returns")

    db_backend = psycopg2.connect(
        database="fed_crawler_db",
        host="postgres",
        user="fed_crawler",  # use secrets
        password="pass",  # use secrets
        port="5433"  # update port mappings
    )

    known_members = KnownHouseMembers(db_backend)
    with ZipFile(BytesIO(yearly_reports_zip)) as zf:
        with zf.open(f"{year_to_parse}FD.xml") as reports_xml:
            # create element tree object
            tree = ET.parse(reports_xml)

            # get root element
            root = tree.getroot()

            # Iterate over disclosures
            for disclosure in root:
                # PTR filing type in the xml is: FilingType = 'P'
                is_ptr = disclosure.find("FilingType")
                if is_ptr is not None:
                    # TODO: use enum here
                    is_ptr = is_ptr.text == "P"

                if is_ptr:
                    last_name: str = disclosure.find("Last").text  # pyright: ignore[ reportAssignmentType,  reportOptionalMemberAccess]
                    first_name: str = disclosure.find("First").text  # pyright: ignore[ reportAssignmentType,  reportOptionalMemberAccess]
                    doc_id: str = disclosure.find("DocID").text  # pyright: ignore[ reportAssignmentType,  reportOptionalMemberAccess]

                    if house_member := known_members.get(last_name, first_name):
                        # add report id to house member's reports list
                        house_member.enqueue_new_doc(doc_id)
                    else:
                        # new house member, add this house member to the registry
                        house_member = HouseMember(last_name, first_name)
                        house_member.log_to_db(db_backend)
                        known_members.add(house_member)
                        house_member.enqueue_new_doc(doc_id)

    db_backend.commit()
    db_backend.close()

    return year_to_parse, known_members


async def process_yearly_returns(payload: Generator[tuple[int, bytes], None, None]) -> None:
    multiprocessing_context = get_context("forkserver")
    # run a process for each reporting year
    with multiprocessing_context.Pool(processes=8) as pool:
        for year, known_members in pool.starmap_async(func=yearly_returns_parser ,iterable=payload, chunksize=1).get():
            parser = PtrParser(year)

            print(f"parsing pdfs for FY {year} for {len(known_members.known_members.keys())} House members")

            pool.map_async(parser, [house_member for _, house_member in known_members.known_members.items()], chunksize=len(known_members.known_members.items())//24 + 1).get()
