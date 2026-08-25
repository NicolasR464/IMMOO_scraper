from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, status

from src.cli import run_pipeline
from src.types.requests import ScrapeRequest
from src.utils import get_project_version
from src.utils.api_checker import verify_api_key

APP_VERSION = get_project_version()

app = FastAPI(title="IMMOO Scraper Service", version=APP_VERSION)

# Create router with /api prefix
api_router = APIRouter(prefix="/api")

# Dependency wrapper (extracts verified token string)
ApiKeyDep = Annotated[str, Depends(verify_api_key)]


def execute_pipeline(payload: ScrapeRequest):
    # Run pipeline with dynamic payload from client
    run_pipeline(payload)


@api_router.get("/health")
def health_check():
    return {"status": "online", "version": APP_VERSION}


@api_router.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(payload: ScrapeRequest, background_tasks: BackgroundTasks):
    # Pass the client payload directly to the background task
    background_tasks.add_task(execute_pipeline, payload)
    return {"success": True, "message": "Scraping pipeline queued successfully!"}


app.include_router(api_router)
