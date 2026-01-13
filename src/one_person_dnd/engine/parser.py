from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DMStructuredResponse:
    narration: str
    choices: list[str]
    dm_notes: str
    memory_suggestions: str
    state_delta_json: str = ""
    thread_updates_json: str = ""


def parse_dm_text(text: str) -> DMStructuredResponse:
    """
    Best-effort parsing for the 4 required sections.
    Prefer strict delimiter protocol:
      ===NARRATION=== / ===CHOICES=== / ===DM_NOTES=== / ===MEMORY===
    If parsing fails, put everything into narration.
    """
    t = (text or "").strip()
    if not t:
        return DMStructuredResponse(narration="", choices=[], dm_notes="", memory_suggestions="")

    def _parse_by_delimiters(src: str) -> DMStructuredResponse | None:
        lines = src.splitlines()
        keys = {
            "===NARRATION===": "narration",
            "===CHOICES===": "choices",
            "===DM_NOTES===": "dm_notes",
            "===MEMORY===": "memory_suggestions",
            "===STATE_DELTA===": "state_delta_json",
            "===THREAD_UPDATES===": "thread_updates_json",
        }
        current: str | None = None
        buf: dict[str, list[str]] = {v: [] for v in keys.values()}

        found_any = False
        for raw in lines:
            line = raw.rstrip("\n")
            if line.strip() in keys:
                current = keys[line.strip()]
                found_any = True
                continue
            if current is None:
                # Ignore any preface text; models sometimes add it.
                continue
            buf[current].append(line)

        if not found_any:
            return None

        narration = "\n".join(buf["narration"]).strip()
        choices_block = "\n".join(buf["choices"]).strip()
        dm_notes = "\n".join(buf["dm_notes"]).strip()
        memory_suggestions = "\n".join(buf["memory_suggestions"]).strip()
        state_delta_json = "\n".join(buf["state_delta_json"]).strip()
        thread_updates_json = "\n".join(buf["thread_updates_json"]).strip()

        choices: list[str] = []
        for line in choices_block.splitlines():
            s = line.strip()
            if not s:
                continue
            # Accept "- xxx" or "1. xxx"
            if s.startswith("-"):
                s = s.lstrip("-").strip()
            # remove leading numbering like "1." / "1)"
            s2 = s
            if len(s2) >= 2 and s2[0].isdigit():
                # naive trim
                s2 = s2.lstrip("0123456789").lstrip(".").lstrip(")").strip()
            s = s2 or s
            if s:
                choices.append(s)

        return DMStructuredResponse(
            narration=narration or "",
            choices=choices,
            dm_notes=dm_notes or "",
            memory_suggestions=memory_suggestions or "",
            state_delta_json=state_delta_json or "",
            thread_updates_json=thread_updates_json or "",
        )

    parsed = _parse_by_delimiters(t)
    if parsed is not None:
        return parsed

    # Fallback: lightweight heuristics for legacy headings.
    lower = t.lower()
    if "choices" not in lower and "选项" not in t and "dm_notes" not in lower and "备注" not in t:
        return DMStructuredResponse(narration=t, choices=[], dm_notes="", memory_suggestions="")

    def _split_by_markers(src: str) -> dict[str, str]:
        markers = [
            ("narration", ["叙事", "narration"]),
            ("choices", ["choices", "可选行动", "选项"]),
            ("dm_notes", ["dm_notes", "dm notes", "dm备注", "备注"]),
            ("memory_suggestions", ["memory_suggestions", "memory suggestions", "建议写入", "剧情摘要要点"]),
        ]
        # Find first occurrence of any marker line start.
        positions: list[tuple[int, str]] = []
        for key, keys in markers:
            for k in keys:
                idx = src.lower().find(k.lower())
                if idx != -1:
                    positions.append((idx, key))
                    break
        positions.sort(key=lambda x: x[0])
        if not positions:
            return {}

        chunks: dict[str, str] = {}
        for i, (pos, key) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(src)
            chunks[key] = src[pos:end].strip()
        return chunks

    chunks = _split_by_markers(t)

    narration = chunks.get("narration", t).strip()
    choices_block = chunks.get("choices", "").strip()
    dm_notes = chunks.get("dm_notes", "").strip()
    memory_suggestions = chunks.get("memory_suggestions", "").strip()

    # Extract list lines for choices.
    choices: list[str] = []
    for line in choices_block.splitlines():
        s = line.strip().lstrip("-").lstrip("*").strip()
        if not s:
            continue
        # Skip heading-ish lines
        if s.lower().startswith("choices") or s.startswith("选项") or s.startswith("可选"):
            continue
        choices.append(s)

    return DMStructuredResponse(
        narration=narration,
        choices=choices,
        dm_notes=dm_notes,
        memory_suggestions=memory_suggestions,
        state_delta_json="",
        thread_updates_json="",
    )

