from pydantic import BaseModel, ConfigDict, Field, SecretStr


class GoogleSheetsStorageConfig(BaseModel):
    """Configuration model for GoogleSheetsStorage initialization parameters."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    access_token: SecretStr = Field(
        ..., description="The user's Google OAuth access token forwarded from NextAuth."
    )
    spreadsheet_id: str | None = Field(
        default=None,
        description="Optional direct Spreadsheet ID. If provided, bypasses Drive search.",
    )
    sheet_name: str = Field(
        default="ADs_list",
        description="Name of the sheet to open or create (defaults to 'ADs_list').",
    )
