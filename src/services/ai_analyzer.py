from google import genai


class GeminiAnalyzer:
    """Uses the official Google GenAI SDK to analyze real estate listing descriptions."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        # Initialize client with your API key explicitly
        self.client = genai.Client(api_key=self.api_key)

    def analyze_description(self, description: str) -> str:
        if not description or not description.strip():
            return "No description provided."

        prompt = (
            "Analyze the following real estate listing description and provide a short summary "
            "(3 bullet points max) highlighting key pros, cons, or hidden details:\n\n"
            f"{description}"
        )

        try:
            # Use gemini-3.7-flash with the standard contents endpoint
            response = self.client.models.generate_content(
                model="gemini-3.7-flash",
                contents=prompt,
            )
            return response.text.strip() if response.text else "No analysis generated."

        except Exception as e:
            print(f"[ERROR] Gemini analysis failed: {e}")
            return "Analysis unavailable."
