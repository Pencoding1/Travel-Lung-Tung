import hmac
import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def verify_service_token(api_key: str = Security(api_key_header)):
    expected_key = os.getenv("CRAWLER_API_KEY", "").strip()
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crawler service authentication is not configured",
        )
    if not hmac.compare_digest(api_key or "", expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Forbidden: Invalid Service Token",
        )
