import json
from pathlib import Path

from src.config import Config, SearchPreferences
from src.domain.models import RealEstateListing
from src.services.ai_analyzer import GeminiAnalyzer
from src.services.storage import GoogleSheetsStorage
from src.services.streamestate_client import StreamEstateClient

OUTPUT_DIR = Path("output")
CACHE_FILE = OUTPUT_DIR / "extracted_listings.json"


def clean_num(val: float | int) -> int | float:
    """Converts a float to an int if it represents a whole number for clean JSON serialization."""
    f_val = float(val)
    return int(f_val) if f_val.is_integer() else f_val


def run_pipeline(payload, access_token: str = "") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload_dict = (
        payload.model_dump()
        if hasattr(payload, "model_dump")
        else (payload if isinstance(payload, dict) else payload.__dict__)
    )

    print("\n" + "=" * 50)
    print("🚀 PIPELINE STARTED WITH CLIENT PAYLOAD:")
    print(json.dumps(payload_dict, indent=2))
    print("=" * 50 + "\n")

    # 1. Load config and credentials
    config = Config()
    streamestate_key = config.streamestate_api_key.get_secret_value()
    gemini_key = config.gemini_api_key.get_secret_value()

    # 2. Instantiate storage client
    storage = None
    existing_links = set()
    if access_token:
        try:
            storage = GoogleSheetsStorage(
                access_token=access_token, sheet_name=config.google_sheet_name
            )
            existing_links = storage.load_existing_links()
        except Exception as e:
            print(f"[WARN] Storage initialization skipped or failed: {e}")

    new_listings: list[RealEstateListing] = []

    # 3. Check for MOCK mode override
    use_mock = getattr(config, "use_mock", False)

    if use_mock and CACHE_FILE.exists():
        print(
            f"[MOCK MODE] Found local file at '{CACHE_FILE}'. Skipping Stream Estate API call."
        )
        try:
            cached_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            new_listings = [
                RealEstateListing(**item) if isinstance(item, dict) else item
                for item in cached_data
            ]
            print(
                f"[MOCK MODE] Successfully loaded {len(new_listings)} listings from local file."
            )
        except Exception as err:
            print(f"[ERROR] Failed to read mock file '{CACHE_FILE}': {err}")
            raise Exception(f"Failed to read local mock file: {err}")

    else:
        # 4. Live API Execution Mode
        client = StreamEstateClient(api_key=streamestate_key)
        ai_analyzer = GeminiAnalyzer(api_key=gemini_key)

        raw_locations = payload_dict.get("locations", [])
        if not raw_locations:
            raw_locations = ["Paris"]

        prefs = SearchPreferences(
            locations=raw_locations,
            min_price=int(payload_dict.get("minPrice", 0)),
            max_price=int(payload_dict.get("maxPrice", 0)),
            min_space=int(payload_dict.get("minSpace", 0)),
            min_rooms=int(payload_dict.get("minRooms", 1)),
            min_bedrooms=int(payload_dict.get("minBedrooms", 1)),
        )

        print("[STREAM ESTATE] Querying live Stream Estate API...")
        raw_properties = client.fetch_properties(
            locations=prefs.locations,
            min_price=prefs.min_price,
            max_price=prefs.max_price,
            min_space=prefs.min_space,
            min_rooms=prefs.min_rooms,
            min_bedrooms=prefs.min_bedrooms,
        )

        # 5. Extract and normalize listing objects safely
        for prop in raw_properties:
            if not isinstance(prop, dict):
                continue

            # Skip only if property is explicitly flagged as expired at top level
            if prop.get("expired") is True:
                continue

            adverts = prop.get("adverts") or []

            # Filter active adverts safely
            active_adverts = [
                adv
                for adv in adverts
                if isinstance(adv, dict) and adv.get("expired") is not True
            ]

            primary_advert = (
                active_adverts[0] if active_adverts else (adverts[0] if adverts else {})
            )
            if not primary_advert or not isinstance(primary_advert, dict):
                continue

            link = primary_advert.get("url") or prop.get("@id", "")
            if not link or link in existing_links:
                continue

            price = float(prop.get("price") or primary_advert.get("price") or 0.0)
            size_sqm = float(
                prop.get("surface") or primary_advert.get("surface") or 0.0
            )
            room_num = int(prop.get("room") or primary_advert.get("room") or 0)
            bedroom_num = int(prop.get("bedroom") or primary_advert.get("bedroom") or 0)

            # APPLY FILTERS SAFELY (Allow 0 if metadata omitted the room count from API)
            if size_sqm and size_sqm < prefs.min_space:
                print(
                    f"[SKIP] Surface too small: {size_sqm} m² < {prefs.min_space} m² ({link})"
                )
                continue
            if room_num > 0 and room_num < prefs.min_rooms:
                print(f"[SKIP] Too few rooms: {room_num} < {prefs.min_rooms} ({link})")
                continue
            if bedroom_num > 0 and bedroom_num < prefs.min_bedrooms:
                print(
                    f"[SKIP] Too few bedrooms: {bedroom_num} < {prefs.min_bedrooms} ({link})"
                )
                continue

            # Format location safely
            city_info = prop.get("city") or {}
            city_name = str(
                city_info.get("name", "") if isinstance(city_info, dict) else ""
            ).strip()
            zipcode = str(
                city_info.get("zipcode", "") if isinstance(city_info, dict) else ""
            ).strip()

            if city_name and zipcode:
                formatted_location = f"{city_name} ({zipcode})"
            elif city_name:
                formatted_location = city_name
            elif zipcode:
                formatted_location = zipcode
            else:
                formatted_location = prefs.locations[0]

            # Images & DPE
            pictures = prop.get("pictures") or primary_advert.get("pictures") or []
            main_pic = (
                pictures[0] if isinstance(pictures, list) and len(pictures) > 0 else ""
            )

            energy_info = primary_advert.get("energy") or {}
            dpe = (
                energy_info.get("category", "N/A")
                if isinstance(energy_info, dict)
                else "N/A"
            )

            # Land surface check
            land_surface = (
                primary_advert.get("landSurface") or prop.get("landSurface") or 0
            )
            try:
                has_garden = float(land_surface) > 0
            except (ValueError, TypeError):
                has_garden = False

            # Floor check
            floor_val = (
                prop.get("floor")
                if prop.get("floor") is not None
                else primary_advert.get("floor")
            )
            floor_str = str(floor_val) if floor_val is not None else "N/A"

            listing = RealEstateListing(
                title=str(
                    prop.get("title")
                    or primary_advert.get("title")
                    or "Property Listing"
                ),
                website_link=str(link),
                main_picture=str(main_pic),
                location=formatted_location,
                price=price,
                size_sqm=size_sqm,
                room_num=room_num,
                bedroom_num=bedroom_num,
                dpe=str(dpe),
                floor=floor_str,
                has_garden=has_garden,
            )

            new_listings.append(listing)
            existing_links.add(link)

        # 6. Save freshly fetched listings to output JSON file
        formatted_json_listings = []
        for listing in new_listings:
            item = listing.model_dump()
            item["price"] = clean_num(item["price"])
            item["size_sqm"] = clean_num(item["size_sqm"])
            formatted_json_listings.append(item)

        CACHE_FILE.write_text(
            json.dumps(formatted_json_listings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Exported {len(new_listings)} clean listings to {CACHE_FILE}")

    # 7. Sync active listings to Google Sheets
    if storage:
        storage.clear_and_replace_listings(new_listings)
        print(f"Synced {len(new_listings)} active listings to Google Sheets.")
    else:
        print("[WARN] Google Sheets storage client is not connected.")
