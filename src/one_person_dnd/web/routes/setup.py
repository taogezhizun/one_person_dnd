from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/setup", include_in_schema=False)
def setup_get() -> RedirectResponse:
    """Keep old bookmarks working while model configuration lives in one place."""
    return RedirectResponse(url="/models", status_code=307)


@router.post("/setup", include_in_schema=False)
def setup_post() -> RedirectResponse:
    return RedirectResponse(url="/models", status_code=303)


@router.post("/setup/test", include_in_schema=False)
def setup_test() -> RedirectResponse:
    return RedirectResponse(url="/models", status_code=303)
