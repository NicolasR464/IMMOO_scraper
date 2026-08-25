import json

from src.config import Config, SearchPreferences
from src.domain.models import RealEstateListing
from src.services.ai_analyzer import GeminiAnalyzer
from src.services.scraper import ZenRowsScraper
from src.services.storage import GoogleSheetsStorage


def run_pipeline(payload) -> None:
    # 1. Clean printout of client-provided payload
    payload_dict = (
        payload.model_dump() if hasattr(payload, "model_dump") else payload.__dict__
    )

    print("\n" + "=" * 50)
    print("🚀 PIPELINE STARTED WITH CLIENT PAYLOAD:")
    print(json.dumps(payload_dict, indent=2))
    print("=" * 50 + "\n")

    scraper = ZenRowsScraper()
    analyzer = GeminiAnalyzer()
    storage = GoogleSheetsStorage(sheet_name=Config.GOOGLE_SHEET_NAME)

    existing_links = storage.load_existing_links()
    new_listings: list[RealEstateListing] = []

    # 2. Map payload to SearchPreferences dataclass
    prefs = SearchPreferences(
        locations=payload.locations,
        min_price=int(payload.minPrice),
        max_price=int(payload.maxPrice),
        min_space=int(payload.minSpace),
        min_rooms=int(payload.minRooms),
        min_bedrooms=int(payload.minBedrooms),
    )

    # 3. Generate target URLs using the mapped preferences
    target_urls = Config.get_target_urls(prefs)

    for target_url in target_urls:
        print(f"Fetching listings from dynamic URL: {target_url}...")
        try:
            html = scraper.fetch_page(target_url)
            cards = scraper.extract_listing_cards(html)
        except Exception as err:
            print(f"Failed to fetch {target_url}: {err}")
            continue

        for card in cards:
            link = card["link"]
            if link in existing_links:
                continue

            print(f"Analyzing listing: {link}")
            analysis = analyzer.analyze_listing_text(card["text"])

            listing = RealEstateListing(
                link=link,
                location=analysis.extracted_location,
                price=0.0,
                size_sqm=0.0,
                analysis=analysis,
            )
            new_listings.append(listing)
            existing_links.add(link)

    if new_listings:
        storage.append_listings(new_listings)
        print(f"Appended {len(new_listings)} new matching listings to Google Sheets.")
    else:
        print("No new listings found matching your preferences.")
