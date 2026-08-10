from __future__ import annotations

from dataclasses import dataclass

from one_person_dnd.adjudication import (
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
    AttemptConflict,
    InvalidAdjudicationInput,
)
from one_person_dnd.web.localization import Localizer, locale_for


TURN_DOMAIN_ERRORS = (
    InvalidAdjudicationInput,
    AttemptConflict,
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
)


@dataclass(frozen=True)
class PublicTurnError:
    status_code: int
    message: str
    retry_after: str | None = None


def public_turn_error(exc: Exception, *, ui: Localizer | None = None) -> PublicTurnError:
    """Map internal adjudication failures to stable, non-sensitive UI messages."""
    translate = ui or locale_for()
    if isinstance(exc, InvalidAdjudicationInput):
        return PublicTurnError(422, translate("game.error.invalid_action"))
    if isinstance(exc, AttemptConflict):
        return PublicTurnError(409, translate("game.error.attempt_conflict"))
    if isinstance(exc, AdjudicationStoreBusy):
        return PublicTurnError(503, translate("game.error.store_busy"), retry_after="1")
    if isinstance(exc, AdjudicationStoreCorrupt):
        return PublicTurnError(409, translate("game.error.store_corrupt"))
    return PublicTurnError(500, translate("game.error.turn_failed"))
