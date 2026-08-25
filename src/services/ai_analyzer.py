import json
from google import genai
from google.genai import types

from src.config import Config
from src.domain.models import AIAnalysisResult


class GeminiAnalyzer:
    def __init__(self, api_key: str = Config.GEMINI_API_KEY) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        self.client = genai.Client(api_key=api_key)

    def analyze_listing_text(self, text: str) -> AIAnalysisResult:
        prompt = f"""
        Analyze this French real estate listing description and extract structured JSON:
        1. "location": string (Extract the city or town name, e.g., "Fontainebleau", "Avon", "Paris", "Melun")
        2. "has_garden": boolean (true if a private garden or terrace is available)
        3. "floor": string (e.g., "Ground Floor", "2nd Floor", "Top Floor", or "Unknown")
        4. "flaws_and_drawbacks": list of strings (e.g., ["Street noise", "No elevator", "Renovation needed"])
        5. "highlights": list of strings (e.g., ["Balcony", "Quiet area", "Cellar"])

        Listing Text:
        {text}
        """

        response = self.client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            return AIAnalysisResult()

        return AIAnalysisResult(
            extracted_location=str(data.get("location", "Unknown")),
            has_garden=bool(data.get("has_garden", False)),
            floor=str(data.get("floor", "Unknown")),
            flaws_and_drawbacks=list(data.get("flaws_and_drawbacks", [])),
            highlights=list(data.get("highlights", [])),
        )
