"""
Ozempic Authentication Module
Simple JWT-based authentication for Ozempic API.
"""

import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration
SECRET_KEY = secrets.token_hex(32)  # Generate secure key
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Admin credential. There is no built-in password: set OZEMPIC_ADMIN_PASSWORD in the
# environment before starting the service. If it is unset the admin account exists but
# no password will authenticate, so the service fails closed.
ADMIN_PASSWORD = os.environ.get("OZEMPIC_ADMIN_PASSWORD", "")

# Simple user database (in production, use a real database)
USERS_DB = {
    "admin": {
        "hashed_password": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
        "role": "admin"
    }
}

security = HTTPBearer()


def create_token(username: str, role: str = "user") -> str:
    """Create a JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get the current authenticated user."""
    token = credentials.credentials
    payload = verify_token(token)
    username = payload.get("sub")
    
    if not username or username not in USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    return {
        "username": username,
        "role": payload.get("role", "user")
    }


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user with username and password."""
    if username not in USERS_DB:
        return None
    
    user = USERS_DB[username]
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    if hashed_password == user["hashed_password"]:
        return {
            "username": username,
            "role": user["role"]
        }
    
    return None


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require admin role for endpoint."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
