from pydantic import BaseModel, Field
from src.enums.table import StatusEnum


class RealEstateListing(BaseModel):
    """Core domain model representing a scraped real estate listing."""

    title: str = Field(default="", description="Property listing title.")
    website_link: str = Field(..., description="Direct URL to the property listing.")
    main_picture: str = Field(default="", description="Primary image URL.")
    location: str = Field(..., description="Location or zip code.")
    price: float = Field(default=0.0, ge=0.0)
    size_sqm: float = Field(default=0.0, ge=0.0)
    room_num: int = Field(default=0, ge=0)
    bedroom_num: int = Field(default=0, ge=0)

    dpe: str = Field(default="N/A", description="Energy class rating (A-G).")
    floor: str = Field(default="N/A")
    has_garden: bool = Field(default=False)

    status: StatusEnum = Field(default=StatusEnum.NEW)
    highlights: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)

    @property
    def price_per_sqm(self) -> float:
        if self.size_sqm > 0:
            return round(self.price / self.size_sqm, 2)
        return 0.0

    def to_sheet_row(self) -> list[str | int | float | bool]:
        """Format listing instance into a flat list matching Google Sheet headers."""
        return [
            self.status.value,
            self.title,
            self.website_link,
            self.main_picture,
            self.location,
            self.room_num,
            self.bedroom_num,
            self.size_sqm,
            self.price,
            self.price_per_sqm,
            self.dpe,
            self.has_garden,
            self.floor,
            ", ".join(self.drawbacks)
            if isinstance(self.drawbacks, list)
            else self.drawbacks,
            ", ".join(self.highlights)
            if isinstance(self.highlights, list)
            else self.highlights,
        ]
