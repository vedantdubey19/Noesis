from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_auth_header(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization or authorization != f"Bearer {settings.api_auth_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Authorization header",
        )
