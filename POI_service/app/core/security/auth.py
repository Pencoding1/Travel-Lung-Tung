import os
import jwt
import logging

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)
load_dotenv()


# Pull dynamically, with a fallback just in case the .env doesn't mount properly
JWT_SECRET = os.getenv("JWT_SECRET", None) 
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

if JWT_SECRET is None:
    logger.critical("FATAL: JWT_SECRET environment variable is not set. Shutting down.")
    raise RuntimeError("Server configuration invalid: Missing JWT_SECRET.")


# HTTPBearer automatically looks for the "Authorization: Bearer <token>" header
# If the header is missing, it automatically throws a 403 Forbidden!
security_scheme = HTTPBearer()

class TokenPayload(BaseModel):
    """The expected structure of your JWT payload."""
    sub: str          # Usually the User ID or Service ID
    role: str = "user" # Example: to restrict ingestion to 'admin' or 'system'

def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> TokenPayload:
    """
    The dependency guard. Decodes the token, checks expiration, 
    and returns the payload if valid.
    """
    token = credentials.credentials

    try:
        decoded_payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]) # type: ignore
        return TokenPayload(**decoded_payload)
        
    except jwt.ExpiredSignatureError:
        logger.warning("Rejected request: JWT Token expired.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please authenticate again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Rejected request: Invalid JWT Token - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.warning(f"Rejected request: Internal Error - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server Internal Error.",
            headers={"WWW-Authenticate": "Bearer"},
        )