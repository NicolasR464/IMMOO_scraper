from typing import Any
from urllib.parse import quote

import requests


class StreamEstateError(Exception):
    """Raised when Stream Estate API request fails."""


class StreamEstateClient:
    """Client for fetching real estate documents via Stream Estate API using official query params."""

    BASE_URL = "https://api.stream.estate/documents/properties"

    def __init__(self, api_key: str):
        self.api_key = api_key.strip() if api_key else ""

    def _resolve_location_params(self, location_query: str) -> list[tuple[str, str]]:
        """Resolves a single location string to an official Stream Estate location parameter."""
        clean = location_query.strip().lower()

        # 1. Direct 5-digit zip code (e.g. "77300", "75011") -> Use official `includedZipcodes[]`
        if clean.isdigit() and len(clean) == 5:
            print(f"[STREAM ESTATE] Querying Zipcode: {clean}")
            return [("includedZipcodes[]", clean)]

        # 2. Direct 2-digit department code (e.g. "77", "75") -> Use official `includedDepartments[]`
        if clean.isdigit() and len(clean) == 2:
            print(f"[STREAM ESTATE] Querying Department: {clean}")
            return [("includedDepartments[]", f"/departments/{clean}")]

        # 3. Dynamic Lookup for City Names
        try:
            geo_url = f"https://geo.api.gouv.fr/communes?nom={quote(clean)}&fields=codesPostaux,codeDepartement&limit=1"
            res = requests.get(geo_url, timeout=5)
            if res.ok:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    postcodes = item.get("codesPostaux", [])
                    dept_code = item.get("codeDepartement")

                    if postcodes:
                        zip_code = str(postcodes[0])
                        print(
                            f"[STREAM ESTATE] Resolved '{location_query}' to Zipcode: {zip_code}"
                        )
                        return [("includedZipcodes[]", zip_code)]
                    elif dept_code:
                        print(
                            f"[STREAM ESTATE] Resolved '{location_query}' to Department: {dept_code}"
                        )
                        return [("includedDepartments[]", f"/departments/{dept_code}")]
        except Exception as err:
            print(f"[WARN] Failed to resolve city name '{location_query}': {err}")

        # Fallback default: Department 75
        return [("includedDepartments[]", "/departments/75")]

    def fetch_properties_for_single_location(
        self,
        location: str,
        min_price: int = 0,
        max_price: int = 0,
        min_space: int = 0,
        items_per_page: int = 30,
    ) -> list[dict[str, Any]]:
        params = self._resolve_location_params(location)

        params.extend(
            [
                ("transactionType", "0"),
                ("withCoherentPrice", "true"),
                ("itemsPerPage", str(items_per_page)),
            ]
        )

        if min_price > 0:
            params.append(("budgetMin", str(min_price)))
        if max_price > 0:
            params.append(("budgetMax", str(max_price)))
        if min_space > 0:
            params.append(("surfaceMin", str(min_space)))

        headers = {
            "Accept": "application/json",
            "X-API-KEY": self.api_key,
        }

        res = requests.get(self.BASE_URL, headers=headers, params=params, timeout=15)

        # RAISE ERROR IMMEDIATELY ON NON-200 STATUS
        if not res.ok:
            error_detail = res.text
            try:
                err_json = res.json()
                error_detail = (
                    err_json.get("hydra:description")
                    or err_json.get("detail")
                    or res.text
                )
            except Exception:
                pass

            print(f"[STREAM ESTATE ERROR] HTTP {res.status_code} -> {res.text}")
            raise StreamEstateError(
                f"Stream Estate API Error ({res.status_code}): {error_detail}"
            )

        data = res.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("hydra:member", [])
        return []

    def fetch_properties(
        self,
        locations: list[str],
        min_price: int = 0,
        max_price: int = 0,
        min_space: int = 0,
        min_rooms: int = 1,
        min_bedrooms: int = 1,
        items_per_page: int = 30,
    ) -> list[dict[str, Any]]:
        all_properties: list[dict[str, Any]] = []
        seen_ids = set()

        for loc in locations:
            props = self.fetch_properties_for_single_location(
                location=loc,
                min_price=min_price,
                max_price=max_price,
                min_space=min_space,
                items_per_page=items_per_page,
            )
            for p in props:
                prop_id = p.get("@id") or p.get("uuid")
                if prop_id and prop_id not in seen_ids:
                    seen_ids.add(prop_id)
                    all_properties.append(p)

        print(
            f"[STREAM ESTATE] Retreived {len(all_properties)} total listings across all locations."
        )
        return all_properties
