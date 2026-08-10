"""Request-scoped localization for the Web UI.

The public seam is intentionally small: middleware binds one immutable
``Localizer`` to each request, callers retrieve it with ``locale_for()``, and
Jinja receives the same object through ``localization_context()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Literal
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .catalogs import load_messages

LocaleCode = Literal["zh-CN", "en"]

DEFAULT_LOCALE: LocaleCode = "zh-CN"
SUPPORTED_LOCALES: tuple[LocaleCode, ...] = ("zh-CN", "en")
LOCALE_COOKIE = "opd_locale"
LOCALE_HEADER = "x-dnd-ui-locale"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_MESSAGES = dict(load_messages())


class CatalogValidationError(RuntimeError):
    pass


class MissingMessageError(KeyError):
    pass


class MessageFormatError(ValueError):
    pass


class UnsupportedLocale(ValueError):
    pass


def _placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text))


def _validate_catalog() -> None:
    for key, pair in _MESSAGES.items():
        if not isinstance(key, str) or not key.strip():
            raise CatalogValidationError("localization keys must be non-empty strings")
        if not isinstance(pair, tuple) or len(pair) != 2 or not all(isinstance(value, str) for value in pair):
            raise CatalogValidationError(f"{key}: expected a (zh-CN, en) text pair")
        if _placeholders(pair[0]) != _placeholders(pair[1]):
            raise CatalogValidationError(f"{key}: locale placeholders do not match")


_validate_catalog()


def normalize_locale(value: str | None, *, strict: bool = False) -> LocaleCode:
    normalized = (value or "").strip().replace("_", "-").casefold()
    if normalized in {"zh", "zh-cn", "zh-hans", "zh-hans-cn"}:
        return "zh-CN"
    if normalized in {"en", "en-us", "en-gb"}:
        return "en"
    if strict:
        raise UnsupportedLocale(value or "")
    return DEFAULT_LOCALE


@dataclass(frozen=True, slots=True)
class Localizer:
    locale: LocaleCode = DEFAULT_LOCALE

    @property
    def html_lang(self) -> str:
        return self.locale

    def __call__(self, key: str, /, **values: object) -> str:
        pair = _MESSAGES.get(key)
        if pair is None:
            raise MissingMessageError(key)
        template = pair[0] if self.locale == "zh-CN" else pair[1]
        required = _placeholders(template)
        missing = required.difference(values)
        if missing:
            names = ", ".join(sorted(missing))
            raise MessageFormatError(f"{key}: missing values: {names}")
        return _PLACEHOLDER_RE.sub(lambda match: str(values[match.group(1)]), template)

    def client_catalog(self) -> dict[str, str]:
        index = 0 if self.locale == "zh-CN" else 1
        return {key: pair[index] for key, pair in _MESSAGES.items()}


_DEFAULT_LOCALIZER = Localizer()


def locale_for(request: object | None = None) -> Localizer:
    """Return the immutable localizer bound to a request, or Chinese by default."""
    try:
        candidate = getattr(getattr(request, "state"), "ui")
    except (AttributeError, TypeError):
        return _DEFAULT_LOCALIZER
    return candidate if isinstance(candidate, Localizer) else _DEFAULT_LOCALIZER


def localization_context(request: object) -> dict[str, Any]:
    """Jinja context processor; all request-specific values stay out of env globals."""
    ui = locale_for(request)
    # Import lazily so labels can use the default Localizer in standalone Jinja tests.
    from one_person_dnd.web.labels import localized_label_maps

    labels = localized_label_maps(ui)
    return {
        "ui": ui,
        "t": ui,
        "locale": ui.locale,
        "html_lang": ui.html_lang,
        "other_locale": "en" if ui.locale == "zh-CN" else "zh-CN",
        "other_locale_label": ui(
            "locale.switch_to_english" if ui.locale == "zh-CN" else "locale.switch_to_chinese"
        ),
        "client_catalog": ui.client_catalog(),
        "label_maps": labels,
        "action_type_labels": labels["action_type"],
        "action_signal_labels": labels["action_signal"],
        "action_warning_labels": labels["action_warning"],
        "critic_warning_labels": labels["critic_warning"],
        "response_warning_labels": labels["response_warning"],
        "adjudication_intent_labels": labels["adjudication_intent"],
    }


def safe_next_path(value: str | None) -> str:
    candidate = (value or "").strip()
    parsed = urlsplit(candidate)
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or parsed.scheme
        or parsed.netloc
    ):
        return "/"
    return candidate


def language_response(*, locale: str, next_path: str | None) -> RedirectResponse:
    selected = normalize_locale(locale, strict=True)
    response = RedirectResponse(url=safe_next_path(next_path), status_code=303)
    response.set_cookie(
        LOCALE_COOKIE,
        selected,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


def _header_value(scope: Scope, name: str) -> str | None:
    encoded = name.encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == encoded:
            return value.decode("latin-1")
    return None


def _request_locale(scope: Scope) -> LocaleCode:
    header_locale = _header_value(scope, LOCALE_HEADER)
    if header_locale is not None and header_locale.strip():
        return normalize_locale(header_locale)

    cookie_header = _header_value(scope, "cookie")
    if cookie_header:
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except Exception:
            cookies = SimpleCookie()
        morsel = cookies.get(LOCALE_COOKIE)
        if morsel is not None:
            return normalize_locale(morsel.value)
    return DEFAULT_LOCALE


class LocaleMiddleware:
    """Bind locale for the complete ASGI response lifetime, including SSE streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or str(scope.get("path") or "").startswith("/static/"):
            await self.app(scope, receive, send)
            return

        locale = _request_locale(scope)
        scope.setdefault("state", {})["ui"] = Localizer(locale)

        async def send_localized(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Language"] = locale
                existing_vary = headers.get("Vary")
                vary_items = [item.strip() for item in (existing_vary or "").split(",") if item.strip()]
                for item in ("Cookie", "X-DND-UI-Locale"):
                    if item.casefold() not in {value.casefold() for value in vary_items}:
                        vary_items.append(item)
                headers["Vary"] = ", ".join(vary_items)
            await send(message)

        await self.app(scope, receive, send_localized)


__all__ = [
    "CatalogValidationError",
    "DEFAULT_LOCALE",
    "LOCALE_COOKIE",
    "LOCALE_HEADER",
    "Localizer",
    "LocaleMiddleware",
    "MessageFormatError",
    "MissingMessageError",
    "SUPPORTED_LOCALES",
    "UnsupportedLocale",
    "language_response",
    "locale_for",
    "localization_context",
    "normalize_locale",
    "safe_next_path",
]
