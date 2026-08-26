import codecs
import json
import re
from pathlib import Path
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup


class LocationNotFoundError(Exception):
    """Raised when a location cannot be resolved to a valid SeLoger placeId."""


class ZenRowsScraper:
    """Scrapes real estate listings using ZenRows HTTP API."""

    def __init__(
        self,
        api_key: str = "",
        cache_file: str = "output/mock_seloger.html",
    ):
        self.api_key = api_key
        self.cache_file = Path(cache_file)

    def _resolve_location_code(self, location_query: str) -> str:
        """Dynamically resolves any French city name or postal code directly via SeLoger's internal API through ZenRows."""
        clean_query = location_query.strip()

        # 1. Direct 5-digit postal code support (e.g. "75011", "77300")
        if clean_query.isdigit() and len(clean_query) == 5:
            return f"AD08FR{clean_query}"

        # 2. Query SeLoger's internal API directly using ZenRows to pass anti-bot / internal routing
        try:
            target_api_url = f"https://www.seloger.com/api/v2/locations/search?text={quote(clean_query)}"
            zenrows_url = "https://api.zenrows.com/v1/"

            params = {
                "apikey": self.api_key,
                "url": target_api_url,
                "premium_proxy": "true",
            }

            res = requests.get(zenrows_url, params=params, timeout=15)

            if res.ok:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    # Extract placeId from top match (e.g., "AD08FR10001" for Paris)
                    first_match = data[0]
                    place_id = first_match.get("id") or first_match.get(
                        "params", {}
                    ).get("locations")

                    if place_id:
                        print(
                            f"[RESOLVER] Dynamic SeLoger Lookup via ZenRows: '{location_query}' -> {place_id}"
                        )
                        return str(place_id)

        except Exception as err:
            raise LocationNotFoundError(
                f"Failed to query location service for '{location_query}': {err}"
            ) from err

        # STRICT ERROR: Fails cleanly if SeLoger returns no valid matches
        raise LocationNotFoundError(
            f"Location '{location_query}' could not be resolved. Please enter a valid French city name or 5-digit postal code."
        )

    def fetch_page(
        self,
        location: str,
        min_price: int = 0,
        max_price: int = 0,
        min_space: int = 0,
        min_rooms: int = 1,
        min_bedrooms: int = 1,
    ) -> str:
        """Fetches SeLoger SERP HTML via ZenRows HTTP Proxy."""
        if self.cache_file.exists():
            print(f"[CACHE] Reading HTML from local file: {self.cache_file}")
            return self.cache_file.read_text(encoding="utf-8")

        # 1. Resolve placeId strictly
        place_id = self._resolve_location_code(location)

        # 2. Build SeLoger search URL
        query_params = {
            "distributionTypes": "Buy",
            "estateTypes": "House,Apartment",
            "locations": place_id,
            "numberOfBedroomsMin": str(min_bedrooms),
            "numberOfRoomsMin": str(min_rooms),
            "priceMin": str(min_price),
            "spaceMin": str(min_space),
            "priceType": "Default",
        }
        if max_price > 0:
            query_params["priceMax"] = str(max_price)

        target_url = (
            f"https://www.seloger.com/classified-search?{urlencode(query_params)}"
        )

        # 3. Request through ZenRows HTTP API (js_render=true enables JS rendering on standard HTTP)
        zenrows_url = "https://api.zenrows.com/v1/"
        params = {
            "apikey": self.api_key,
            "url": target_url,
            "js_render": "true",
            "premium_proxy": "true",
        }

        print(f"[FETCH] Requesting via ZenRows HTTP: {target_url}...")
        response = requests.get(zenrows_url, params=params, timeout=60)

        if not response.ok:
            raise RuntimeError(
                f"ZenRows request failed with status {response.status_code}: {response.text}"
            )

        html_content = response.text

        # 4. Save to cache
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(html_content, encoding="utf-8")
        print(f"[CACHE] Saved live DOM HTML to {self.cache_file}")

        return html_content

    def extract_listing_cards(self, html_content: str) -> list[dict]:
        """Parses rendering DOM script payload to return structured listing dicts."""
        soup = BeautifulSoup(html_content, "html.parser")
        script_tag = soup.find("script", id="__UFRN_FETCHER__")

        if not script_tag or not script_tag.string:
            print("[WARN] Could not find __UFRN_FETCHER__ script tag.")
            return []

        try:
            match = re.search(r'JSON\.parse\("(.*?)"\);', script_tag.string)
            if not match:
                return []

            raw_str = match.group(1)
            if not raw_str.endswith("}}}"):
                last_valid = raw_str.rfind('},"2')
                if last_valid != -1:
                    raw_str = raw_str[:last_valid] + "}}}}}"

            unicode_clean = codecs.decode(raw_str, "unicode_escape")
            try:
                unicode_clean = unicode_clean.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

            data = json.loads(unicode_clean)
            classifieds = (
                data.get("data", {})
                .get("classified-serp-init-data", {})
                .get("pageProps", {})
                .get("classifiedsData", {})
            )

            listings = []
            for card_id, item in classifieds.items():
                hard_facts = item.get("hardFacts", {})
                location_info = item.get("location", {}).get("address", {})

                title = hard_facts.get("title", "") or item.get(
                    "mainDescription", {}
                ).get("headline", "")
                images = item.get("gallery", {}).get("images", [])
                main_picture = images[0].get("url", "") if images else ""

                raw_price = hard_facts.get("price", {}).get("value", "0")
                cleaned_price = re.sub(r"[^\d.]", "", str(raw_price).replace(",", "."))
                price = float(cleaned_price) if cleaned_price else 0.0

                dpe = item.get("energyClass", "") or item.get("tracking", {}).get(
                    "energy_certificate", "N/A"
                )

                facts_list = hard_facts.get("facts", [])
                key_facts = [
                    str(kf).lower() for kf in hard_facts.get("keyfacts", []) if kf
                ]

                size_sqm, room_num, bedroom_num = 0.0, 0, 0
                floor_info, has_garden = "N/A", False

                for kf in key_facts:
                    if any(t in kf for t in ["jardin", "terrain", "terrasse", "parc"]):
                        has_garden = True

                for fact in facts_list:
                    ftype = fact.get("type")
                    val_str = str(fact.get("value", "")).strip()
                    split_val = str(fact.get("splitValue", "0")).replace(",", ".")

                    if ftype in ("livingSpace", "overallSpace"):
                        size_sqm = float(re.sub(r"[^\d.]", "", split_val) or 0.0)
                    elif ftype == "numberOfRooms":
                        room_num = int(re.sub(r"[^\d]", "", split_val) or 0)
                    elif ftype == "numberOfBedrooms":
                        bedroom_num = int(re.sub(r"[^\d]", "", split_val) or 0)
                    elif ftype in ("numberOfFloors", "floor", "buildingFloor"):
                        if val_str and val_str != "0":
                            floor_info = val_str
                    elif ftype in ("plotSpace", "landSpace"):
                        has_garden = True

                city = location_info.get("city", "")
                district = location_info.get("district", "")
                full_location = f"{district}, {city}".strip(", ") if district else city

                listings.append(
                    {
                        "id": card_id,
                        "title": title,
                        "main_picture": main_picture,
                        "link": item.get("url", ""),
                        "price": price,
                        "size_sqm": size_sqm,
                        "room_num": room_num,
                        "bedroom_num": bedroom_num,
                        "dpe": dpe,
                        "floor": floor_info,
                        "has_garden": has_garden,
                        "location": full_location,
                    }
                )

            return listings

        except Exception as err:
            print(f"[ERROR] Parsing script payload failed: {err}")
            return []
