from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from one_person_dnd.config import LLMConfig, MemoryConfig
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import (
    sessions,
    state_change_requests,
    story_journal,
    summaries,
    turn_logs,
)
from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.engine.dice import DiceEvent
from one_person_dnd.engine.parser import DMStructuredResponse
from one_person_dnd.llm import ChatMessage, create_llm_client

logger = logging.getLogger("one_person_dnd.turn")

_REQUIRED_PROTOCOL_DELIMS = (
    "===NARRATION===",
    "===CHOICES===",
    "===DM_NOTES===",
    "===MEMORY===",
)


def _has_required_protocol_delims(text: str) -> bool:
    t = text or ""
    return all(d in t for d in _REQUIRED_PROTOCOL_DELIMS)


def _build_protocol_repair_prompt(raw: str) -> str:
    return (
        "你刚才的回复未严格按分隔符协议输出。请在不改变事实/剧情内容的前提下，将其“重新排版”为严格协议格式。\n"
        "要求：\n"
        "1) 必须包含并且仅包含这些分隔符段落（分隔符单独占一行，大小写一致）：\n"
        "===NARRATION===\n"
        "===CHOICES===\n"
        "===DM_NOTES===\n"
        "===MEMORY===\n"
        "可选（若确实需要）：===STATE_DELTA=== 与 ===THREAD_UPDATES===，内容为 JSON 对象。\n"
        "2) 禁止输出任何分隔符之外的标题/前缀/解释。\n"
        "3) CHOICES 段必须给出 3-6 条，以 - 开头，每条一行。\n"
        "\n"
        "【原始输出】\n"
        f"{(raw or '').strip()}\n"
    )


def ensure_dm_protocol_output(
    client,
    messages: list[ChatMessage],
    dm_raw: str,
    *,
    max_retries: int = 1,
) -> tuple[str, bool]:
    """
    Ensure DM output follows the delimiter protocol. If not, ask the model to reformat once.
    Returns: (final_text, repaired?)
    """
    if _has_required_protocol_delims(dm_raw):
        return dm_raw, False

    last = dm_raw
    for attempt in range(max_retries):
        repair = _build_protocol_repair_prompt(last)
        logger.warning(
            "dm_protocol_missing attempt=%s raw_len=%s",
            attempt + 1,
            len((last or "").strip()),
        )
        last = client.chat(messages + [ChatMessage(role="user", content=repair)])
        if _has_required_protocol_delims(last):
            return last, True
    return last, True


def chat_dm_with_protocol_retry(client, messages: list[ChatMessage], *, max_retries: int = 1) -> tuple[str, bool]:
    dm_raw = client.chat(messages)
    return ensure_dm_protocol_output(client, messages, dm_raw, max_retries=max_retries)


@dataclass(frozen=True)
class TurnResult:
    turn_index: int
    dm_raw_text: str
    dm: DMStructuredResponse
    recalled_world: list[dict]
    dice_events: list[DiceEvent]
    recalled_context: list[dict] = field(default_factory=list)
    action_assessment: ActionAssessment | None = None
    critic_warnings: list[str] = field(default_factory=list)
    response_warnings: list[str] = field(default_factory=list)


def _next_turn_index(conn: sqlite3.Connection, session_id: int) -> int:
    return turn_logs.get_next_turn_index(conn, session_id)


def _get_session_scene_id(conn: sqlite3.Connection, session_id: int) -> str:
    return sessions.get_session_scene_id(conn, session_id)


def persist_turn(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    player_text: str,
    dm_raw: str,
    dm_struct: DMStructuredResponse,
    recalled_world: list[dict],
    recalled_context: list[dict] | None = None,
    dice_events: list[DiceEvent] | None = None,
) -> TurnResult:
    """
    Persist turn logs, story journal, pending change requests, and rollup summaries.
    Caller is responsible for committing.
    """
    turn_index = _next_turn_index(conn, session_id)
    safe_dice_events = list(dice_events or [])
    turn_logs.insert_turn_log(
        conn,
        session_id=session_id,
        turn_index=turn_index,
        player_text=player_text,
        dm_text=dm_raw,
        dice_events_json=json.dumps(safe_dice_events, ensure_ascii=False),
    )

    if (dm_struct.state_delta_json or "").strip():
        state_change_requests.create_request(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            kind="state_delta",
            delta_json_text=(dm_struct.state_delta_json or "").strip(),
        )
    if (dm_struct.thread_updates_json or "").strip():
        state_change_requests.create_request(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            kind="thread_updates",
            delta_json_text=(dm_struct.thread_updates_json or "").strip(),
        )

    mem = (dm_struct.memory_suggestions or "").strip()
    if mem:
        scene_id = _get_session_scene_id(conn, session_id)
        story_journal.insert_story_journal_entry(
            conn, session_id=session_id, scene_id=scene_id, summary=mem, turn_index=turn_index
        )

    sessions.touch_last_played(conn, session_id=session_id)
    _maybe_rollup_summaries(conn, session_id=session_id, current_turn_index=turn_index)
    return TurnResult(
        turn_index=turn_index,
        dm_raw_text=dm_raw,
        dm=dm_struct,
        recalled_world=recalled_world,
        dice_events=safe_dice_events,
        recalled_context=list(recalled_context or []),
    )


def run_turn(
    *,
    db_path: Path,
    llm_cfg: LLMConfig,
    campaign_id: int,
    session_id: int,
    player_text: str,
    state_block: str,
    tags: list[str] | None = None,
    memory_cfg: MemoryConfig | None = None,
) -> TurnResult:
    """Compatibility entrypoint; turn semantics live in agents.TurnPipeline."""
    from one_person_dnd.agents.pipeline import TurnPipeline
    from one_person_dnd.domain.actions import PlayerAction

    conn = get_connection(db_path)
    try:
        memory_cfg = memory_cfg or MemoryConfig()
        client = create_llm_client(llm_cfg)
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text=player_text,
            manual_tags=list(tags or []),
            extra_context=(state_block or "").strip(),
        )
        result = TurnPipeline(dm_client=client).run_non_streaming(
            conn,
            action=action,
            memory_cfg=memory_cfg,
            state_block=(state_block or "").strip(),
        )
        logger.info(
            "turn_done legacy_entry session=%s turn=%s",
            session_id,
            result.turn_index,
        )
        return result
    finally:
        conn.close()


def _truncate(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _maybe_rollup_summaries(conn: sqlite3.Connection, *, session_id: int, current_turn_index: int) -> None:
    """
    MVP rollup strategy:
    - Keep recent buffer of journal entries unsummarized.
    - When enough unsummarized entries accumulate, create a chapter summary.
    - When enough chapter summaries exist, (re)generate campaign summary.
    """
    RECENT_BUFFER = 12
    CHAPTER_CHUNK = 20
    CHAPTER_MAX_CHARS = 1200
    CAMPAIGN_MAX_CHARS = 1500
    CAMPAIGN_REGEN_CHAPTERS = 3

    progress_end = summaries.get_chapter_rollup_progress(conn, session_id=session_id)
    start_turn = progress_end + 1
    end_limit = max(-1, current_turn_index - RECENT_BUFFER)
    if end_limit < start_turn:
        return

    # Find the next chunk end by scanning available journal entries.
    rows = conn.execute(
        """
        SELECT turn_index, summary
        FROM story_journal_entries
        WHERE session_id = ? AND turn_index IS NOT NULL AND turn_index BETWEEN ? AND ?
        ORDER BY turn_index ASC, id ASC
        """,
        (session_id, start_turn, end_limit),
    ).fetchall()
    if len(rows) < CHAPTER_CHUNK:
        return

    chunk_rows = rows[:CHAPTER_CHUNK]
    chunk_start = int(chunk_rows[0]["turn_index"])
    chunk_end = int(chunk_rows[-1]["turn_index"])
    lines = []
    for r in chunk_rows:
        s = (r["summary"] or "").strip()
        if s:
            lines.append(s)
    chapter_text = _truncate("\n".join(lines), CHAPTER_MAX_CHARS) or "（空）"
    summaries.insert_summary(
        conn,
        session_id=session_id,
        level="chapter",
        start_turn=chunk_start,
        end_turn=chunk_end,
        summary=chapter_text,
    )

    # Regenerate campaign summary from all chapter summaries (deterministic).
    chapters = summaries.list_chapter_summaries(conn, session_id=session_id, limit=200)
    if len(chapters) < CAMPAIGN_REGEN_CHAPTERS:
        return
    merged = "\n\n".join([f"[{c['start_turn']}-{c['end_turn']}]\n{c['summary']}" for c in chapters]).strip()
    campaign_text = _truncate(merged, CAMPAIGN_MAX_CHARS) or "（空）"
    latest_end = max(int(c["end_turn"]) for c in chapters)
    summaries.delete_campaign_summaries(conn, session_id=session_id)
    summaries.insert_summary(
        conn,
        session_id=session_id,
        level="campaign",
        start_turn=0,
        end_turn=latest_end,
        summary=campaign_text,
    )
