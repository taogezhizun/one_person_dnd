"""Canonical, replayable ability-check adjudication.

Callers use one entry point: ``ActionAdjudicator.adjudicate``.  The package
deliberately does not expose separate plan/roll methods, so a caller cannot see
a die result before choosing the ability, DC, or roll mode.
"""

from one_person_dnd.adjudication.core import (
    POLICY_VERSION,
    ActionAdjudicator,
    AdjudicationRecord,
    AdjudicationRequest,
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
    AttemptConflict,
    CheckResolution,
    InvalidAdjudicationInput,
    SequenceRoller,
    SystemRoller,
)

__all__ = [
    "POLICY_VERSION",
    "ActionAdjudicator",
    "AdjudicationRecord",
    "AdjudicationRequest",
    "AdjudicationStoreBusy",
    "AdjudicationStoreCorrupt",
    "AttemptConflict",
    "CheckResolution",
    "InvalidAdjudicationInput",
    "SequenceRoller",
    "SystemRoller",
]
