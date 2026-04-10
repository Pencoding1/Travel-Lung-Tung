from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config.settings import CrawlerSetting

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_service_token(api_key: str = Security(api_key_header)):
    if api_key != "test":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Forbidden: Invalid Service Token",
        )