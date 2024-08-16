from fastapi import FastAPI
from fed_crawler import scrape_ptr_reports

app = FastAPI()


@app.get("/")
async def root():
    # test submodule integration
    await scrape_ptr_reports()
    return {"message": "Processed all available US House members' Periodic Transaction Reports"}
