import json
import os

import gspread

from src.domain.models import RealEstateListing
from src.enums.table import ColumnHeader


class GoogleSheetsStorage:
    def __init__(self, sheet_name: str = "ADs_list"):
        raw_creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw_creds:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON environment variable is required"
            )

        # 1. Parse JSON safely handling escaped newlines
        try:
            if isinstance(raw_creds, str):
                clean_json = raw_creds.replace("\\n", "\n")
                creds_dict = json.loads(clean_json)
            else:
                creds_dict = raw_creds
        except Exception as e:
            raise ValueError(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

        # 2. Validate mandatory fields before initializing gspread
        required_fields = ["client_email", "token_uri", "private_key"]
        missing = [field for field in required_fields if field not in creds_dict]
        if missing:
            raise ValueError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON is missing fields: {', '.join(missing)}"
            )

        # 3. Initialize gspread client
        self.client = gspread.service_account_from_dict(creds_dict)
        self.sheet = self.client.open(sheet_name).sheet1
        self._ensure_header_row()

    def _ensure_header_row(self) -> None:
        """Initialize sheet headers if empty."""
        headers = [header.value for header in ColumnHeader]
        first_row = self.sheet.row_values(1)
        if not first_row:
            self.sheet.append_row(headers)

    def load_existing_links(self) -> set[str]:
        records = self.sheet.get_all_records()
        target_column = ColumnHeader.WEBSITE_LINK.value

        return {row[target_column] for row in records if row.get(target_column)}

    def append_listings(self, listings: list[RealEstateListing]) -> None:
        rows_to_append = [listing.to_sheet_row() for listing in listings]
        if rows_to_append:
            self.sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
