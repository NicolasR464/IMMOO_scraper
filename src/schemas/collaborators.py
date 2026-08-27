from pydantic import BaseModel


class AddCollaboratorPayload(BaseModel):
    collaborator_name: str
    spreadsheet_id: str
