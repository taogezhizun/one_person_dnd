from __future__ import annotations

import json
import sqlite3
from typing import Any

from one_person_dnd.db.repos import plot_threads
from one_person_dnd.domain.state_changes import StateChangePreview
from one_person_dnd.engine.guardrails import GuardrailError


_ALLOWED_STATUS = {"open", "closed"}
_UPDATE_FIELDS = ("title", "status", "priority", "summary", "next_step", "tags")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_int(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception as exc:
        raise GuardrailError(f"{field} 必须是整数") from exc


def _load_updates(delta_json_text: str) -> list[dict[str, Any]]:
    raw = (delta_json_text or "").strip()
    if not raw:
        raise GuardrailError("THREAD_UPDATES 为空")
    if len(raw) > 8000:
        raise GuardrailError("THREAD_UPDATES 过大（>8000 chars）")
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise GuardrailError(f"THREAD_UPDATES JSON 解析失败：{exc}") from exc
    if not isinstance(payload, dict):
        raise GuardrailError("THREAD_UPDATES 必须是 JSON 对象")

    updates = payload.get("updates")
    if not isinstance(updates, list) or not updates:
        raise GuardrailError("THREAD_UPDATES.updates 必须是非空数组")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(updates, start=1):
        if not isinstance(item, dict):
            raise GuardrailError(f"updates[{idx}] 必须是对象")
        update: dict[str, Any] = {}
        if "id" in item:
            thread_id = item.get("id")
            if type(thread_id) is not int or thread_id <= 0:
                raise GuardrailError("id 必须是正整数")
            update["id"] = thread_id
        if "priority" in item:
            priority = _optional_int(item.get("priority"), field="priority")
            if priority is not None:
                update["priority"] = priority
        for field in ("title", "summary", "next_step", "tags"):
            if field in item:
                update[field] = _text(item.get(field))
        if "status" in item:
            status = _text(item.get("status")) or "open"
            if status not in _ALLOWED_STATUS:
                raise GuardrailError("status 必须是 open 或 closed")
            update["status"] = status
        if not any(field in update for field in _UPDATE_FIELDS):
            raise GuardrailError(f"updates[{idx}] 缺少可应用字段")
        if "id" not in update and not update.get("title"):
            raise GuardrailError(f"updates[{idx}] 新建剧情线时必须提供 title")
        normalized.append(update)
    return normalized


def validate_thread_updates_json(delta_json_text: str) -> list[dict[str, Any]]:
    """Validate and normalize a THREAD_UPDATES payload without applying it."""
    return _load_updates(delta_json_text)


def preview_thread_updates_json(delta_json_text: str) -> StateChangePreview:
    try:
        updates = _load_updates(delta_json_text)
    except GuardrailError as exc:
        return StateChangePreview(ok=False, summary="无法预览剧情线更新", lines=[str(exc)])

    lines: list[str] = []
    for update in updates:
        if "id" in update:
            parts: list[str] = []
            if update.get("title"):
                parts.append(f"标题：{update['title']}")
            if "summary" in update:
                parts.append(update["summary"] or "清空概要")
            if "next_step" in update:
                parts.append(f"下一步：{update['next_step'] or '清空'}")
            if "status" in update:
                parts.append("状态：" + ("进行中" if update["status"] == "open" else "已关闭"))
            if "priority" in update:
                parts.append(f"优先级：{update['priority']}")
            if "tags" in update:
                parts.append(f"标签：{update['tags'] or '清空'}")
            lines.append(f"#{update['id']} 更新：" + "；".join(parts))
        else:
            priority = int(update.get("priority") or 0)
            tags = update.get("tags") or ""
            suffix_parts = [f"P{priority}"]
            if tags:
                suffix_parts.append(tags)
            lines.append(f"新建：{update['title']}（{'，'.join(suffix_parts)}）")
    return StateChangePreview(ok=True, summary="将更新剧情线", lines=lines)


def apply_thread_updates_json(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    delta_json_text: str,
) -> list[str]:
    updates = _load_updates(delta_json_text)
    applied: list[str] = []
    for update in updates:
        if "id" in update:
            thread_id = int(update["id"])
            existing = plot_threads.get_thread(conn, session_id=session_id, thread_id=thread_id)
            if existing is None:
                raise GuardrailError(f"未找到剧情线 #{thread_id}")
            status = update.get("status") or existing.get("status") or "open"
            title = update.get("title") or existing.get("title") or f"Thread {thread_id}"
            priority = int(update["priority"]) if "priority" in update else int(existing.get("priority") or 0)
            summary = update["summary"] if "summary" in update else (existing.get("summary") or "")
            next_step = update["next_step"] if "next_step" in update else (existing.get("next_step") or "")
            tags = update["tags"] if "tags" in update else (existing.get("tags") or "")
            plot_threads.update_thread(
                conn,
                thread_id=thread_id,
                session_id=session_id,
                title=title,
                priority=priority,
                summary=summary,
                next_step=next_step,
                tags=tags,
            )
            if status != existing.get("status"):
                plot_threads.set_status(conn, thread_id=thread_id, session_id=session_id, status=status)
            applied.append(f"updated:{thread_id}")
            continue

        status = update.get("status") or "open"
        thread_id = plot_threads.create_thread(
            conn,
            session_id=session_id,
            title=update["title"],
            priority=int(update.get("priority") or 0),
            summary=update.get("summary") or "",
            next_step=update.get("next_step") or "",
            tags=update.get("tags") or "",
        )
        if status != "open":
            plot_threads.set_status(conn, thread_id=thread_id, session_id=session_id, status=status)
        applied.append(f"created:{thread_id}")
    return applied
