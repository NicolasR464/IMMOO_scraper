import re
import json
import os

import requests
from bs4 import BeautifulSoup, Tag
from pydantic import SecretStr


class ZenRowsScraper:
    """Handles fetching and parsing web pages using ZenRows proxy and anti-bot bypass."""

    def __init__(self, api_key: str | SecretStr | None = None) -> None:
        """Initialize ZenRows scraper client.

        Args:
            api_key: Optional ZenRows API key override or SecretStr.
        """
        if api_key is None:
            resolved_key = os.environ.get("ZENROWS_API_KEY", "")
        elif isinstance(api_key, SecretStr):
            resolved_key = api_key.get_secret_value()
        else:
            resolved_key = api_key

        if not resolved_key:
            raise ValueError("ZENROWS_API_KEY is not configured or is empty.")

        self.api_key = resolved_key
        self.endpoint = "https://api.zenrows.com/v1/"

    def fetch_page(self, target_url: str) -> str:
        """Fetch raw HTML content from target URL via ZenRows API with antibot bypass.

        Args:
            target_url: URL of the target real estate search/listing page.

        Returns:
            String containing rendered HTML source.
        """
        params = {
            "api_key": self.api_key,
            "url": target_url,
            "js_render": "true",
            "premium_proxy": "true",
        }

        response = requests.get(self.endpoint, params=params)
        response.raise_for_status()
        return response.text

    def extract_listing_cards(self, html_content: str) -> list[dict]:
        soup = BeautifulSoup(html_content, "html.parser")
        script_tag = soup.find("script", id="__UFRN_FETCHER__")

        if not script_tag or not script_tag.string:
            return []

        match = re.search(r'JSON\.parse\("(.*?)"\);', script_tag.string)
        if not match:
            return []

        # Fix UTF-8 encoding without double-encoding artifacts
        raw_json_str = match.group(1)
        # Replacing escaped quotes and backslashes directly keeps UTF-8 intact
        clean_json = raw_json_str.replace('\\"', '"').replace("\\\\", "\\")
        data = json.loads(clean_json)

        classifieds_dict = (
            data.get("data", {})
            .get("classified-serp-init-data", {})
            .get("pageProps", {})
            .get("classifiedsData", {})
        )

        listings = []
        for card_id, item in classifieds_dict.items():
            hard_facts = item.get("hardFacts", {})
            location = item.get("location", {}).get("address", {})

            # Extract location cleanly
            city = location.get("city", "")
            district = location.get("district", "")
            full_location = f"{district}, {city}".strip(", ") if district else city

            # Garden check from keyfacts
            key_facts = [str(kf).lower() for kf in hard_facts.get("keyfacts", [])]
            has_garden = any(
                "jardin" in kf or "terrain" in kf or "terrasse" in kf
                for kf in key_facts
            )

            # Floor check from facts
            floor_info = "N/A"
            for fact in hard_facts.get("facts", []):
                if fact.get("type") in ("numberOfFloors", "floor", "buildingFloor"):
                    val = str(fact.get("value", "")).strip()
                    if val and val != "0":
                        floor_info = val
                elif fact.get("type") in ("plotSpace", "landSpace"):
                    has_garden = True

            listings.append(
                {
                    "link": item.get("url", ""),
                    "location": full_location,
                    "price": float(hard_facts.get("price", {}).get("value", 0)),
                    "size_sqm": float(
                        next(
                            (
                                f.get("splitValue", 0)
                                for f in hard_facts.get("facts", [])
                                if f.get("type") in ("livingSpace", "overallSpace")
                            ),
                            0,
                        )
                    ),
                    "room_num": int(
                        next(
                            (
                                f.get("splitValue", 0)
                                for f in hard_facts.get("facts", [])
                                if f.get("type") == "numberOfRooms"
                            ),
                            0,
                        )
                    ),
                    "bedroom_num": int(
                        next(
                            (
                                f.get("splitValue", 0)
                                for f in hard_facts.get("facts", [])
                                if f.get("type") == "numberOfBedrooms"
                            ),
                            0,
                        )
                    ),
                    "has_garden": has_garden,
                    "floor": floor_info,
                    "text": f"{hard_facts.get('title', '')}. {item.get('mainDescription', {}).get('description', '')}",
                }
            )

        return listings
