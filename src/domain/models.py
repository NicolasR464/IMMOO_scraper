from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from src.enums.table import StatusEnum


class RealEstateListing(BaseModel):
    title: str = Field(default="", description="Property listing title.")
    website_link: str = Field(..., description="Direct URL to the property listing.")
    main_picture: str = Field(default="", description="Primary image URL.")
    location: str = Field(..., description="Location or zip code.")
    price: float = Field(default=0.0, ge=0.0)
    size_sqm: float = Field(default=0.0, ge=0.0)
    room_num: int = Field(default=0, ge=0)
    bedroom_num: int = Field(default=0, ge=0)

    dpe: str = Field(default="-", description="Energy class rating (A-G).")
    floor: str = Field(default="-")
    has_garden: bool = Field(default=False)

    status: StatusEnum = Field(default=StatusEnum.TO_REVIEW)
    highlights: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def fallback_status(cls, value: str) -> StatusEnum:
        """Map legacy status values (e.g., 'New') to default 'TO_REVIEW'."""
        try:
            return StatusEnum(value)
        except ValueError:
            return StatusEnum.TO_REVIEW

    @property
    def price_per_sqm(self) -> float:
        if self.size_sqm > 0 and self.price > 0:
            return round(self.price / self.size_sqm, 2)
        return 0.0

    def to_sheet_row(self) -> list[str | int | float | bool]:
        """Formats listing instance into a flat list matching ColumnHeader order strictly."""

        def clean(val):
            if val in (0, 0.0, "0", "N/A", "n/a", "", None):
                return "-"
            return val

        # 1. Main Picture Image Formula
        picture_formula = (
            f'=IMAGE("{self.main_picture}", 2)'
            if self.main_picture and self.main_picture.startswith("http")
            else "-"
        )

        # 2. Extract domain name for clean hyperlink formula
        if self.website_link and self.website_link.startswith("http"):
            domain = urlparse(self.website_link).netloc.replace("www.", "")
            link_label = domain.capitalize() if domain else "View Listing 🔗"
            link_formula = f'=HYPERLINK("{self.website_link}", "{link_label}")'
        else:
            link_formula = "-"

        drawbacks_str = (
            ", ".join(self.drawbacks)
            if isinstance(self.drawbacks, list) and self.drawbacks
            else "-"
        )
        highlights_str = (
            ", ".join(self.highlights)
            if isinstance(self.highlights, list) and self.highlights
            else "-"
        )

        return [
            self.status.value,  # 1. Status
            picture_formula,  # 2. Main Picture
            clean(self.title),  # 3. Title
            link_formula,  # 4. Website Link (Clean Hyperlink)
            clean(self.location),  # 5. Location
            clean(self.room_num),  # 6. Room Num
            clean(self.bedroom_num),  # 7. Bedroom Num
            clean(self.size_sqm),  # 8. Size (sqm)
            clean(self.price),  # 9. Price
            clean(self.price_per_sqm),  # 10. Price/sqm
            clean(self.dpe),  # 11. DPE
            self.has_garden,  # 12. Garden
            clean(self.floor),  # 13. Floor
            drawbacks_str,  # 14. Drawbacks
            highlights_str,  # 15. Highlights
        ]
