import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


def verify_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> str:
    scr_key = os.environ.get("SCRAPER_API_KEY", "sk_live_default_secret_key")

    # Extract the actual bearer token string
    token = credentials.credentials

    # Validate against expected secret key
    if not secrets.compare_digest(token, scr_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    # Return the raw token string so routes can consume it if needed
    return token
