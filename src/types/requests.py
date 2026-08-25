from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    locations: list[str]
    minPrice: int = Field(default=0, ge=0)
    maxPrice: int = Field(default=5000000)
    minSpace: int = Field(default=0, ge=0)
    minRooms: int = Field(default=0, ge=0)
    minBedrooms: int = Field(default=0, ge=0)
