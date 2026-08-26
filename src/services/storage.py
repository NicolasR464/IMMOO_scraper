import time

import gspread
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
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

from src.enums.table import ColumnHeader, StatusEnum


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

    def _apply_theme_and_dropdowns(self, total_columns: int = 18) -> None:
        """Applies layout styles and dropdown validation in a single batch request to prevent 429 rate limits."""
        if not hasattr(self, "sheet") or self.sheet is None:
            return

        try:
            end_col = gspread.utils.rowcol_to_a1(1, max(total_columns, 18)).replace(
                "1", ""
            )

            # 1. Unmerge & Merge Top Banner
            try:
                self.sheet.unmerge_cells(f"A1:{end_col}1")
            except Exception:
                pass

            self.sheet.merge_cells(f"B1:{end_col}1", merge_type="MERGE_ALL")

            # 2. Set Column Widths
            set_column_width(self.sheet, "A", 160)  # Action Status Dropdown
            set_column_width(self.sheet, "B", 120)  # Main Picture (Compact)
            set_column_width(self.sheet, "C", 220)  # Title
            set_column_width(self.sheet, "D", 150)  # Website Link

            # 3. Apply Cell Formatting (gspread_formatting)
            banner_format = CellFormat(
                backgroundColor=Color(0.31, 0.27, 0.90),
                textFormat=TextFormat(
                    bold=True, foregroundColor=Color(1, 1, 1), fontSize=12
                ),
                horizontalAlignment="LEFT",
                verticalAlignment="MIDDLE",
            )
            format_cell_range(self.sheet, f"A1:{end_col}1", banner_format)
            set_row_height(self.sheet, "1", 50)

            header_format = CellFormat(
                backgroundColor=Color(0.19, 0.18, 0.51),
                textFormat=TextFormat(
                    bold=True, foregroundColor=Color(1, 1, 1), fontSize=11
                ),
                horizontalAlignment="CENTER",
                verticalAlignment="MIDDLE",
            )
            format_cell_range(self.sheet, f"A2:{end_col}2", header_format)
            set_row_height(self.sheet, "2", 36)

            data_format = CellFormat(
                backgroundColor=Color(0.06, 0.09, 0.16),
                textFormat=TextFormat(
                    foregroundColor=Color(0.97, 0.98, 0.99), fontSize=10
                ),
                horizontalAlignment="CENTER",
                verticalAlignment="MIDDLE",
            )
            format_cell_range(self.sheet, f"A3:{end_col}200", data_format)

            for r in range(3, 100):
                set_row_height(self.sheet, str(r), 65)

            left_align_format = CellFormat(
                horizontalAlignment="LEFT", verticalAlignment="MIDDLE"
            )
            format_cell_range(self.sheet, "C3:D200", left_align_format)

            currency_format = CellFormat(
                numberFormat=NumberFormat(type="CURRENCY", pattern="€#,##0"),
                horizontalAlignment="RIGHT",
                verticalAlignment="MIDDLE",
            )
            format_cell_range(self.sheet, "I3:J200", currency_format)

            link_format = CellFormat(
                textFormat=TextFormat(
                    foregroundColor=Color(0.22, 0.74, 0.97), underline=True
                ),
                horizontalAlignment="LEFT",
                verticalAlignment="MIDDLE",
            )
            format_cell_range(self.sheet, "D3:D200", link_format)

            # 4. SINGLE BATCH REQUEST FOR DROPDOWN CHIPS
            grid_range = a1_range_to_grid_range("A3:A200")
            grid_range["sheetId"] = self.sheet.id
            status_options = [status.value for status in StatusEnum]

            dropdown_request = {
                "setDataValidation": {
                    "range": grid_range,
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
            }

            # Execute batch update with rate-limit protection
            self._safe_batch_update({"requests": [dropdown_request]})

        except Exception as err:
            print(f"[WARN] Failed to apply sheet styling: {err}")

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
        self, listings: list, collaborators: list[str] | None = None
    ) -> None:
        """Clears sheet, populates property listings with dynamic user rating columns,

        applies dark UI theme, and attaches dropdown validation chips in 2 API calls.
        """
        if not hasattr(self, "sheet") or self.sheet is None:
            return

        try:
            # 1. Clear contents
            self.sheet.clear()

            # 2. Setup dynamic collaborator rating columns
            users = collaborators if collaborators else ["User 1", "User 2"]
            rating_headers = [f"Rating ({user})" for user in users] + ["Avg Rating"]

            # Build full list of headers
            base_headers = [
                h.value
                for h in ColumnHeader
                if not h.value.startswith("Rating") and h.value != "Avg Rating"
            ]
            headers = base_headers + rating_headers
            total_cols = len(headers)

            # Determine column letters for the dynamic AVERAGE formula
            first_rating_col_idx = len(base_headers) + 1  # 1-indexed
            last_rating_col_idx = len(base_headers) + len(users)

            first_col_letter = gspread.utils.rowcol_to_a1(
                1, first_rating_col_idx
            ).replace("1", "")
            last_col_letter = gspread.utils.rowcol_to_a1(
                1, last_rating_col_idx
            ).replace("1", "")

            # 3. Build listing rows
            logo_url = "https://res.cloudinary.com/bgnfvyt8/image/upload/v1787740895/immoo_logo_main.png"
            slogan_text = "   IMMOO   •   Your Personal Real Estate Intelligence & Listing Aggregator"

            rows = []
            for idx, listing in enumerate(listings, start=3):
                row_data = (
                    listing.to_sheet_row()
                    if hasattr(listing, "to_sheet_row")
                    else list(listing.values())
                )
                # Append empty placeholders for each user rating
                row_data.extend([""] * len(users))
                # Append dynamic average rating formula across user columns
                row_data.append(
                    f'=IFERROR(AVERAGE({first_col_letter}{idx}:{last_col_letter}{idx}), "-")'
                )
                rows.append(row_data)

            # Single write request for all values
            payload_values = [
                [f'=IMAGE("{logo_url}", 1)', slogan_text],
                headers,
            ] + rows

            self.sheet.update(
                values=payload_values,
                range_name="A1",
                value_input_option=gspread.utils.ValueInputOption.user_entered,
            )

            # 4. Construct complete formatting and data validation batch request
            sheet_id = self.sheet.id
            status_options = [status.value for status in StatusEnum]

            dark_bg = {"red": 0.06, "green": 0.09, "blue": 0.16}
            white_text = {
                "foregroundColor": {"red": 0.97, "green": 0.98, "blue": 0.99},
                "fontSize": 10,
            }

            def make_cell_format(
                horiz_align: str, number_format: dict | None = None
            ) -> dict:
                fmt = {
                    "backgroundColor": dark_bg,
                    "textFormat": white_text,
                    "verticalAlignment": "MIDDLE",
                    "horizontalAlignment": horiz_align,
                }
                if number_format:
                    fmt["numberFormat"] = number_format
                return fmt

            requests = [
                # Merge B1:R1 Banner
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
                # Column Widths
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 1,
                        },
                        "properties": {"pixelSize": 190},
                        "fields": "pixelSize",
                    }
                },  # A: Status
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 1,
                            "endIndex": 2,
                        },
                        "properties": {"pixelSize": 120},
                        "fields": "pixelSize",
                    }
                },  # B: Main Picture
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 2,
                            "endIndex": 3,
                        },
                        "properties": {"pixelSize": 380},
                        "fields": "pixelSize",
                    }
                },  # C: Title
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 3,
                            "endIndex": 4,
                        },
                        "properties": {"pixelSize": 150},
                        "fields": "pixelSize",
                    }
                },  # D: Link
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 4,
                            "endIndex": 5,
                        },
                        "properties": {"pixelSize": 170},
                        "fields": "pixelSize",
                    }
                },  # E: Location
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
                # Row 1 Banner Format
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
                # Row 2 Header Format
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
                # LEFT ALIGNED DATA COLUMNS (Title, Link, Location, Drawbacks, Highlights) -> C, D, E, N, O
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 2,
                            "endColumnIndex": 5,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("LEFT")},
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 13,
                            "endColumnIndex": 15,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("LEFT")},
                        "fields": "userEnteredFormat",
                    }
                },
                # CENTER ALIGNED DATA COLUMNS -> A, B, F, G, H, K, L, M, and Dynamic Ratings
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 0,
                            "endColumnIndex": 2,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("CENTER")},
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 5,
                            "endColumnIndex": 8,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("CENTER")},
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 10,
                            "endColumnIndex": 13,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("CENTER")},
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 15,
                            "endColumnIndex": total_cols,
                        },
                        "cell": {"userEnteredFormat": make_cell_format("CENTER")},
                        "fields": "userEnteredFormat",
                    }
                },
                # RIGHT ALIGNED & CURRENCY COLUMNS -> I, J
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
                            "startColumnIndex": 8,
                            "endColumnIndex": 10,
                        },
                        "cell": {
                            "userEnteredFormat": make_cell_format(
                                "RIGHT", {"type": "CURRENCY", "pattern": "€#,##0"}
                            )
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                # Dropdown Validation Chips for Column A (A3:A200)
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": 200,
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
            ]

            # Execute batch update
            self._safe_batch_update({"requests": requests})
            print(
                f"[STORAGE] Successfully populated listings with collaborator columns: {users}"
            )

        except Exception as e:
            print(f"[ERROR] Failed to replace listings in Google Sheets: {e}")
