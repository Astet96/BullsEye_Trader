import requests
import json
from fastapi import FastAPI, Request
import os

app = FastAPI()

# Services
@app.get("/fed_crawler/{path:path}")
async def fed_crawler(request: Request, path: str):
    return json.loads(requests.get(f"http://{os.environ.get('FED_CRAWLER')}:8081/{path}").content.decode('utf-8'))

@app.get("/yfin_scraper/{path:path}")
async def yfin_scraper(request: Request, path: str):
    return json.loads(requests.get(f"http://{os.environ.get('YFIN_SCRAPER')}:8082/{path}").content.decode('utf-8'))

# API
@app.get("/")
async def root():
    return {"message": "Hello World"}
