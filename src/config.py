import os
from dataclasses import dataclass, field
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()


@dataclass
class SearchPreferences:
    locations: list[str] = field(
        default_factory=lambda: ["77300", "77210"]
    )  # Fontainebleau, Avon
    min_price: int = 400000
    max_price: int = 550000
    min_space: int = 80
    min_rooms: int = 4
    max_rooms: int = 5
    min_bedrooms: int = 3
    max_bedrooms: int = 4
    estate_types: list[str] = field(default_factory=lambda: ["House", "Apartment"])


class Config:
    ZENROWS_API_KEY: str = os.environ.get("ZENROWS_API_KEY", "")
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    GOOGLE_SHEET_NAME: str = os.environ.get("GOOGLE_SHEET_NAME", "ADs_list")

    # Default fallback preferences from env
    PREFERENCES = SearchPreferences(
        min_price=int(os.environ.get("SEARCH_MIN_PRICE", 400000)),
        max_price=int(os.environ.get("SEARCH_MAX_PRICE", 550000)),
        min_space=int(os.environ.get("SEARCH_MIN_SPACE", 80)),
        min_rooms=int(os.environ.get("SEARCH_MIN_ROOMS", 4)),
        max_rooms=int(os.environ.get("SEARCH_MAX_ROOMS", 5)),
        min_bedrooms=int(os.environ.get("SEARCH_MIN_BEDROOMS", 3)),
        max_bedrooms=int(os.environ.get("SEARCH_MAX_BEDROOMS", 4)),
    )

    @classmethod
    def get_target_urls(cls, prefs: SearchPreferences | None = None) -> list[str]:
        """Generate target scraping URLs. Uses client-provided preferences or falls back to defaults."""
        p = prefs or cls.PREFERENCES
        urls = []

        # 1. SeLoger Dynamic URL Generator
        seloger_params = {
            "distributionTypes": "Buy",
            "estateTypes": ",".join(p.estate_types),
            "numberOfBedroomsMin": p.min_bedrooms,
            "numberOfBedroomsMax": p.max_bedrooms,
            "numberOfRoomsMin": p.min_rooms,
            "numberOfRoomsMax": p.max_rooms,
            "priceMin": p.min_price,
            "priceMax": p.max_price,
            "spaceMin": p.min_space,
            "priceType": "Default",
            "order": "DateDesc",
        }
        seloger_url = (
            f"https://www.seloger.com/classified-search?{urlencode(seloger_params)}"
        )
        urls.append(seloger_url)

        # 2. IAD France Dynamic URLs (per location)
        for zip_code in p.locations:
            iad_url = f"https://www.iadfrance.fr/en/ads/search?zip={zip_code}&min_price={p.min_price}&max_price={p.max_price}&min_surface={p.min_space}"
            urls.append(iad_url)

        return urls
