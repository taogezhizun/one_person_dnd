from __future__ import annotations

import json
from typing import Any


class GuardrailError(ValueError):
    pass


def validate_state_delta_json(delta_json_text: str, *, max_chars: int = 8000, max_depth: int = 8) -> dict[str, Any]:
    """
    MVP schema validation:
    - Must be a JSON object (dict)
    - Size limits + depth limits
    - Values must be JSON-serializable primitives/containers
    """
    t = (delta_json_text or "").strip()
    if not t:
        raise GuardrailError("STATE_DELTA 为空")
    if len(t) > max_chars:
        raise GuardrailError(f"STATE_DELTA 过大（>{max_chars} chars）")

    try:
        obj = json.loads(t)
    except Exception as e:
        raise GuardrailError(f"STATE_DELTA JSON 解析失败：{e}") from e

    if not isinstance(obj, dict):
        raise GuardrailError("STATE_DELTA 必须是 JSON 对象（{}）")

    def _check(v: Any, depth: int) -> None:
        if depth > max_depth:
            raise GuardrailError(f"STATE_DELTA 嵌套过深（>{max_depth}）")
        if v is None or isinstance(v, (str, int, float, bool)):
            return
        if isinstance(v, list):
            for it in v:
                _check(it, depth + 1)
            return
        if isinstance(v, dict):
            for k, it in v.items():
                if not isinstance(k, str):
                    raise GuardrailError("STATE_DELTA 的对象 key 必须是字符串")
                _check(it, depth + 1)
            return
        raise GuardrailError(f"STATE_DELTA 含不支持的类型：{type(v).__name__}")

    _check(obj, 1)
    return obj

