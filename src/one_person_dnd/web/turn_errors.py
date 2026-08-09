from __future__ import annotations

from dataclasses import dataclass

from one_person_dnd.adjudication import (
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
    AttemptConflict,
    InvalidAdjudicationInput,
)


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


def public_turn_error(exc: Exception) -> PublicTurnError:
    """Map internal adjudication failures to stable, non-sensitive UI messages."""
    if isinstance(exc, InvalidAdjudicationInput):
        return PublicTurnError(422, "行动数据无效，请检查当前冒险和行动内容后重新发送。")
    if isinstance(exc, AttemptConflict):
        return PublicTurnError(409, "这次行动与已保存的尝试发生冲突，请保留草稿并重新发送。")
    if isinstance(exc, AdjudicationStoreBusy):
        return PublicTurnError(503, "本地存档正忙，请稍后使用同一行动重试。", retry_after="1")
    if isinstance(exc, AdjudicationStoreCorrupt):
        return PublicTurnError(409, "这次行动已保存的检定无法读取，请先恢复存档或查看诊断。")
    return PublicTurnError(500, "回合处理失败，请稍后重试。")
