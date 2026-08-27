from src.schemas.collaborators import AddCollaboratorPayload
from src.services.storage import GoogleSheetsStorage
from src.config import settings

import traceback
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.pipeline import run_pipeline
from src.services.streamestate_client import StreamEstateError

app = FastAPI()


class SearchPayload(BaseModel):
    locations: list[str] = ["Paris"]
    minPrice: float = 0
    maxPrice: float = 0
    minSpace: float = 0
    minRooms: int = 1
    minBedrooms: int = 1
    spreadsheet_id: str | None = None


@app.post("/api/search")
async def search(
    payload: SearchPayload,
    x_user_email: str | None = Header(None, alias="X-User-Email"),
):
    try:
        storage = run_pipeline(payload=payload, user_email=x_user_email or "")

        # Verify storage was successfully created before reading its spreadsheet ID
        if (
            not storage
            or not hasattr(storage, "spreadsheet")
            or not storage.spreadsheet
        ):
            raise HTTPException(
                status_code=500,
                detail="Google Sheets storage client failed to initialize during pipeline execution.",
            )

        return {
            "status": "success",
            "message": "Search pipeline executed and Google Sheets synced successfully.",
            "spreadsheet_id": storage.spreadsheet.id,
        }

    except StreamEstateError as se_err:
        print(f"[ERROR] Stream Estate API Error: {se_err}")
        raise HTTPException(
            status_code=502,
            detail=f"Stream Estate external API failed: {se_err}",
        )
    except HTTPException:
        raise
    except Exception as err:
        print(f"[ERROR] Pipeline execution failed: {err}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Search pipeline execution failed: {err}"
        )


@app.post("/api/collaborators/add")
async def add_collaborator(payload: AddCollaboratorPayload):
    # Open the user's specific spreadsheet by ID
    storage = GoogleSheetsStorage(
        master_template_id=settings.google_sheets_master_template_id,
        spreadsheet_id=payload.spreadsheet_id,
    )

    storage.add_collaborator_column(payload.collaborator_name)
    return {"success": True, "message": f"Added column for {payload.collaborator_name}"}
