from __future__ import annotations

# How many recent dialogue turns to include in the LLM prompt as conversation history.
HISTORY_TURNS_FOR_PROMPT = 6

# How many story journal entries to include in the LLM prompt as medium-term memory.
STORY_JOURNAL_FOR_PROMPT = 12

# Soft character budget for assembled ContextPack blocks included in the prompt.
CONTEXT_CHARS_FOR_PROMPT = 12000
