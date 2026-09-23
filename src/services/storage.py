import json
import os
import time
from pathlib import Path

from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from gspread.utils import a1_range_to_grid_range
from gspread_formatting import (
    CellFormat,
    Color,
    NumberFormat,
    TextFormat,
    format_cell_range,
    set_column_width,
    set_row_height,
)
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.config import settings
from src.enums.table import ColumnHeader, StatusEnum

# Automatically resolves to the root folder of your project
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SERVICE_ACCOUNT_PATH = str(BASE_DIR / "service_account.json")
# Preferred over the file above: the credentials JSON passed directly as an
# env var (see scripts/fetch-secrets.sh), so no key file needs to exist on disk.
SERVICE_ACCOUNT_JSON_ENV_VAR = "GOOGLE_SERVICE_ACCOUNT_JSON"


class StaticAccessTokenCredentials(Credentials):
    """Custom credentials wrapper that prevents auto-refresh routines when using temporary NextAuth access tokens."""

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def refresh(self, request: Request) -> None:
        """Override refresh to do nothing, preventing RefreshError exceptions."""


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
    """Handles interactions with Google Sheets using backend Service Account.

    Clones a Master Template containing bound Apps Script protections when
    creating new sheets inside Shared Drives.
    """

    client: gspread.Client
    sheet: gspread.Worksheet
    spreadsheet: gspread.Spreadsheet

    def __init__(
        self,
        master_template_id: str,
        user_email: str | None = None,
        spreadsheet_id: str | None = None,
        sheet_name: str = "ADs_list",
        service_account_file: str = DEFAULT_SERVICE_ACCOUNT_PATH,
    ) -> None:
        """Initialize Google Sheets client using backend Service Account."""
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        # 1. Authenticate with Service Account — prefer the credentials JSON
        # passed directly via env var (no file ever touches disk); fall back
        # to a file path for environments that still mount one that way.
        service_account_json = os.environ.get(SERVICE_ACCOUNT_JSON_ENV_VAR)
        if service_account_json:
            info = json.loads(service_account_json)
            self.creds = service_account.Credentials.from_service_account_info(
                info, scopes=scopes
            )
        else:
            if not os.path.exists(service_account_file):
                raise FileNotFoundError(
                    f"Service account file '{service_account_file}' not found, "
                    f"and {SERVICE_ACCOUNT_JSON_ENV_VAR} is not set."
                )
            self.creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=scopes
            )
        self.client = gspread.authorize(self.creds)
        self.drive_service = build("drive", "v3", credentials=self.creds)

        try:
            # 2. Open existing sheet OR clone from Master Template
            if spreadsheet_id:
                print(f"[STORAGE] Opening existing sheet by ID: {spreadsheet_id}")
                self.spreadsheet = self.client.open_by_key(spreadsheet_id)
            else:
                if not master_template_id:
                    raise ValueError(
                        "master_template_id must be provided when spreadsheet_id is None."
                    )

                staging_folder_id = settings.google_drive_staging_folder_id
                print(f"[STORAGE] Staging Folder ID retrieved: '{staging_folder_id}'")

                copy_body: dict[str, str | list[str]] = {
                    "name": sheet_name,
                }
                if staging_folder_id:
                    copy_body["parents"] = [staging_folder_id]

                print(
                    f"[STORAGE] Copying Master Template (ID: {master_template_id}) to Shared Drive..."
                )
                copied_file = (
                    self.drive_service.files()  # type: ignore[attr-defined]
                    .copy(
                        fileId=master_template_id,
                        body=copy_body,
                        supportsAllDrives=True,
                    )
                    .execute()
                )

                new_id = copied_file["id"]
                print(
                    f"[STORAGE] Successfully created sheet from template. New ID: {new_id}"
                )

                # Share sheet with user email if provided
                if user_email:
                    print(f"[STORAGE] Granting access to user: {user_email}")
                    user_permission = {
                        "type": "user",
                        "role": "writer",
                        "emailAddress": user_email,
                    }

                    self.drive_service.permissions().create(  # type: ignore[attr-defined]
                        fileId=new_id,
                        body=user_permission,
                        supportsAllDrives=True,
                        sendNotificationEmail=False,
                    ).execute()

                self.spreadsheet = self.client.open_by_key(new_id)

            self.sheet = self.spreadsheet.sheet1
            self._ensure_header_row()
            print(
                "[STORAGE] Google Sheets connection initialized successfully via Service Account."
            )

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
            raw_links = self.sheet.col_values(3)

            if len(raw_links) <= 1:
                return set()

            existing_links: set[str] = {
                str(link).strip()
                for link in raw_links[1:]
                if link is not None and str(link).strip()
            }

            return existing_links

        except Exception as e:
            print(f"[WARN] Failed to load existing links from sheet: {e}")
            return set()

    def _safe_batch_update(self, payload: dict, max_retries: int = 3) -> None:
        """Helper to execute batch update requests with rate-limit retries."""
        for attempt in range(max_retries):
            try:
                self.sheet.spreadsheet.batch_update(payload)
                return
            except gspread.exceptions.APIError as err:
                if "429" in str(err) and attempt < max_retries - 1:
                    sleep_time = (attempt + 1) * 3
                    print(f"[WARN] Quota limit hit (429). Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    raise err

    def clear_and_replace_listings(
        self,
        listings: list,
        collaborators: list[str] | None = None,
        user_email: str | None = None,
    ) -> None:
        """Clears sheet, populates property listings, applies text wrapping,

        and dynamically sets rating headers for connected users.
        """
        if not hasattr(self, "sheet") or self.sheet is None:
            return

        try:
            self.sheet.clear()

            # 1. Dynamically parse the primary user's name from email or gspread permissions
            user_name = None

            if user_email and "@" in user_email:
                user_name = user_email.split("@")[0].split(".")[0].capitalize()
            elif collaborators and len(collaborators) > 0 and "@" in collaborators[0]:
                user_name = collaborators[0].split("@")[0].split(".")[0].capitalize()

            # If email is not supplied, fetch permissions safely via gspread
            if not user_name:
                try:
                    perms = self.spreadsheet.list_permissions()
                    for p in perms:
                        # Extract emailAddress and force default to empty string
                        email = p.get("emailAddress") or p.get("email", "")

                        # Combined into a single type-safe if statement
                        if (
                            isinstance(email, str)
                            and email.strip()
                            and not email.endswith("gserviceaccount.com")
                        ):
                            user_name = email.split("@")[0].split(".")[0].capitalize()
                            break
                except Exception as perm_err:
                    print(f"[WARN] Failed to fetch gspread permissions: {perm_err}")

            if not user_name:
                user_name = "User"

            rating_headers = [f"Rating ({user_name})", "Avg Rating"]

            base_headers = [
                h.value
                for h in ColumnHeader
                if not h.value.startswith("Rating") and h.value != "Avg Rating"
            ]
            headers = base_headers + rating_headers
            total_cols = len(headers)

            rating_col_idx = len(base_headers) + 1
            rating_col_letter = gspread.utils.rowcol_to_a1(1, rating_col_idx).replace(
                "1", ""
            )

            logo_url = "https://res.cloudinary.com/bgnfvyt8/image/upload/v1787783775/immoo_logo_main2.png"
            slogan_text = "   IMMOO   •   Your Personal Real Estate Intelligence & Listing Aggregator"

            rows = []
            for idx, listing in enumerate(listings, start=3):
                row_data = (
                    listing.to_sheet_row()
                    if hasattr(listing, "to_sheet_row")
                    else list(listing.values())
                )
                row_data.append("")  # Slot for star rating chip
                row_data.append(
                    f'=IFERROR(VALUE(REGEXEXTRACT({rating_col_letter}{idx}, "\\d+")), "-")'
                )
                rows.append(row_data)

            payload_values = [
                [f'=IMAGE("{logo_url}", 1)', slogan_text],
                headers,
            ] + rows

            self.sheet.update(
                values=payload_values,
                range_name="A1",
                value_input_option=gspread.utils.ValueInputOption.user_entered,
            )

            sheet_id = self.sheet.id
            status_options = [status.value for status in StatusEnum]
            star_options = ["⭐ 1", "⭐ 2", "⭐ 3", "⭐ 4", "⭐ 5"]

            requests = [
                # Top Banner Merge
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 1,
                            "endColumnIndex": total_cols,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                },
                # Column C (Title) Width -> 350px
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 2,
                            "endIndex": 3,
                        },
                        "properties": {"pixelSize": 350},
                        "fields": "pixelSize",
                    }
                },
                # Column D (Website Link) Width -> 180px
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 3,
                            "endIndex": 4,
                        },
                        "properties": {"pixelSize": 180},
                        "fields": "pixelSize",
                    }
                },
                # Column E (Location) Width -> 200px
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 4,
                            "endIndex": 5,
                        },
                        "properties": {"pixelSize": 200},
                        "fields": "pixelSize",
                    }
                },
                # Row Heights
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 0,
                            "endIndex": 1,
                        },
                        "properties": {"pixelSize": 50},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 2,
                        },
                        "properties": {"pixelSize": 36},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 2,
                            "endIndex": max(len(rows) + 2, 20),
                        },
                        "properties": {"pixelSize": 65},
                        "fields": "pixelSize",
                    }
                },
                # Global Dark Theme Styling with ENFORCED WRAP Strategy on Data Cells
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 0,
                            "endColumnIndex": total_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.06,
                                    "green": 0.09,
                                    "blue": 0.16,
                                },
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0.97,
                                        "green": 0.98,
                                        "blue": 0.99,
                                    },
                                    "fontSize": 10,
                                },
                                "verticalAlignment": "MIDDLE",
                                "horizontalAlignment": "CENTER",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                # Left-Align Title (Col C) & Website Link (Col D)
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 2,
                            "endColumnIndex": 4,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "LEFT",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.wrapStrategy",
                    }
                },
                # Top Banner Formatting
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": total_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.31,
                                    "green": 0.27,
                                    "blue": 0.90,
                                },
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": {
                                        "red": 1,
                                        "green": 1,
                                        "blue": 1,
                                    },
                                    "fontSize": 12,
                                },
                                "horizontalAlignment": "LEFT",
                                "verticalAlignment": "MIDDLE",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                # Header Row Formatting
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": total_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.19,
                                    "green": 0.18,
                                    "blue": 0.51,
                                },
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": {
                                        "red": 1,
                                        "green": 1,
                                        "blue": 1,
                                    },
                                    "fontSize": 11,
                                },
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                # Status Dropdown Chips
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": max(len(rows) + 2, 200),
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": opt} for opt in status_options
                                ],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                },
                # Rating Dropdown Chips
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": max(len(rows) + 2, 200),
                            "startColumnIndex": rating_col_idx - 1,
                            "endColumnIndex": rating_col_idx,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": opt} for opt in star_options
                                ],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                },
            ]

            self._safe_batch_update({"requests": requests})
            print(f"[STORAGE] Populated sheet with rating column for user: {user_name}")

        except Exception as e:
            print(f"[ERROR] Failed to replace listings in Google Sheets: {e}")

    def add_collaborator_column(self, collaborator_name: str) -> None:
        """Dynamically inserts a new rating column before 'Avg Rating', applies soft warning

        protection, and updates the 'Avg Rating' column formulas to compute the average
        across all reviewer rating columns.
        """
        if not hasattr(self, "sheet") or self.sheet is None:
            raise ValueError("Spreadsheet connection is not initialized.")

        headers = self.sheet.row_values(2)
        formatted_name = collaborator_name.strip().capitalize()
        new_header = f"Rating ({formatted_name})"

        if new_header in headers:
            print(f"[STORAGE] Column '{new_header}' already exists.")
            return

        # 1. Locate column positions
        avg_idx = (
            headers.index("Avg Rating") + 1
            if "Avg Rating" in headers
            else len(headers) + 1
        )

        # 2. Insert empty column & set new header value
        self.sheet.insert_cols([[""]], col=avg_idx)
        self.sheet.update_cell(2, avg_idx, new_header)

        sheet_id = self.sheet.id
        star_options = ["⭐ 1", "⭐ 2", "⭐ 3", "⭐ 4", "⭐ 5"]

        # 3. Calculate dynamic A1 range for rating columns to compute Avg Rating formula
        # Find index of the very first rating column (e.g., Rating (Nicolas))
        rating_headers = [h for h in headers if h.startswith("Rating")]
        first_rating_idx = (
            headers.index(rating_headers[0]) + 1 if rating_headers else avg_idx
        )

        first_rating_letter = gspread.utils.rowcol_to_a1(1, first_rating_idx).replace(
            "1", ""
        )
        last_rating_letter = gspread.utils.rowcol_to_a1(1, avg_idx).replace("1", "")
        avg_rating_letter = gspread.utils.rowcol_to_a1(1, avg_idx + 1).replace("1", "")

        # 4. Prepare formula updates for Avg Rating column (Rows 3 to 200)
        avg_formula_updates = []
        for row in range(3, 201):
            formula = (
                f"=IFERROR(AVERAGE(ARRAYFORMULA(VALUE(REGEXEXTRACT("
                f"FILTER({first_rating_letter}{row}:{last_rating_letter}{row}, "
                f'{first_rating_letter}{row}:{last_rating_letter}{row}<>""), "\\d+")))), "-")'
            )
            avg_formula_updates.append([formula])

        # Batch update the Avg Rating formulas
        self.sheet.update(
            range_name=f"{avg_rating_letter}3:{avg_rating_letter}200",
            values=avg_formula_updates,
            raw=False,
        )

        # 5. UI Formatting, Data Validation & Soft Warning Protection
        requests = [
            # Header styling (Row 2)
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": avg_idx - 1,
                        "endColumnIndex": avg_idx,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.19,
                                "green": 0.18,
                                "blue": 0.51,
                            },
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "fontSize": 11,
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat",
                }
            },
            # Star rating dropdown chips (Rows 3-200)
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 2,
                        "endRowIndex": 200,
                        "startColumnIndex": avg_idx - 1,
                        "endColumnIndex": avg_idx,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": opt} for opt in star_options
                            ],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            },
            # Soft Protection Warning Prompt
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": avg_idx - 1,
                            "endColumnIndex": avg_idx,
                        },
                        "description": f"Rating Column - {formatted_name}",
                        "warningOnly": True,
                    }
                }
            },
        ]

        self._safe_batch_update({"requests": requests})
        print(
            f"[STORAGE] Added rating column for '{formatted_name}' and updated Avg Rating formulas."
        )
