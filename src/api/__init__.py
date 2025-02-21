import logging
import os

from fastapi import FastAPI

# set up initial app components
APP_NAME = os.getenv("APP_NAME")
if not APP_NAME:
    raise ValueError("Must supply an 'APP_NAME' environment variable")

APP_VERSION = os.getenv("APP_VERSION")
if not APP_VERSION:
    raise ValueError("Must supply an 'APP_VERSION' environment variable")

# set up logging
log = logging.getLogger(f"{os.getenv('COMPANY_NAME')} {os.getenv('APP_NAME')}")
log.setLevel("DEBUG")
log.info(f"Initilizing application {os.getenv('APP_NAME')}")

OPENAPI_SERVER_URL = os.getenv("OPENAPI_SERVER_URL")
if not OPENAPI_SERVER_URL:
    log.info("OPENAPI_SERVER_URL defaulting to '/'")
    OPENAPI_SERVER_URL = "/"

OPENAPI_URL = f"{OPENAPI_SERVER_URL}openapi.json"
log.info(f"OPENAPI_URL set to {OPENAPI_URL}")

# app init
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    openapi_url=OPENAPI_URL,
)
