from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
load_dotenv()

from routers import api

app = FastAPI(docs_url="/docs", openapi_url="/openapi.json")

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=True,   
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def helloworld():
    return {"Hello": "FastAPI is running :)"}

app.include_router(api.router)