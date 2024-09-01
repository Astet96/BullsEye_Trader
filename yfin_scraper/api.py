from fastapi import FastAPI
from yfin_scraper import *

app = FastAPI()


@app.get("/")
async def root():
    # test submodule integration
    # await foo()
    return {"message": "success!"}
