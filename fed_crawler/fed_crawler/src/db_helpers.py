from __future__ import annotations

import psycopg2

from uuid import UUID
import hashlib
from datetime import datetime
from typing import Callable, Any, Optional
from psycopg2.extras import register_uuid  # pyright: ignore[reportUnknownVariableType]

register_uuid()


def db_unique_violation_handler(func: Callable[[Any, psycopg2.extensions.connection], None]) -> Callable[[Any, psycopg2.extensions.connection], None]:
    # decorator to handle DB unique condition when inserting data
    def handle_race_conditions(self: Any, db_backend: psycopg2.extensions.connection) -> None:
        try:
            func(self, db_backend)
        except psycopg2.errors.UniqueViolation:
            cursor = db_backend.cursor()
            cursor.execute("ROLLBACK")
            cursor.close()
    return handle_race_conditions

def db_foreign_key_violation_handler(func: Callable[[Any, psycopg2.extensions.connection], None]) -> Callable[[Any, psycopg2.extensions.connection, Optional[HouseMember]], None]:
    # decorator to handle DB FKey condition when inserting data
    def handle_race_conditions(self: Any, db_backend: psycopg2.extensions.connection, house_member: HouseMember) -> None:
        try:
            func(self, db_backend)
        except psycopg2.errors.ForeignKeyViolation:
            cursor = db_backend.cursor()
            cursor.execute("ROLLBACK")
            house_member.log_to_db(db_backend)
            func(self, db_backend)
            cursor.close()
    return handle_race_conditions  # pyright: ignore[reportReturnType]

# helper functions
def create_uuid_from_string(val: str) -> UUID:
    hex_string = hashlib.md5(val.encode("UTF-8")).hexdigest()
    return UUID(hex=hex_string)

def db_get_last_known_year(db_backend: psycopg2.extensions.connection) -> int:
    """
    Retreives the last known year for reports published at: disclosures-clerk.house.gov
    Value for 2008 is hard-coded in the database because it is the first reporting year
    """
    cursor = db_backend.cursor()
    cursor.execute("SELECT year_id FROM known_years ORDER BY known_years DESC LIMIT 1")
    rtrn_value: int = int(cursor.fetchone()[0])  # pyright: ignore[reportUnknownArgumentType,  reportOptionalSubscript]

    cursor.close()
    return rtrn_value

def db_validate_tables(db_backend: psycopg2.extensions.connection) -> bool:
    """
    Validates that the DB has the required tables and they aren't malformed
    """
    ...

def db_seed_db(db_backend: psycopg2.extensions.connection) -> None:
    """
    Seeds the DB by creating the relevant tables if they don't exist
    or are malformed
    """
    ...

# classes
class HouseMember():
    def __init__(self, last_name: str, first_name: str, parsed_doc_ids: list[str] | None = None) -> None:
        self.id: UUID = create_uuid_from_string(f"{last_name}_{first_name}")
        self.last_name: str = last_name
        self.first_name: str = first_name
        self.parsed_doc_ids: list[str] = parsed_doc_ids or []
        self.new_doc_ids: list[str] = []

    def enqueue_new_doc(self, doc_id: str) -> None:
        if doc_id in self.parsed_doc_ids or doc_id in self.new_doc_ids:
            return
        self.new_doc_ids.append(doc_id)

    def parse_doc(self, doc_id: str) -> None:
        if doc_id in self.new_doc_ids:
            self.new_doc_ids.remove(doc_id)
        if doc_id not in self.parsed_doc_ids:
            self.parsed_doc_ids.append(doc_id)

    def db_update_parsed_docs(self, db_backend: psycopg2.extensions.connection) -> None:
        cursor = db_backend.cursor()
        db_operation = f"UPDATE house_members SET parsed_doc_ids = %s WHERE id = %s"
        cursor.execute(db_operation, (self.parsed_doc_ids, self.id))
        cursor.close()

    @db_unique_violation_handler
    def log_to_db(self, db_backend: psycopg2.extensions.connection) -> None:
        cursor = db_backend.cursor()
        db_operation = f"""INSERT INTO house_members (
                id,
                last_name,
                first_name
            ) VALUES (
                %s,
                %s,
                %s
            )"""
        cursor.execute(db_operation, (self.id, self.last_name, self.first_name))
        cursor.close()


class KnownHouseMembers():
    def _seed_from_db(self, db_backend: psycopg2.extensions.connection) -> None:
        cursor = db_backend.cursor()
        cursor.execute("SELECT * FROM house_members")

        while house_member_tuple := cursor.fetchone():
            self.known_members[house_member_tuple[0]] = HouseMember(*house_member_tuple[1:])
        cursor.close()

    def __init__(self, db_backend: psycopg2.extensions.connection) -> None:
        self.known_members: dict[UUID, HouseMember] = {}
        self._seed_from_db(db_backend)

    def get(self, last_name: str, first_name: str) -> HouseMember | None:
        return self.known_members.get(create_uuid_from_string(f"{last_name}_{first_name}"))

    def add(self, house_member: HouseMember) -> None:
        if not self.get(house_member.last_name, house_member.first_name):
            self.known_members[create_uuid_from_string(f"{house_member.last_name}_{house_member.first_name}")] = house_member

class PTRreport():
    # TODO:
    # use Enums for transaction_type & amount
    def str_date_to_datetime(self, str_date: str) -> datetime:
        """
        Input: date in string format mm/dd/yyyy
        Returns: datetime instance
        """
        m, d, y = str_date.split('/')
        return datetime(day=int(d.lstrip('0')), month=int(m.lstrip('0')), year=int(y))

    def get_transaction_type_from_str(self, transaction_type: str) -> str:
        transaction_types = {
            "P": "P",
            "S": "S",
            "S (partial)": "PS",
            "E": "E",
        }
        return transaction_types.get(transaction_type) or ''

    def get_amount_band_from_amount_str(self, amount: str) -> str:
        amount_band = {
            "$1,001": "A",
            "$15,001": "B",
            "$50,001": "C",
            "$100,001": "D",
            "$250,001": "E",
            "$500,001": "F",
            "$1,000,001": "G",
            "$5,000,001": "H",
            "$25,000,001": "I",
            "Over": "J",
            "Spouse/DC": "K",
        }
        amount_band_limits: dict[int, str] = {
            1_001: "A",
            15_001: "B",
            50_001: "C",
            100_001: "D",
            250_001: "E",
            500_001: "F",
            1_000_001: "G",
            5_000_001: "H",
            25_000_001: "I",
        }
        if amount in amount_band:
            return amount_band[amount]
        else:
            new_amount: int = int(amount[1:].replace(',', '_').split('.')[0] or 0)
            int_amount_band = 1_001
            for int_amount_band in amount_band_limits:
                if new_amount < int_amount_band:
                    break
            return amount_band_limits[int_amount_band]


    def __init__(self, house_member_id: UUID, doc_id: str, asset: str, transaction_type: str, transaction_date: str, notification_date: str, amount: str, counter: int) -> None:
        self.id: str = f"{doc_id}_{counter}"
        self.house_member_id: UUID = house_member_id
        self.asset: str = asset
        self.transaction_type: str = self.get_transaction_type_from_str(transaction_type)
        self.transaction_date: datetime = self.str_date_to_datetime(transaction_date)
        self.notification_date: datetime = self.str_date_to_datetime(notification_date)
        self.amount: str = self.get_amount_band_from_amount_str(amount)

    @db_foreign_key_violation_handler  # pyright: ignore[ reportArgumentType]
    @db_unique_violation_handler
    def log_to_db(self, db_backend: psycopg2.extensions.connection, house_member: HouseMember|None=None) -> None:
        cursor = db_backend.cursor()
        db_operation = f"""INSERT INTO ptr (
                id,
                house_member_id,
                asset,
                transaction_type,
                transaction_date,
                notification_date,
                amount
            ) VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )"""
        cursor.execute(db_operation,
                       (self.id,
                        self.house_member_id,
                        self.asset,
                        self.transaction_type,
                        self.transaction_date,
                        self.notification_date,
                        self.amount,
                       )
        )
        cursor.close()
