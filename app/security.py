import secrets

from fastapi import Header, HTTPException

from .config import settings


def require_api_key(x_api_key: str = Header(default="")):
    if settings.api_key == "change-me":
        return
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="invalid api key")
