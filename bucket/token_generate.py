import jwt
import os
# Best practice: Import only what you need to avoid the 'double datetime' confusion
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("JWT_SECRET", "20112005@Pen215")
ALGO = os.getenv("JWT_ALGORITHM", "HS256")

def create_admin_token(user_id: str, days_valid: int = 30):
    """Forges a valid JWT for Travel Lung Tung."""
    
    # Using the specific imports from above
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=days_valid)
    
    payload = {
        "sub": user_id,
        "role": "admin",
        "exp": int(expiry.timestamp()) # exp should be a Unix timestamp (integer)
    }
    
    token = jwt.encode(payload, SECRET, algorithm=ALGO)
    return token
