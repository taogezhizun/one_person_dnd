from __future__ import annotations

import random
import re
from typing import TypedDict


_ROLL_TOKEN_RE = re.compile(r"(?i)\b(\d{0,3})d(\d{1,4})([+-]\d{1,5})?\b")
_FULL_EXPR_RE = re.compile(r"(?i)^\s*(\d{0,3})d(\d{1,4})([+-]\d{1,5})?\s*$")


class DiceEvent(TypedDict):
    expr: str
    count: int
    sides: int
    modifier: int
    rolls: list[int]
    total: int


def _normalize_expr(*, count: int, sides: int, modifier: int) -> str:
    base = f"{count}d{sides}"
    if modifier > 0:
        return f"{base}+{modifier}"
    if modifier < 0:
        return f"{base}{modifier}"
    return base


def parse_roll_expr(expr: str) -> tuple[int, int, int]:
    """
    Parse NdM(+/-)K expression.
    Examples: d20, 1d20+5, 2d6-1
    """
    m = _FULL_EXPR_RE.match((expr or "").strip())
    if not m:
        raise ValueError("掷骰表达式格式无效（示例：d20 / 1d20+5 / 2d6-1）")

    count_raw, sides_raw, mod_raw = m.group(1), m.group(2), m.group(3)
    count = int(count_raw) if count_raw else 1
    sides = int(sides_raw)
    modifier = int(mod_raw) if mod_raw else 0

    if count < 1 or count > 100:
        raise ValueError("骰子个数必须在 1~100")
    if sides < 2 or sides > 1000:
        raise ValueError("骰子面数必须在 2~1000")
    if modifier < -100000 or modifier > 100000:
        raise ValueError("修正值超出范围")
    return count, sides, modifier


def roll_expr(expr: str) -> DiceEvent:
    count, sides, modifier = parse_roll_expr(expr)
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    normalized = _normalize_expr(count=count, sides=sides, modifier=modifier)
    return {
        "expr": normalized,
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "rolls": rolls,
        "total": total,
    }


def roll_events_from_text(text: str, *, max_rolls: int = 5) -> list[DiceEvent]:
    events: list[DiceEvent] = []
    for m in _ROLL_TOKEN_RE.finditer(text or ""):
        token = m.group(0)
        try:
            events.append(roll_expr(token))
        except ValueError:
            continue
        if len(events) >= max_rolls:
            break
    return events


def format_events_for_prompt(events: list[DiceEvent]) -> str:
    lines: list[str] = []
    for e in events:
        rolls = ", ".join(str(x) for x in e["rolls"])
        mod = e["modifier"]
        mod_txt = f"{mod:+d}" if mod else "+0"
        lines.append(f"- {e['expr']} => [{rolls}] {mod_txt} = {e['total']}")
    return "\n".join(lines).strip()

