from __future__ import annotations

from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse

from one_person_dnd.web.localization import Localizer


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _rejected_response(scope) -> PlainTextResponse:
    candidate = scope.get("state", {}).get("ui")
    ui = candidate if isinstance(candidate, Localizer) else Localizer()
    return PlainTextResponse(
        ui("errors.cross_site_write"),
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )


def _origin_parts(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            return None
        if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.casefold(), parsed.hostname.casefold(), port


class UnsafeWriteProtectionMiddleware:
    """Reject browser writes whose Origin does not match the request origin."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"].upper() in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        fetch_site = headers.get(b"sec-fetch-site", b"").decode("latin-1").strip().casefold()
        if fetch_site == "cross-site":
            response = _rejected_response(scope)
            await response(scope, receive, send)
            return

        raw_origin = headers.get(b"origin")
        raw_host = headers.get(b"host")
        if raw_origin is not None:
            origin = _origin_parts(raw_origin.decode("latin-1"))
            request_origin = _origin_parts(
                f"{scope.get('scheme', 'http')}://{raw_host.decode('latin-1') if raw_host else ''}"
            )
            if origin is None or origin != request_origin:
                response = _rejected_response(scope)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
