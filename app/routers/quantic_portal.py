from fastapi import APIRouter

from ..quantic_portal_status import build_portal_status


router = APIRouter(prefix="/quantic/portal", tags=["quantic-portal"])


@router.get("/status")
def quantic_portal_status():
    return build_portal_status()
