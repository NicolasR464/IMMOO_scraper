import os
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Environment variables
ZENROWS_API_KEY = os.environ.get("ZENROWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_FILE = "ADs_list.csv"

# Target URL (Example: Search listings for Fontainebleau/Avon)
TARGET_URL = "https://www.iadfrance.fr/en/ads/fontainebleau-77300/sale"

# Initialize Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)


def fetch_html_via_zenrows(url):
    endpoint = "https://api.zenrows.com/v1/"
    params = {
        "api_key": ZENROWS_API_KEY,
        "url": url,
        "js_render": "true",  # Enables JS rendering if needed
    }
    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    return response.text


def analyze_listing_with_gemini(raw_text):
    prompt = f"""
    Analyze this French real estate text and output structured JSON data:
    
    1. "has_garden": boolean (true if private garden/terrace is available, false otherwise)
    2. "floor": string or integer (e.g., "Ground Floor", "2nd Floor", "Top Floor")
    3. "flaws_and_drawbacks": array of strings (e.g., ["Street noise", "No elevator", "Major renovation needed", "Ground floor street side"])
    4. "highlights": array of strings (e.g., ["Balcony", "Quiet area", "Cellar included"])
    
    Listing Text:
    {raw_text}
    """

    # Force JSON output structure using Gemini 1.5 Flash
    response = ai_client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def main():
    # Load or initialize DataFrame
    try:
        df = pd.read_csv(CSV_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(
            columns=[
                "Status",
                "Website link",
                "Location",
                "Room num",
                "Size (sqm)",
                "Price",
                "Price/sqm",
                "Garden",
                "Floor",
                "Drawbacks",
                "Highlights",
            ]
        )

    print("Fetching page via ZenRows...")
    html_content = fetch_html_via_zenrows(TARGET_URL)
    soup = BeautifulSoup(html_content, "html.parser")

    # Adapt selectors according to target portal HTML structure
    cards = soup.select(".card-ad")
    new_rows = []

    for card in cards:
        link = card.find("a", href=True)["href"] if card.find("a", href=True) else ""
        if not link or link in df["🔗 Link"].values:
            continue  # Skip already processed listings

        card_text = card.get_text(separator=" ", strip=True)

        # Analyze unstructured text with Gemini
        ai_data = analyze_listing_with_gemini(card_text)

        # Extract basic metrics
        price = 0.0  # Parse price float from card
        sqm = 0.0  # Parse surface float from card
        price_per_sqm = round(price / sqm, 2) if sqm > 0 else None

        new_rows.append(
            {
                "Status": "New",
                "🔗 Link": link,
                "Location": "Fontainebleau / Avon",
                "Room num": None,
                "Size (sqm)": sqm,
                "Price": price,
                "Price/sqm": price_per_sqm,
                "Garden": "Yes" if ai_data.get("has_garden") else "No",
                "Floor": ai_data.get("floor", "Unknown"),
                "Drawbacks": ", ".join(ai_data.get("flaws_and_drawbacks", [])),
                "Highlights": ", ".join(ai_data.get("highlights", [])),
            }
        )

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_updated = pd.concat([df, df_new], ignore_index=True)
        df_updated.to_csv(CSV_FILE, index=False)
        print(f"Added {len(new_rows)} new listings to CSV.")
    else:
        print("No new listings found.")


if __name__ == "__main__":
    main()
