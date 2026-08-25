# IMMOO Scraper Service

FastAPI background worker for the IMMOO real estate pipeline. Managed with `uv`.

## Quickstart

```bash
# 1. Environment setup
cp .env.example .env

# 2. Install dependencies
uv sync

# 3. Run server
uv run uvicorn main:app --reload --port 8000

```

## `.env` Configuration

```env
SCRAPER_API_KEY=sk_live_default_secret_key
ZENROWS_API_KEY=your_zenrows_api_key
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_SERVICE_ACCOUNT_JSON=your_google_credentials
GOOGLE_SHEET_NAME=ADs_list

```

## API Endpoints

* **`GET /api/health`** — Health check & app version.
* **`POST /api/scrape`** — Triggers background scraper task.
* **Docs:** `http://localhost:8000/docs`

## Example Request

```bash
curl -X POST "http://localhost:8000/api/scrape" \
  -H "Authorization: Bearer sk_live_default_secret_key" \
  -H "Content-Type: application/json" \
  -d '{
    "locations": ["77300", "77210"],
    "minPrice": 400000,
    "maxPrice": 550000,
    "minSpace": 80,
    "minRooms": 4,
    "minBedrooms": 3
  }'

```