import gspread
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from gspread.utils import ValueInputOption
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.enums.table import ColumnHeader


class StaticAccessTokenCredentials(Credentials):
    """Custom credentials wrapper that prevents auto-refresh routines when using temporary NextAuth access tokens."""

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def refresh(self, request: Request) -> None:
        """Override refresh to do nothing, preventing RefreshError exceptions."""
        pass


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


class GoogleSheetsStorage:
    """Handles interactions with Google Sheets using temporary user OAuth access tokens."""

    client: gspread.Client
    sheet: gspread.Worksheet

    def __init__(
        self,
        access_token: str | SecretStr,
        spreadsheet_id: str | None = None,
        sheet_name: str = "ADs_list",
    ) -> None:
        """Initialize Google Sheets client using validated Pydantic settings."""
        token_secret = (
            access_token
            if isinstance(access_token, SecretStr)
            else SecretStr(access_token)
        )
        config = GoogleSheetsStorageConfig(
            access_token=token_secret,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
        )

        raw_token = config.access_token.get_secret_value().strip()
        if not raw_token:
            raise ValueError("Google OAuth access_token cannot be empty.")

        # Wrap token in non-refreshable credentials subclass
        creds = StaticAccessTokenCredentials(raw_token)
        self.client = gspread.authorize(creds)

        # Open sheet by explicit Key (ID) or fallback to Title search / creation
        try:
            if config.spreadsheet_id:
                print(f"[STORAGE] Opening sheet by ID: {config.spreadsheet_id}")
                self.sheet = self.client.open_by_key(config.spreadsheet_id).sheet1
            else:
                print(f"[STORAGE] Searching for sheet by Title: '{config.sheet_name}'")
                try:
                    self.sheet = self.client.open(config.sheet_name).sheet1
                except gspread.exceptions.SpreadsheetNotFound:
                    print(
                        f"[STORAGE] Sheet '{config.sheet_name}' not found. Creating a new document..."
                    )
                    sh = self.client.create(config.sheet_name)
                    self.sheet = sh.sheet1

            self._ensure_header_row()
            print("[STORAGE] Google Sheets connection initialized successfully.")

        except gspread.exceptions.APIError as api_err:
            status_code = getattr(
                getattr(api_err, "response", None), "status_code", "N/A"
            )
            error_text = getattr(
                getattr(api_err, "response", None), "text", str(api_err)
            )
            print(f"[ERROR] Google Sheets API Error ({status_code}): {error_text}")
            raise Exception(f"Google API call failed: {error_text}") from api_err
        except Exception as err:
            print(
                f"[ERROR] Failed to initialize GoogleSheetsStorage: {type(err).__name__} -> {err}"
            )
            raise

    def _ensure_header_row(self) -> None:
        """Initialize sheet header row if the target spreadsheet is completely empty."""
        try:
            headers: list[str] = [header.value for header in ColumnHeader]
            first_row: list[str] = self.sheet.row_values(1)
            if not first_row:
                self.sheet.append_row(headers)
        except Exception as err:
            print(f"[WARN] Could not verify or append header row: {err}")

    def load_existing_links(self) -> set[str]:
        """Loads all existing website_link URLs from column C to avoid duplicate scraping."""
        if not hasattr(self, "sheet") or self.sheet is None:
            return set()

        try:
            # Fetch column 3 values
            raw_links = self.sheet.col_values(3)

            if len(raw_links) <= 1:
                return set()

            # Skip header row (index 0) and filter out empty/None values
            existing_links: set[str] = {
                str(link).strip()
                for link in raw_links[1:]
                if link is not None and str(link).strip()
            }

            return existing_links

        except Exception as e:
            print(f"[WARN] Failed to load existing links from sheet: {e}")
            return set()

    def clear_and_replace_listings(self, listings: list) -> None:
        """Clears all existing rows (except headers) and writes the fresh set of listings."""
        if not hasattr(self, "sheet") or self.sheet is None:
            print("[WARN] Google Sheets storage not connected.")
            return

        try:
            # 1. Clear existing listing rows starting from row 2
            all_values = self.sheet.get_all_values()
            if len(all_values) > 1:
                self.sheet.batch_clear([f"A2:Z{len(all_values)}"])
                print("[STORAGE] Cleared old listings from Google Sheets.")

            # 2. Format fresh rows
            rows = []
            for listing in listings:
                if hasattr(listing, "to_sheet_row"):
                    rows.append(listing.to_sheet_row())
                elif isinstance(listing, dict):
                    rows.append(list(listing.values()))

            # 3. Write new dataset using the typed ValueInputOption enum
            if rows:
                self.sheet.append_rows(
                    rows, value_input_option=ValueInputOption.user_entered
                )
                print(f"[STORAGE] Replaced sheet with {len(rows)} fresh listings.")

        except Exception as e:
            print(f"[ERROR] Failed to replace listings in Google Sheets: {e}")
