from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from one_person_dnd.web.localization import UnsupportedLocale, language_response, locale_for

router = APIRouter()


@router.post("/locale")
def set_locale(
    request: Request,
    locale: str = Form(...),
    next_path: str = Form("/"),
) -> Response:
    try:
        return language_response(locale=locale, next_path=next_path)
    except UnsupportedLocale:
        return PlainTextResponse(locale_for(request)("errors.unsupported_locale"), status_code=400)
