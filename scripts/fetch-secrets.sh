#!/bin/bash
# Regenerates .env from Google Cloud Secret Manager (project: immoo-506522).
# Run this instead of hand-editing .env. No credentials file is written to
# disk anymore — the service account JSON is passed as GOOGLE_SERVICE_ACCOUNT_JSON.
# Requires: gcloud auth login (already done once) + secretmanager.secretAccessor.
set -euo pipefail
cd "$(dirname "$0")/.."

fetch() { gcloud secrets versions access latest --secret="$1" --project=immoo-506522; }
fetch_json_compact() { fetch "$1" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)))"; }

cat > .env <<EOF
SCRAPER_API_KEY=$(fetch immo-scraper-api-key)

ZENROWS_API_KEY=$(fetch immo-scraper-zenrows-api-key)

GEMINI_API_KEY=$(fetch immo-scraper-gemini-api-key)

GOOGLE_SHEET_NAME="Immoo Live Listing"

STREAMESTATE_API_KEY=$(fetch immo-scraper-streamestate-api-key)

USE_MOCK=true

GOOGLE_SHEETS_MASTER_TEMPLATE_ID=18dvMh-rbU7dof6EtjKH8PSSoI632qlbQ9_4E_5oSuEE
GOOGLE_DRIVE_STAGING_FOLDER_ID=0ABCJ9B8w13-pUk9PVA

GOOGLE_SERVICE_ACCOUNT_JSON='$(fetch_json_compact immoo-service-account-key)'
EOF
chmod 600 .env

echo "wrote .env (values not printed) — no service_account.json file needed"
