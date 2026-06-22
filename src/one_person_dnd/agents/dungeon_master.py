from __future__ import annotations

from one_person_dnd.context.pack import ContextPack
from one_person_dnd.engine.orchestrator import ensure_dm_protocol_output
from one_person_dnd.engine.prompt_builder import build_dm_messages_from_context_pack
from one_person_dnd.llm import ChatMessage


class DungeonMasterAgent:
    def __init__(self, client) -> None:
        self._client = client

    def build_messages(
        self,
        pack: ContextPack,
        *,
        player_text: str,
        recent_messages: list[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        messages = build_dm_messages_from_context_pack(pack)
        messages.extend(recent_messages or [])
        messages.append(ChatMessage(role="user", content=player_text))
        return messages

    def run_non_streaming(self, messages: list[ChatMessage], *, repair: bool = True) -> tuple[str, bool]:
        dm_raw = self._client.chat(messages)
        if repair:
            return ensure_dm_protocol_output(self._client, messages, dm_raw, max_retries=1)
        return dm_raw, False

    def repair_non_streaming(self, messages: list[ChatMessage], repair_prompt: str) -> str:
        return self._client.chat(messages + [ChatMessage(role="user", content=repair_prompt)])
