import requests
from bs4 import BeautifulSoup

from src.config import Config


class ZenRowsScraper:
    def __init__(self, api_key: str = Config.ZENROWS_API_KEY):
        self.api_key = api_key
        self.endpoint = "https://api.zenrows.com/v1/"

    def fetch_page(self, url: str) -> str:
        params = {"api_key": self.api_key, "url": url, "js_render": "true"}
        response = requests.get(self.endpoint, params=params, timeout=30)
        response.raise_for_status()
        return response.text

    def extract_listing_cards(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".card-ad")
        extracted = []

        for card in cards:
            link = (
                card.find("a", href=True)["href"] if card.find("a", href=True) else ""
            )
            if link:
                extracted.append(
                    {
                        "link": link,
                        "text": card.get_text(separator=" ", strip=True),
                    }
                )
        return extracted
