import traceback

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.pipeline import run_pipeline
from src.services.streamestate_client import StreamEstateError

app = FastAPI()


class SearchPayload(BaseModel):
    locations: list[str]
    minPrice: float = 0.0
    maxPrice: float = 0.0
    minSpace: float = 0.0
    minRooms: int = 1
    minBedrooms: int = 1


@app.post("/api/search")
async def search_listings(
    payload: SearchPayload,
    authorization: str | None = Header(
        default=None
    ),  # Explicitly parses HTTP Authorization Header
):
    try:
        access_token = ""
        if authorization and authorization.startswith("Bearer "):
            access_token = authorization.split(" ")[1]

        run_pipeline(payload, access_token=access_token)
        return {
            "status": "success",
            "message": "Property search completed successfully.",
        }
    except StreamEstateError as api_err:
        raise HTTPException(status_code=402, detail=str(api_err))
    except Exception as err:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(err))
