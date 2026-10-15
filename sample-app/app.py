"""Small deployment target monitored by DeployIQ."""
import os
from fastapi import FastAPI

app = FastAPI(title="DeployIQ Sample App", version="0.1.0")


@app.get("/")
def index():
    return {"service": "deployiq-sample", "version": os.getenv("APP_VERSION", "local")}


@app.get("/health")
def health():
    return {"status": "healthy"}
