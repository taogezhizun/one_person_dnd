from __future__ import annotations

from collections.abc import Mapping

from .common import MESSAGES as COMMON_MESSAGES
from .diagnostics import MESSAGES as DIAGNOSTIC_MESSAGES
from .game import MESSAGES as GAME_MESSAGES
from .management import MESSAGES as MANAGEMENT_MESSAGES
from .onboarding import MESSAGES as ONBOARDING_MESSAGES


def load_messages() -> Mapping[str, tuple[str, str]]:
    """Load and validate the packaged message domains."""
    merged: dict[str, tuple[str, str]] = {}
    for domain in (
        COMMON_MESSAGES,
        DIAGNOSTIC_MESSAGES,
        GAME_MESSAGES,
        ONBOARDING_MESSAGES,
        MANAGEMENT_MESSAGES,
    ):
        for key, value in domain.items():
            if key in merged:
                raise ValueError(f"duplicate localization key: {key}")
            merged[key] = value
    return merged


__all__ = ["load_messages"]
