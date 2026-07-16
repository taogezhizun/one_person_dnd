"""Single source of truth for the Chinese display labels used in the game UI.

These five code -> 中文 maps used to be hand-duplicated across the Jinja
partials (`templates/partials/chat_turn.html`, `templates/partials/turn_diagnostics.html`)
and the streaming renderer (`static/js/app.js`). Historical turns are rendered
server-side by Jinja while new turns are rendered client-side by JS as they
stream in, so a stale copy in either place would silently show a raw code (or,
worse, a different translation) instead of the intended label.

Now Python owns the maps:
  - Jinja templates get them as globals (see `web/routes/common.py`), under the
    same variable names the templates already used (`action_type_labels`, ...).
  - `app.js` gets them serialized as JSON, injected via `base.html` into a
    `<script id="dnd-labels" type="application/json">` element that loads
    before `app.js` runs.

Do not edit these maps in templates or app.js directly; edit them here.
"""

from __future__ import annotations

import json
from typing import Any

ACTION_TYPE_LABELS: dict[str, str] = {
    "exploration": "探索",
    "social": "社交",
    "combat": "战斗",
    "rest": "休息",
    "inventory": "物品",
    "meta": "系统/元指令",
}

ACTION_SIGNAL_LABELS: dict[str, str] = {
    "explicit_roll": "已识别掷骰",
    "state_change_likely": "可能影响角色状态",
    "time_passes": "时间会推进",
    "roll_may_be_needed": "可能需要掷骰",
    "dm_should_adjudicate_outcome": "结果由 DM 判定",
}

ACTION_WARNING_LABELS: dict[str, str] = {
    "possible_overreach": "行动可能越权",
    "declared_success": "行动描述已包含结果",
    "npc_outcome_claim": "人物结果需要 DM 判定",
}

# NOTE: prior to this refactor, `turn_diagnostics.html` (server-rendered
# historical turns) and `app.js` (streaming new turns) had already drifted
# apart for these two maps: the Jinja copy used "行动建议..." wording while
# the JS copy used "选项..." wording for the same codes. Since a single
# source can only carry one value per code, this file adopts the
# "行动建议" wording, which matches the vocabulary used elsewhere in the app
# for `turn.dm.choices` (e.g. "行动灵感" / "行动建议" in game.html and
# chat_turn.html). This intentionally changes the text a freshly streamed
# turn shows for these three codes (previously "选项...") so both render
# paths agree going forward.
CRITIC_WARNING_LABELS: dict[str, str] = {
    "empty_dm_response": "DM 没有返回内容",
    "missing_required_protocol_delimiters": "DM 输出缺少必要段落",
    "empty_narration": "叙事内容为空",
    "choice_count_out_of_range": "行动建议数量不适合继续游玩",
    "malformed_state_delta": "状态变更建议格式有误",
}

RESPONSE_WARNING_LABELS: dict[str, str] = {
    "duplicate_choices": "行动建议重复",
    "non_actionable_choice": "行动建议过于笼统",
    "choice_declares_outcome": "行动建议替玩家宣布结果",
}


def all_label_maps() -> dict[str, dict[str, str]]:
    """Return all five label maps keyed for JSON serialization to the client."""
    return {
        "action_type": ACTION_TYPE_LABELS,
        "action_signal": ACTION_SIGNAL_LABELS,
        "action_warning": ACTION_WARNING_LABELS,
        "critic_warning": CRITIC_WARNING_LABELS,
        "response_warning": RESPONSE_WARNING_LABELS,
    }


def register_jinja_globals(env: Any) -> None:
    """Register the five label maps (plus their JSON form) on a Jinja Environment.

    Templates keep using the same variable names they used to `{% set %}`
    locally (`action_type_labels`, `action_signal_labels`,
    `action_warning_labels`, `critic_warning_labels`, `response_warning_labels`),
    so call sites like `action_type_labels.get(code, code)` are unchanged.
    """
    env.globals["action_type_labels"] = ACTION_TYPE_LABELS
    env.globals["action_signal_labels"] = ACTION_SIGNAL_LABELS
    env.globals["action_warning_labels"] = ACTION_WARNING_LABELS
    env.globals["critic_warning_labels"] = CRITIC_WARNING_LABELS
    env.globals["response_warning_labels"] = RESPONSE_WARNING_LABELS
    env.globals["label_maps_json"] = json.dumps(all_label_maps(), ensure_ascii=False)
