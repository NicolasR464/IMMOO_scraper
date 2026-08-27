from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class StatusEnum(StrEnum):
    """Actionable buyer workflow statuses."""

    TO_REVIEW = "📌 To Review"
    SHORTLISTED = "⭐ Shortlisted"
    CONTACTED = "📞 Agent Contacted"
    VISIT_SCHEDULED = "🗓️ Visit Scheduled"
    OFFER_MADE = "💶 Offer Made"
    REJECTED = "❌ Rejected"


class ColumnHeader(StrEnum):
    ACTION_STATUS = "Action Status"
    MAIN_PICTURE = "Main Picture"
    TITLE = "Title"
    WEBSITE_LINK = "Website Link"
    LOCATION = "Location"
    ROOM_NUM = "Room Num"
    BEDROOM_NUM = "Bedroom Num"
    SIZE_SQM = "Size (sqm)"
    PRICE = "Price"
    PRICE_PER_SQM = "Price/sqm"
    DPE = "DPE"
    HAS_GARDEN = "Garden"
    FLOOR = "Floor"
    DRAWBACKS = "Drawbacks"
    HIGHLIGHTS = "Highlights"
    RATING_USER1 = "Rating (User 1)"
    RATING_USER2 = "Rating (User 2)"
    AVG_RATING = "Avg Rating"


class ListingRowModel(BaseModel):
    """Pydantic schema representing a single row in the Google Sheet."""

    status: StatusEnum = Field(
        default=StatusEnum.TO_REVIEW,  # <-- FIXED HERE (Changed from StatusEnum.NEW)
        json_schema_extra={
            "sheet_header": ColumnHeader.ACTION_STATUS,
            "ui_type": "dropdown",
        },
    )
    main_picture: str = Field(
        default="",
        json_schema_extra={"sheet_header": ColumnHeader.MAIN_PICTURE},
    )
    title: str = Field(
        default="",
        json_schema_extra={"sheet_header": ColumnHeader.TITLE},
    )
    website_link: HttpUrl = Field(
        ...,
        json_schema_extra={"sheet_header": ColumnHeader.WEBSITE_LINK},
    )
    location: str = Field(
        ...,
        json_schema_extra={"sheet_header": ColumnHeader.LOCATION},
    )
    room_num: int = Field(
        default=0,
        ge=0,
        json_schema_extra={"sheet_header": ColumnHeader.ROOM_NUM},
    )
    bedroom_num: int = Field(
        default=0,
        ge=0,
        json_schema_extra={"sheet_header": ColumnHeader.BEDROOM_NUM},
    )
    size_sqm: float = Field(
        default=0.0,
        ge=0.0,
        json_schema_extra={"sheet_header": ColumnHeader.SIZE_SQM},
    )
    price: float = Field(
        default=0.0,
        ge=0.0,
        json_schema_extra={"sheet_header": ColumnHeader.PRICE},
    )
    price_per_sqm: float = Field(
        default=0.0,
        ge=0.0,
        json_schema_extra={"sheet_header": ColumnHeader.PRICE_PER_SQM},
    )
    dpe: str = Field(
        default="-",
        json_schema_extra={"sheet_header": ColumnHeader.DPE},
    )
    has_garden: bool = Field(
        default=False,
        json_schema_extra={
            "sheet_header": ColumnHeader.HAS_GARDEN,
            "ui_type": "checkbox",
        },
    )
    floor: int | str = Field(
        default="-",
        json_schema_extra={"sheet_header": ColumnHeader.FLOOR},
    )
    drawbacks: list[str] = Field(
        default_factory=list,
        json_schema_extra={"sheet_header": ColumnHeader.DRAWBACKS},
    )
    highlights: list[str] = Field(
        default_factory=list,
        json_schema_extra={"sheet_header": ColumnHeader.HIGHLIGHTS},
    )
