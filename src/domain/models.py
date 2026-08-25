from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIAnalysisResult:
    has_garden: bool = False
    floor: str = "Unknown"
    extracted_location: str = "Unknown"
    flaws_and_drawbacks: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class RealEstateListing:
    link: str
    location: str
    price: float
    size_sqm: float
    room_num: Optional[float] = None
    status: str = "New"
    rating: Optional[float] = None
    analysis: Optional[AIAnalysisResult] = None

    @property
    def price_per_sqm(self) -> Optional[float]:
        if self.size_sqm and self.size_sqm > 0:
            return round(self.price / self.size_sqm, 2)
        return None

    def to_sheet_row(self) -> list:
        analysis = self.analysis
        return [
            self.status,
            self.link,
            self.location,
            self.room_num or "",
            self.size_sqm,
            self.price,
            self.price_per_sqm or "",
            "Yes" if analysis and analysis.has_garden else "No",
            analysis.floor if analysis else "Unknown",
            ", ".join(analysis.flaws_and_drawbacks) if analysis else "",
            ", ".join(analysis.highlights) if analysis else "",
        ]
