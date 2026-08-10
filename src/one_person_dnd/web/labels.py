"""Stable compatibility maps for coded display labels used in the game UI.

The bilingual copy lives only in ``web.localization.catalogs.diagnostics``.
This module derives the existing code-to-Chinese maps from that catalog so
older Python callers, standalone Jinja rendering, and browser serialization
keep the same public API without maintaining a second copy of the wording.

These maps were originally introduced to replace hand-duplicated labels across
the Jinja
partials (`templates/partials/chat_turn.html`, `templates/partials/turn_diagnostics.html`)
and the streaming renderer (`static/js/app.js`). Historical turns are rendered
server-side by Jinja while new turns are rendered client-side by JS as they
stream in, so a stale copy in either place would silently show a raw code (or,
worse, a different translation) instead of the intended label.

Python exposes the derived maps to both renderers:
  - Jinja templates get them as globals (see `web/routes/common.py`), under the
    same variable names the templates already used (`action_type_labels`, ...).
  - `app.js` gets them serialized as JSON, injected via `base.html` into a
    `<script id="dnd-labels" type="application/json">` element that loads
    before `app.js` runs.

Edit diagnostic wording only in ``web/localization/catalogs/diagnostics.py``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from one_person_dnd.web.localization.catalogs.diagnostics import MESSAGES as DIAGNOSTIC_MESSAGES

if TYPE_CHECKING:
    from one_person_dnd.web.localization import Localizer


def _default_labels(prefix: str) -> dict[str, str]:
    return {
        key.removeprefix(prefix): pair[0]
        for key, pair in DIAGNOSTIC_MESSAGES.items()
        if key.startswith(prefix)
    }


ACTION_TYPE_LABELS: dict[str, str] = _default_labels("action.type.")
ACTION_SIGNAL_LABELS: dict[str, str] = _default_labels("action.signal.")
ACTION_WARNING_LABELS: dict[str, str] = _default_labels("action.warning.")
CRITIC_WARNING_LABELS: dict[str, str] = _default_labels("critic.")
RESPONSE_WARNING_LABELS: dict[str, str] = _default_labels("response.")

# Frozen adjudication records predate UI localization and persist their intent
# as a canonical Chinese domain phrase. Keep this compatibility map at the
# presentation boundary so switching the interface never mutates old saves.
ADJUDICATION_INTENT_CODES: dict[str, str] = {
    label: code
    for code, label in _default_labels("adjudication.intent.").items()
}

ADJUDICATION_INTENT_LABELS: dict[str, str] = {
    intent: intent for intent in ADJUDICATION_INTENT_CODES
}


def all_label_maps() -> dict[str, dict[str, str]]:
    """Return display maps keyed for JSON serialization to the client."""
    return {
        "action_type": ACTION_TYPE_LABELS,
        "action_signal": ACTION_SIGNAL_LABELS,
        "action_warning": ACTION_WARNING_LABELS,
        "critic_warning": CRITIC_WARNING_LABELS,
        "response_warning": RESPONSE_WARNING_LABELS,
        "adjudication_intent": ADJUDICATION_INTENT_LABELS,
    }


def localized_label_maps(localizer: "Localizer") -> dict[str, dict[str, str]]:
    """Project the stable diagnostic codes through the request localizer."""
    return {
        "action_type": {
            code: localizer(f"action.type.{code}")
            for code in ACTION_TYPE_LABELS
        },
        "action_signal": {
            code: localizer(f"action.signal.{code}")
            for code in ACTION_SIGNAL_LABELS
        },
        "action_warning": {
            code: localizer(f"action.warning.{code}")
            for code in ACTION_WARNING_LABELS
        },
        "critic_warning": {
            code: localizer(f"critic.{code}")
            for code in CRITIC_WARNING_LABELS
        },
        "response_warning": {
            code: localizer(f"response.{code}")
            for code in RESPONSE_WARNING_LABELS
        },
        "adjudication_intent": {
            intent: localizer(f"adjudication.intent.{code}")
            for intent, code in ADJUDICATION_INTENT_CODES.items()
        },
    }


def register_jinja_globals(env: Any) -> None:
    """Register display-label maps (plus their JSON form) on a Jinja Environment.

    Templates keep using the same variable names they used to `{% set %}`
    locally (`action_type_labels`, `action_signal_labels`,
    `action_warning_labels`, `critic_warning_labels`, `response_warning_labels`),
    so call sites like `action_type_labels.get(code, code)` are unchanged.
    """
    env.globals["action_type_labels"] = ACTION_TYPE_LABELS
    env.globals["action_signal_labels"] = ACTION_SIGNAL_LABELS
    env.globals["action_warning_labels"] = ACTION_WARNING_LABELS
    env.globals["critic_warning_labels"] = CRITIC_WARNING_LABELS
    env.globals["response_warning_labels"] = RESPONSE_WARNING_LABELS
    env.globals["adjudication_intent_labels"] = ADJUDICATION_INTENT_LABELS
    env.globals["label_maps_json"] = json.dumps(all_label_maps(), ensure_ascii=False)
    # Standalone template tests do not pass through the request context processor.
    # They intentionally render the default Chinese UI.
    from one_person_dnd.web.localization import Localizer

    env.globals["t"] = Localizer()
