from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class StatusEnum(StrEnum):
    """Supported status options for the real estate pipeline."""

    NEW = "New"
    CONTACTED = "Contacted"
    VISIT_SCHEDULED = "Visit Scheduled"
    OFFER_MADE = "Offer Made"
    REJECTED = "Rejected"


class ColumnHeader(StrEnum):
    """Google Sheet header identifiers."""

    STATUS = "Status"
    WEBSITE_LINK = "Website Link"
    LOCATION = "Location"
    ROOM_NUM = "Room num"
    SIZE_SQM = "Size (sqm)"
    PRICE = "Price"
    PRICE_PER_SQM = "Price/sqm"
    GARDEN = "Garden"
    FLOOR = "Floor"
    DRAWBACKS = "Drawbacks"
    HIGHLIGHTS = "Highlights"


class ListingRowModel(BaseModel):
    """Pydantic schema representing a single row in the Google Sheet.

    Includes metadata tags to specify Google Sheets data-validation types
    (e.g., Checkboxes or Dropdown Select lists).
    """

    status: StatusEnum = Field(
        default=StatusEnum.NEW,
        description="Select dropdown column for listing status.",
        json_schema_extra={"sheet_header": ColumnHeader.STATUS, "ui_type": "dropdown"},
    )
    website_link: HttpUrl = Field(
        ...,
        description="Direct URL to the property listing.",
        json_schema_extra={"sheet_header": ColumnHeader.WEBSITE_LINK},
    )
    location: str = Field(
        ...,
        description="City or zip code of the property.",
        json_schema_extra={"sheet_header": ColumnHeader.LOCATION},
    )
    room_num: int = Field(
        default=0,
        ge=0,
        description="Total number of rooms.",
        json_schema_extra={"sheet_header": ColumnHeader.ROOM_NUM},
    )
    size_sqm: float = Field(
        default=0.0,
        ge=0.0,
        description="Living space size in square meters.",
        json_schema_extra={"sheet_header": ColumnHeader.SIZE_SQM},
    )
    price: float = Field(
        default=0.0,
        ge=0.0,
        description="Total listing price in Euros.",
        json_schema_extra={"sheet_header": ColumnHeader.PRICE},
    )
    price_per_sqm: float = Field(
        default=0.0,
        ge=0.0,
        description="Calculated price per square meter.",
        json_schema_extra={"sheet_header": ColumnHeader.PRICE_PER_SQM},
    )
    is_contacted: bool = Field(
        default=False,
        description="Checkbox ticker column indicating if the agent was contacted.",
        json_schema_extra={"sheet_header": ColumnHeader.STATUS, "ui_type": "checkbox"},
    )
    has_garden: bool = Field(
        default=False,
        description="Checkbox ticker column indicating if the property has a garden.",
        json_schema_extra={"sheet_header": ColumnHeader.GARDEN, "ui_type": "checkbox"},
    )
    floor: int | str = Field(
        default="N/A",
        description="Floor number or text description (e.g., Ground floor).",
        json_schema_extra={"sheet_header": ColumnHeader.FLOOR},
    )
    drawbacks: list[str] = Field(
        default_factory=list,
        description="List of AI-extracted drawbacks.",
        json_schema_extra={"sheet_header": ColumnHeader.DRAWBACKS},
    )
    highlights: list[str] = Field(
        default_factory=list,
        description="List of AI-extracted key features.",
        json_schema_extra={"sheet_header": ColumnHeader.HIGHLIGHTS},
    )

    def to_sheet_row(self) -> list[str | int | float | bool]:
        """Convert the Pydantic model instance directly into a row list for gspread."""
        return [
            self.status.value,
            str(self.website_link),
            self.location,
            self.room_num,
            self.size_sqm,
            self.price,
            self.price_per_sqm,
            # Google Sheets automatically renders booleans (TRUE/FALSE) as interactive checkboxes
            self.has_garden,
            str(self.floor),
            ", ".join(self.drawbacks)
            if isinstance(self.drawbacks, list)
            else self.drawbacks,
            ", ".join(self.highlights)
            if isinstance(self.highlights, list)
            else self.highlights,
        ]
