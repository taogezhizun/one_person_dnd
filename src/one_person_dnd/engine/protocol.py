from __future__ import annotations

"""Single source of truth for the DM structured-output delimiter protocol.

The DM's raw text is expected to be split into sections marked by these
delimiters (each on its own line). NARRATION/CHOICES/DM_NOTES/MEMORY are
required; STATE_DELTA/THREAD_UPDATES are optional trailing sections.

Every place that needs to render, parse, or validate these delimiters
(prompt_builder, parser, orchestrator, continuity_critic, response_evaluator)
should import the constants from here instead of hardcoding the literal
strings, so a rename or typo fix only has to happen in one place.
"""

NARRATION = "===NARRATION==="
CHOICES = "===CHOICES==="
DM_NOTES = "===DM_NOTES==="
MEMORY = "===MEMORY==="
STATE_DELTA = "===STATE_DELTA==="
THREAD_UPDATES = "===THREAD_UPDATES==="

REQUIRED_DELIMITERS = (NARRATION, CHOICES, DM_NOTES, MEMORY)
OPTIONAL_DELIMITERS = (STATE_DELTA, THREAD_UPDATES)

# Delimiter literal -> DMStructuredResponse field name, used by the parser to
# route each section's lines into the right buffer.
DELIMITER_FIELDS: dict[str, str] = {
    NARRATION: "narration",
    CHOICES: "choices",
    DM_NOTES: "dm_notes",
    MEMORY: "memory_suggestions",
    STATE_DELTA: "state_delta_json",
    THREAD_UPDATES: "thread_updates_json",
}
