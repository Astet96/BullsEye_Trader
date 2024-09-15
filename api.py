import requests
import json
from fastapi import FastAPI, Request
import os

app = FastAPI()

# Services
def redirect_services_api(service: str):
    @app.get(f"/{service}/"+"{path:path}")
    async def service_redirect(request: Request, path: str):
        return json.loads(requests.get(f"http://{service}/{path}").content.decode('utf-8'))
    return service_redirect

for service in os.environ.get("SERVICES").split(" "):  # pyright: ignore[reportOptionalMemberAccess]
    globals()[service] = redirect_services_api(service)


# API
@app.get("/")
async def root():
    return {"message": "Hello World"}
