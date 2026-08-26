from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    streamestate_api_key: SecretStr
    gemini_api_key: SecretStr  # Add this field
    google_sheet_name: str = "ADs_list"
    google_sheets_master_template_id: str
    google_drive_staging_folder_id: str
    use_mock: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


class SearchPreferences(BaseModel):
    locations: list[str] = ["Paris"]
    min_price: int = 0
    max_price: int = 0
    min_space: int = 0
    min_rooms: int = 1
    min_bedrooms: int = 1


settings = Config()
