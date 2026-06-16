# Phase 1 System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the Phase 1 architecture from `docs/superpowers/specs/2026-06-15-one-person-dnd-system-redesign.md`: DeepSeek provider preset, typed player actions, context packs, deterministic turn agents, a shared turn pipeline, and a play-first responsive game UI.

**Architecture:** Keep FastAPI/Jinja2/SQLite and the existing public routes, but move turn semantics out of `web/routes/game.py` and `engine/orchestrator.py` into new `domain/`, `context/`, and `agents/` modules. The first pass uses deterministic agents and the existing OpenAI-compatible LLM client; streaming keeps the current no-second-repair invariant.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite, httpx, standard-library `unittest`, HTMX, small vanilla JS in templates.

**Implementation status (2026-06-16):** Tasks 1-7 are implemented in the current worktree. DeepSeek provider presets, `PlayerAction`, `ContextPack`, deterministic agents, `TurnPipeline`, non-streaming/streaming route integration, and the play-first navigation/responsive CSS now exist. Follow-up slices add `CharacterSummary`, inject authoritative character sheet summaries into ContextPack, show a readable character overview before advanced JSON editing, parse and render abilities/conditions/notes, add a lightweight `/character/quick_state` form for status notes, preserve top-level legacy character sheets during quick edits, prevent Web routes from duplicating session context in prompt overrides, preview pending `STATE_DELTA` requests through `domain.state_changes`, move the game UI toward a state-aware play cockpit where empty sessions start with the action composer and existing sessions show story history before a compact sticky composer, keep quick-roll controls directly next to the action composer, expose `/new` as a first-class new-adventure entry from the nav and home page, use the same active DB LLM profile resolution on the home page as the game routes, compress desktop 1280x720 and 520px-and-below mobile chrome so status/action/quick-roll controls reach the first viewport sooner, split the adventure panel into Character/World/Threads/System tabs, render open plot threads and next steps directly in the game page Threads tab, keep system controls tucked into advanced sections, route legacy `engine.run_turn()` through `TurnPipeline`, make `ActionJudgeAgent` / `ContinuityCriticAgent` / `ResponseEvaluatorAgent` enforce concrete solo-play flow rules such as adjudication warnings, non-streaming playability repair, malformed state-delta suppression, duplicate/vague next-action detection, and outcome-declaring choice warnings, surface `ActionJudgeAgent` output as a “系统判定” block for newly generated non-streaming and streaming turns, surface `ContextPack.recalled_context` as a “本回合参考” block for newly generated non-streaming and streaming turns, apply `[memory].context_chars_for_prompt` so low-priority recalls are marked “已裁剪” instead of entering the prompt, surface `ContinuityCriticAgent` warnings as a “DM 审查” block for newly generated non-streaming and streaming turns, surface `ResponseEvaluatorAgent` warnings as a “反应评估” block for newly generated non-streaming and streaming turns, route completed streaming DM output through the same critic/response-evaluator/persistence tail as non-streaming without adding a second LLM repair call, let player-approved `THREAD_UPDATES` preview/apply changes to `plot_threads`, and make `/models` DeepSeek-first with a quick-start form before custom OpenAI-compatible configuration while keeping saved API keys out of edit-form values. Continue with full smoke testing before treating Phase 1 as finished.

---

## Current Baseline

Current verification command:

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

Known environment note: this machine currently uses Python 3.11 in the shell, while `pyproject.toml` requires Python 3.12. Use `PYTHONPATH=src` for local verification if editable install is unavailable.

## File Structure

Create:

- `src/one_person_dnd/domain/__init__.py`
- `src/one_person_dnd/domain/actions.py`
- `src/one_person_dnd/context/__init__.py`
- `src/one_person_dnd/context/pack.py`
- `src/one_person_dnd/context/selection.py`
- `src/one_person_dnd/context/builder.py`
- `src/one_person_dnd/agents/__init__.py`
- `src/one_person_dnd/agents/base.py`
- `src/one_person_dnd/agents/action_judge.py`
- `src/one_person_dnd/agents/context_curator.py`
- `src/one_person_dnd/agents/continuity_critic.py`
- `src/one_person_dnd/agents/dungeon_master.py`
- `src/one_person_dnd/agents/state_keeper.py`
- `src/one_person_dnd/agents/pipeline.py`
- `src/one_person_dnd/llm/providers.py`
- `tests/test_actions.py`
- `tests/test_context_pack.py`
- `tests/test_llm_providers.py`
- `tests/test_turn_pipeline.py`

Modify:

- `src/one_person_dnd/llm/client.py`
- `src/one_person_dnd/llm/__init__.py`
- `src/one_person_dnd/web/routes/models.py`
- `src/one_person_dnd/web/templates/models.html`
- `src/one_person_dnd/web/routes/game.py`
- `src/one_person_dnd/web/templates/base.html`
- `src/one_person_dnd/web/templates/game.html`
- `src/one_person_dnd/web/static/style.css`
- `README.md`
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/RUNBOOK.md`

## Task 1: DeepSeek Provider Presets

**Files:**

- Create: `src/one_person_dnd/llm/providers.py`
- Modify: `src/one_person_dnd/llm/client.py`
- Modify: `src/one_person_dnd/llm/__init__.py`
- Modify: `src/one_person_dnd/web/routes/models.py`
- Modify: `src/one_person_dnd/web/templates/models.html`
- Test: `tests/test_llm_providers.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write provider preset tests**

Create `tests/test_llm_providers.py`:

```python
import unittest

from one_person_dnd.config import LLMConfig
from one_person_dnd.llm.providers import (
    apply_provider_defaults,
    get_provider_preset,
    list_provider_presets,
)


class TestLLMProviderPresets(unittest.TestCase):
    def test_deepseek_preset_exists(self) -> None:
        preset = get_provider_preset("deepseek")
        self.assertEqual(preset.id, "deepseek")
        self.assertEqual(preset.provider, "deepseek")
        self.assertEqual(preset.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(preset.default_model, "deepseek-chat")
        self.assertFalse(preset.allows_empty_api_key)

    def test_openai_compat_custom_preset_exists(self) -> None:
        ids = [p.id for p in list_provider_presets()]
        self.assertIn("openai_compat", ids)
        self.assertIn("deepseek", ids)

    def test_apply_provider_defaults_fills_missing_values(self) -> None:
        cfg = LLMConfig(provider="deepseek", base_url="", api_key="k", model="")
        out = apply_provider_defaults(cfg)
        self.assertEqual(out.provider, "deepseek")
        self.assertEqual(out.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(out.model, "deepseek-chat")
        self.assertEqual(out.api_key, "k")

    def test_apply_provider_defaults_preserves_explicit_values(self) -> None:
        cfg = LLMConfig(provider="deepseek", base_url="https://proxy.example/v1", api_key="k", model="deepseek-reasoner")
        out = apply_provider_defaults(cfg)
        self.assertEqual(out.base_url, "https://proxy.example/v1")
        self.assertEqual(out.model, "deepseek-reasoner")
```

- [ ] **Step 2: Run provider tests and verify failure**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_llm_providers -v
```

Expected: import failure for `one_person_dnd.llm.providers`.

- [ ] **Step 3: Implement provider presets**

Create `src/one_person_dnd/llm/providers.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace

from one_person_dnd.config import LLMConfig


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    provider: str
    base_url: str
    default_model: str
    allows_empty_api_key: bool = True
    help_text: str = ""


_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai_compat",
        label="OpenAI-compatible custom",
        provider="openai_compat",
        base_url="",
        default_model="",
        allows_empty_api_key=True,
        help_text="Use any server that exposes /v1/chat/completions.",
    ),
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        allows_empty_api_key=False,
        help_text="DeepSeek uses an OpenAI-compatible chat completions API.",
    ),
)


def list_provider_presets() -> list[ProviderPreset]:
    return list(_PRESETS)


def get_provider_preset(provider_id: str) -> ProviderPreset:
    normalized = (provider_id or "openai_compat").strip().lower()
    aliases = {
        "openai": "openai_compat",
        "openai-compatible": "openai_compat",
        "openai_compatible": "openai_compat",
    }
    normalized = aliases.get(normalized, normalized)
    for preset in _PRESETS:
        if preset.id == normalized or preset.provider == normalized:
            return preset
    return _PRESETS[0]


def apply_provider_defaults(cfg: LLMConfig) -> LLMConfig:
    preset = get_provider_preset(cfg.provider)
    base_url = (cfg.base_url or "").strip() or preset.base_url
    model = (cfg.model or "").strip() or preset.default_model
    provider = (cfg.provider or preset.provider).strip() or preset.provider
    return replace(cfg, provider=provider, base_url=base_url, model=model)


def transport_provider(provider: str) -> str:
    preset = get_provider_preset(provider)
    if preset.id == "deepseek":
        return "openai_compat"
    return preset.provider
```

- [ ] **Step 4: Allow DeepSeek in the LLM client**

Modify `src/one_person_dnd/llm/client.py`:

```python
from one_person_dnd.llm.providers import apply_provider_defaults, transport_provider
```

In `OpenAICompatClient.__init__`, replace the assignment:

```python
self._cfg = apply_provider_defaults(cfg)
```

In `create_llm_client`, replace provider normalization with:

```python
effective = apply_provider_defaults(cfg)
provider = transport_provider(effective.provider).strip().lower()
if provider in ("openai_compat", "openai-compatible", "openai"):
    return OpenAICompatClient(effective)
```

- [ ] **Step 5: Export providers**

Modify `src/one_person_dnd/llm/__init__.py` to export:

```python
from one_person_dnd.llm.providers import ProviderPreset, apply_provider_defaults, get_provider_preset, list_provider_presets
```

- [ ] **Step 6: Add client test for DeepSeek transport**

Add to `tests/test_llm_client.py`:

```python
    def test_deepseek_uses_openai_compatible_endpoint(self) -> None:
        cfg = LLMConfig(provider="deepseek", base_url="", api_key="k", model="")
        c = OpenAICompatClient(cfg)
        self.assertEqual(c._endpoint(), "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(c._headers()["Authorization"], "Bearer k")
```

- [ ] **Step 7: Pass provider presets to the model page**

Modify `src/one_person_dnd/web/routes/models.py` imports:

```python
from one_person_dnd.llm.providers import apply_provider_defaults, list_provider_presets
```

In `models_page`, add context:

```python
"provider_presets": list_provider_presets(),
```

In `models_create` and `models_update`, build a config and apply defaults before saving:

```python
cfg = apply_provider_defaults(
    LLMConfig(
        provider=(provider or "openai_compat").strip(),
        base_url=base_url.strip(),
        api_key=(api_key or "").strip(),
        model=model.strip(),
        timeout_seconds=float(timeout_seconds),
    )
)
```

Then save `cfg.provider`, `cfg.base_url`, `cfg.api_key`, `cfg.model`, and `cfg.timeout_seconds`.

- [ ] **Step 8: Add provider select to `models.html`**

In `src/one_person_dnd/web/templates/models.html`, replace the provider input in the create form with:

```html
<label class="label">
  Provider
  <select class="input" name="provider" data-provider-select>
    {% for preset in provider_presets %}
      <option
        value="{{ preset.id }}"
        data-base-url="{{ preset.base_url }}"
        data-default-model="{{ preset.default_model }}"
      >{{ preset.label }}</option>
    {% endfor %}
  </select>
</label>
```

Add this script near the bottom of the template:

```html
<script>
  (function () {
    document.querySelectorAll("[data-provider-select]").forEach(function (select) {
      const form = select.closest("form");
      if (!form) return;
      const baseUrl = form.querySelector("[name=base_url]");
      const model = form.querySelector("[name=model]");
      function applyPreset() {
        const opt = select.options[select.selectedIndex];
        if (!opt) return;
        const nextBase = opt.getAttribute("data-base-url") || "";
        const nextModel = opt.getAttribute("data-default-model") || "";
        if (baseUrl && nextBase && !baseUrl.value.trim()) baseUrl.value = nextBase;
        if (model && nextModel && !model.value.trim()) model.value = nextModel;
      }
      select.addEventListener("change", applyPreset);
      applyPreset();
    });
  })();
</script>
```

- [ ] **Step 9: Run provider tests**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_llm_providers tests.test_llm_client -v
```

Expected: all tests pass.

## Task 2: Domain Player Actions And Deterministic Action Judge

**Files:**

- Create: `src/one_person_dnd/domain/__init__.py`
- Create: `src/one_person_dnd/domain/actions.py`
- Create: `src/one_person_dnd/agents/__init__.py`
- Create: `src/one_person_dnd/agents/action_judge.py`
- Test: `tests/test_actions.py`

- [ ] **Step 1: Write action assessment tests**

Create `tests/test_actions.py`:

```python
import unittest

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.domain.actions import PlayerAction


class TestActionJudgeAgent(unittest.TestCase):
    def test_detects_explicit_dice(self) -> None:
        action = PlayerAction(campaign_id=1, session_id=2, text="我观察门锁并掷 1d20+3", manual_tags=[], extra_context="")
        result = ActionJudgeAgent().run(action)
        self.assertEqual(result.action_type, "exploration")
        self.assertEqual(len(result.dice_events), 1)
        self.assertIn("explicit_roll", result.signals)

    def test_flags_player_overreach(self) -> None:
        action = PlayerAction(campaign_id=1, session_id=2, text="我宣布国王立刻死亡并把王国送给我", manual_tags=[], extra_context="")
        result = ActionJudgeAgent().run(action)
        self.assertIn("possible_overreach", result.warnings)

    def test_classifies_social_action(self) -> None:
        action = PlayerAction(campaign_id=1, session_id=2, text="我试图说服守卫放我进去", manual_tags=[], extra_context="")
        result = ActionJudgeAgent().run(action)
        self.assertEqual(result.action_type, "social")
        self.assertIn("roll_may_be_needed", result.signals)
```

- [ ] **Step 2: Run action tests and verify failure**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_actions -v
```

Expected: import failure for new modules.

- [ ] **Step 3: Implement action dataclasses**

Create `src/one_person_dnd/domain/actions.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from one_person_dnd.engine.dice import DiceEvent


@dataclass(frozen=True)
class PlayerAction:
    campaign_id: int
    session_id: int
    text: str
    manual_tags: list[str] = field(default_factory=list)
    extra_context: str = ""


@dataclass(frozen=True)
class ActionAssessment:
    action_type: str
    dice_events: list[DiceEvent]
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

Create `src/one_person_dnd/domain/__init__.py`:

```python
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction

__all__ = ["ActionAssessment", "PlayerAction"]
```

- [ ] **Step 4: Implement deterministic action judge**

Create `src/one_person_dnd/agents/action_judge.py`:

```python
from __future__ import annotations

from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.engine.dice import roll_events_from_text


class ActionJudgeAgent:
    def run(self, action: PlayerAction) -> ActionAssessment:
        text = (action.text or "").strip()
        lowered = text.lower()
        dice_events = roll_events_from_text(text, max_rolls=5)
        signals: list[str] = []
        warnings: list[str] = []

        if dice_events:
            signals.append("explicit_roll")

        action_type = "exploration"
        if any(k in text for k in ("说服", "交涉", "欺骗", "威胁", "询问", "谈判")):
            action_type = "social"
        elif any(k in text for k in ("攻击", "战斗", "施法", "射击", "挥砍")):
            action_type = "combat"
        elif any(k in text for k in ("休息", "睡觉", "扎营", "疗伤")):
            action_type = "rest"
        elif any(k in text for k in ("背包", "购买", "出售", "装备", "使用物品")):
            action_type = "inventory"
        elif lowered.startswith("/") or any(k in text for k in ("系统", "debug", "忽略规则")):
            action_type = "meta"

        if not dice_events and action_type in ("social", "combat", "exploration"):
            signals.append("roll_may_be_needed")

        if any(k in text for k in ("我宣布", "直接杀死", "立刻死亡", "世界规则改为", "所有人都")):
            warnings.append("possible_overreach")

        return ActionAssessment(
            action_type=action_type,
            dice_events=dice_events,
            signals=signals,
            warnings=warnings,
        )
```

Create `src/one_person_dnd/agents/__init__.py`:

```python
from one_person_dnd.agents.action_judge import ActionJudgeAgent

__all__ = ["ActionJudgeAgent"]
```

- [ ] **Step 5: Run action tests**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_actions -v
```

Expected: all tests pass.

## Task 3: ContextPack And Context Builder

**Files:**

- Create: `src/one_person_dnd/context/__init__.py`
- Create: `src/one_person_dnd/context/pack.py`
- Create: `src/one_person_dnd/context/selection.py`
- Create: `src/one_person_dnd/context/builder.py`
- Test: `tests/test_context_pack.py`

- [ ] **Step 1: Write context pack tests**

Create `tests/test_context_pack.py`:

```python
import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.builder import build_context_pack
from one_person_dnd.db.schema import init_db
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, sessions, world_bible
from one_person_dnd.domain.actions import PlayerAction


class TestContextPack(unittest.TestCase):
    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection]:
        d = tempfile.TemporaryDirectory()
        db_path = Path(d.name) / "test.sqlite3"
        init_db(db_path)
        return d, get_connection(db_path)

    def test_builds_context_pack_with_world_and_scene(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="乌鸦酒馆")
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type="Location",
                title="乌鸦酒馆",
                content="港口区的旧酒馆，老板知道走私线索。",
                tags="酒馆,港口区",
            )
            conn.commit()

            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我在酒馆观察可疑的人",
                manual_tags=["酒馆"],
                extra_context="我保持低调。",
            )
            assessment = ActionJudgeAgent().run(action)
            pack = build_context_pack(conn, action=action, assessment=assessment, memory_cfg=MemoryConfig())
            kinds = [b.kind for b in pack.blocks]
            self.assertIn("world_bible", kinds)
            self.assertIn("scene_state", kinds)
            self.assertIn("action_assessment", kinds)
            self.assertEqual(pack.recalled_world[0]["title"], "乌鸦酒馆")
        finally:
            conn.close()
            tmp.cleanup()
```

- [ ] **Step 2: Implement context dataclasses**

Create `src/one_person_dnd/context/pack.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.engine.dice import DiceEvent


@dataclass(frozen=True)
class ContextBlock:
    kind: str
    title: str
    content: str
    source: str
    priority: int = 0


@dataclass(frozen=True)
class ContextPack:
    campaign_id: int
    session_id: int
    action_text: str
    blocks: list[ContextBlock] = field(default_factory=list)
    recalled_world: list[dict] = field(default_factory=list)
    dice_events: list[DiceEvent] = field(default_factory=list)
    assessment: ActionAssessment | None = None

    def blocks_of_kind(self, kind: str) -> list[ContextBlock]:
        return [b for b in self.blocks if b.kind == kind]
```

Create `src/one_person_dnd/context/__init__.py`:

```python
from one_person_dnd.context.pack import ContextBlock, ContextPack

__all__ = ["ContextBlock", "ContextPack"]
```

- [ ] **Step 3: Move selection helpers**

Create `src/one_person_dnd/context/selection.py`:

```python
from __future__ import annotations

import sqlite3

from one_person_dnd.db.repos import plot_threads, story_journal, summaries, turn_logs, world_bible
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import ChatMessage


def select_world_blocks(conn: sqlite3.Connection, *, campaign_id: int, tags: list[str] | None, limit: int = 10) -> tuple[list[str], list[dict]]:
    rows = world_bible.select_world_bible_for_prompt(conn, campaign_id=campaign_id, tags=tags, limit=limit)
    blocks: list[str] = []
    preview: list[dict] = []
    for r in rows:
        blocks.append(f"[{r['type']}] {r['title']}\n标签：{r['tags'] or ''}\n{r['content']}")
        preview.append({"type": r["type"], "title": r["title"], "tags": r["tags"] or ""})
    return blocks, preview


def select_thread_blocks(conn: sqlite3.Connection, *, session_id: int, limit: int = 20) -> list[str]:
    rows = plot_threads.list_open_threads(conn, session_id=session_id, limit=limit)
    blocks: list[str] = []
    for t in rows:
        parts = [f"[P{t.get('priority', 0)}] {(t.get('title') or '').strip()}"]
        if (t.get("tags") or "").strip():
            parts.append(f"标签：{(t.get('tags') or '').strip()}")
        if (t.get("summary") or "").strip():
            parts.append(f"进展：{(t.get('summary') or '').strip()}")
        if (t.get("next_step") or "").strip():
            parts.append(f"下一步：{(t.get('next_step') or '').strip()}")
        blocks.append("\n".join(parts).strip())
    return blocks


def select_story_blocks(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[str]:
    rows = story_journal.select_story_journal_for_prompt(conn, session_id=session_id, limit=limit)
    blocks: list[str] = []
    for r in rows[::-1]:
        blocks.append(f"场景：{r['scene_id'] or ''}\n摘要：{r['summary']}\n未解决：{r['open_threads'] or ''}\n要点：{r['key_facts'] or ''}")

    campaign_sum = summaries.get_latest_summary(conn, session_id=session_id, level="campaign")
    chapter_sum = summaries.get_latest_summary(conn, session_id=session_id, level="chapter")
    if campaign_sum and (campaign_sum.get("summary") or "").strip():
        blocks = ["【战役总摘要】\n" + (campaign_sum.get("summary") or "").strip()] + blocks
    if chapter_sum and (chapter_sum.get("summary") or "").strip():
        blocks = ["【最近章节摘要】\n" + (chapter_sum.get("summary") or "").strip()] + blocks
    return blocks


def select_recent_turn_messages(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[ChatMessage]:
    if limit <= 0:
        return []
    rows = turn_logs.list_recent_turn_pairs(conn, session_id=session_id, limit=limit)
    messages: list[ChatMessage] = []
    for r in rows[::-1]:
        player_text = (r["player_text"] or "").strip()
        dm_text = (r["dm_text"] or "").strip()
        if player_text:
            messages.append(ChatMessage(role="user", content=player_text))
        if dm_text:
            dm = parse_dm_text(dm_text)
            parts = []
            if dm.narration:
                parts.append(dm.narration.strip())
            if dm.choices:
                parts.append("可选行动：\n" + "\n".join([f"- {c}" for c in dm.choices]))
            messages.append(ChatMessage(role="assistant", content="\n\n".join(parts).strip() or dm_text))
    return messages
```

- [ ] **Step 4: Implement context builder**

Create `src/one_person_dnd/context/builder.py`:

```python
from __future__ import annotations

import sqlite3

from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.pack import ContextBlock, ContextPack
from one_person_dnd.context.selection import select_story_blocks, select_thread_blocks, select_world_blocks
from one_person_dnd.db.repos import sessions
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.engine.dice import format_events_for_prompt


def build_context_pack(
    conn: sqlite3.Connection,
    *,
    action: PlayerAction,
    assessment: ActionAssessment,
    memory_cfg: MemoryConfig,
    state_block: str = "",
    cheat_prompt: str = "",
) -> ContextPack:
    blocks: list[ContextBlock] = []
    world_blocks, recalled_world = select_world_blocks(conn, campaign_id=action.campaign_id, tags=action.manual_tags or None)
    for idx, block in enumerate(world_blocks):
        blocks.append(ContextBlock(kind="world_bible", title=f"WorldBible {idx + 1}", content=block, source="world_bible", priority=80))

    srow = sessions.get_session_sidebar(conn, action.session_id)
    if srow:
        scene_parts = []
        if (srow["title"] or "").strip():
            scene_parts.append(f"会话：{(srow['title'] or '').strip()}")
        if (srow["current_scene"] or "").strip():
            scene_parts.append(f"当前场景：{(srow['current_scene'] or '').strip()}")
        if scene_parts:
            blocks.append(ContextBlock(kind="scene_state", title="Scene", content="\n".join(scene_parts), source="sessions", priority=90))
        if (srow["session_state"] or "").strip():
            blocks.append(ContextBlock(kind="character_state", title="Character State", content=(srow["session_state"] or "").strip(), source="sessions", priority=90))
        if (srow["pinned_world_notes"] or "").strip():
            blocks.append(ContextBlock(kind="world_bible", title="Pinned World Notes", content=(srow["pinned_world_notes"] or "").strip(), source="sessions.pinned_world_notes", priority=100))

    if assessment.dice_events:
        blocks.append(ContextBlock(kind="dice", title="Dice", content=format_events_for_prompt(assessment.dice_events), source="action_judge", priority=95))
    if state_block.strip():
        blocks.append(ContextBlock(kind="scene_state", title="Turn Extra Context", content=state_block.strip(), source="player.extra_context", priority=70))
    if cheat_prompt.strip():
        blocks.append(ContextBlock(kind="cheat_directive", title="Cheat Directive", content=cheat_prompt.strip(), source="session_cheats", priority=60))

    thread_blocks = select_thread_blocks(conn, session_id=action.session_id)
    for idx, block in enumerate(thread_blocks):
        blocks.append(ContextBlock(kind="plot_threads", title=f"Open Thread {idx + 1}", content=block, source="plot_threads", priority=70))

    story_blocks = select_story_blocks(conn, session_id=action.session_id, limit=memory_cfg.story_journal_for_prompt)
    for idx, block in enumerate(story_blocks):
        blocks.append(ContextBlock(kind="story_memory", title=f"Story Memory {idx + 1}", content=block, source="story_journal", priority=50))

    assessment_text = "\n".join(
        [
            f"action_type: {assessment.action_type}",
            "signals: " + ", ".join(assessment.signals),
            "warnings: " + ", ".join(assessment.warnings),
        ]
    ).strip()
    blocks.append(ContextBlock(kind="action_assessment", title="Action Assessment", content=assessment_text, source="action_judge", priority=85))

    return ContextPack(
        campaign_id=action.campaign_id,
        session_id=action.session_id,
        action_text=action.text,
        blocks=blocks,
        recalled_world=recalled_world,
        dice_events=assessment.dice_events,
        assessment=assessment,
    )
```

- [ ] **Step 5: Run context tests**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_context_pack -v
```

Expected: all tests pass.

## Task 4: Deterministic Agent Pipeline

**Files:**

- Create: `src/one_person_dnd/agents/base.py`
- Create: `src/one_person_dnd/agents/context_curator.py`
- Create: `src/one_person_dnd/agents/continuity_critic.py`
- Create: `src/one_person_dnd/agents/dungeon_master.py`
- Create: `src/one_person_dnd/agents/state_keeper.py`
- Create: `src/one_person_dnd/agents/pipeline.py`
- Modify: `src/one_person_dnd/engine/prompt_builder.py`
- Test: `tests/test_turn_pipeline.py`

- [ ] **Step 1: Write pipeline test with a fake DM client**

Create `tests/test_turn_pipeline.py`:

```python
import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.agents.pipeline import TurnPipeline
from one_person_dnd.config import MemoryConfig
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.schema import init_db
from one_person_dnd.db.repos import campaigns, sessions
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.llm import ChatMessage


class FakeDMClient:
    def chat(self, messages: list[ChatMessage]) -> str:
        return "\n".join(
            [
                "===NARRATION===",
                "你推开门，屋内传来潮湿木头的气味。",
                "===CHOICES===",
                "- 进入房间",
                "- 退后观察",
                "===DM_NOTES===",
                "保持悬念。",
                "===MEMORY===",
                "玩家发现一扇潮湿木门。",
            ]
        )


class TestTurnPipeline(unittest.TestCase):
    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection, int, int]:
        d = tempfile.TemporaryDirectory()
        db_path = Path(d.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        campaign_id = campaigns.create_campaign(conn, "测试战役")
        session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
        conn.commit()
        return d, conn, campaign_id, session_id

    def test_non_streaming_pipeline_persists_turn(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(campaign_id=campaign_id, session_id=session_id, text="我推开门", manual_tags=[], extra_context="")
            result = TurnPipeline(dm_client=FakeDMClient()).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())
            self.assertEqual(result.turn_index, 0)
            self.assertEqual(result.dm.choices, ["进入房间", "退后观察"])
            self.assertEqual(result.recalled_world, [])
            row = conn.execute("SELECT COUNT(*) AS c FROM turn_logs WHERE session_id = ?", (session_id,)).fetchone()
            self.assertEqual(int(row["c"]), 1)
        finally:
            conn.close()
            tmp.cleanup()
```

- [ ] **Step 2: Add prompt builder from ContextPack**

Modify `src/one_person_dnd/engine/prompt_builder.py` with:

```python
from one_person_dnd.context.pack import ContextPack
```

Add:

```python
def build_dm_messages_from_context_pack(pack: ContextPack) -> list[ChatMessage]:
    world = "\n\n".join([b.content for b in pack.blocks if b.kind == "world_bible"]) or "（无相关世界设定条目）"
    story = "\n\n".join([b.content for b in pack.blocks if b.kind == "story_memory"]) or "（无近期剧情摘要）"
    threads = "\n\n".join([b.content for b in pack.blocks if b.kind == "plot_threads"]) or "（无进行中的主线线程）"
    state_parts = [b.content for b in pack.blocks if b.kind in ("scene_state", "character_state", "dice", "action_assessment", "cheat_directive")]
    return build_dm_messages(
        memory=RetrievedMemory(world_bible_blocks=[world], story_blocks=[story], plot_threads_blocks=[threads]),
        state_block="\n\n".join([p for p in state_parts if p.strip()]).strip(),
    )
```

- [ ] **Step 3: Implement basic agent modules**

Create `src/one_person_dnd/agents/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

Create `src/one_person_dnd/agents/context_curator.py`:

```python
from __future__ import annotations

import sqlite3

from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.builder import build_context_pack
from one_person_dnd.context.pack import ContextPack
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction


class ContextCuratorAgent:
    def run(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        assessment: ActionAssessment,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> ContextPack:
        return build_context_pack(
            conn,
            action=action,
            assessment=assessment,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
```

Create `src/one_person_dnd/agents/continuity_critic.py`:

```python
from __future__ import annotations

from one_person_dnd.agents.base import AgentResult
from one_person_dnd.engine.orchestrator import _has_required_protocol_delims


class ContinuityCriticAgent:
    def run(self, dm_raw: str) -> AgentResult:
        warnings: list[str] = []
        if not (dm_raw or "").strip():
            warnings.append("empty_dm_response")
        if not _has_required_protocol_delims(dm_raw):
            warnings.append("missing_required_protocol_delimiters")
        return AgentResult(agent_name="continuity_critic", status="ok" if not warnings else "warn", warnings=warnings)
```

Create `src/one_person_dnd/agents/dungeon_master.py`:

```python
from __future__ import annotations

from one_person_dnd.context.pack import ContextPack
from one_person_dnd.engine.orchestrator import ensure_dm_protocol_output
from one_person_dnd.engine.prompt_builder import build_dm_messages_from_context_pack
from one_person_dnd.llm import ChatMessage


class DungeonMasterAgent:
    def __init__(self, client) -> None:
        self._client = client

    def build_messages(self, pack: ContextPack, *, player_text: str, recent_messages: list[ChatMessage] | None = None) -> list[ChatMessage]:
        messages = build_dm_messages_from_context_pack(pack)
        messages.extend(recent_messages or [])
        messages.append(ChatMessage(role="user", content=player_text))
        return messages

    def run_non_streaming(self, messages: list[ChatMessage], *, repair: bool = True) -> tuple[str, bool]:
        dm_raw = self._client.chat(messages)
        if repair:
            return ensure_dm_protocol_output(self._client, messages, dm_raw, max_retries=1)
        return dm_raw, False
```

Create `src/one_person_dnd/agents/state_keeper.py`:

```python
from __future__ import annotations

import sqlite3

from one_person_dnd.engine.orchestrator import TurnResult, persist_turn
from one_person_dnd.engine.parser import DMStructuredResponse
from one_person_dnd.engine.dice import DiceEvent


class StateKeeperAgent:
    def persist(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        player_text: str,
        dm_raw: str,
        dm_struct: DMStructuredResponse,
        recalled_world: list[dict],
        dice_events: list[DiceEvent],
    ) -> TurnResult:
        return persist_turn(
            conn,
            session_id=session_id,
            player_text=player_text,
            dm_raw=dm_raw,
            dm_struct=dm_struct,
            recalled_world=recalled_world,
            dice_events=dice_events,
        )
```

- [ ] **Step 4: Implement pipeline**

Create `src/one_person_dnd/agents/pipeline.py`:

```python
from __future__ import annotations

import sqlite3

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.agents.context_curator import ContextCuratorAgent
from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent
from one_person_dnd.agents.dungeon_master import DungeonMasterAgent
from one_person_dnd.agents.state_keeper import StateKeeperAgent
from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.selection import select_recent_turn_messages
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.engine.orchestrator import TurnResult
from one_person_dnd.engine.parser import parse_dm_text


class TurnPipeline:
    def __init__(
        self,
        *,
        dm_client,
        action_judge: ActionJudgeAgent | None = None,
        context_curator: ContextCuratorAgent | None = None,
        critic: ContinuityCriticAgent | None = None,
        state_keeper: StateKeeperAgent | None = None,
    ) -> None:
        self.action_judge = action_judge or ActionJudgeAgent()
        self.context_curator = context_curator or ContextCuratorAgent()
        self.dm = DungeonMasterAgent(dm_client)
        self.critic = critic or ContinuityCriticAgent()
        self.state_keeper = state_keeper or StateKeeperAgent()

    def run_non_streaming(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> TurnResult:
        assessment = self.action_judge.run(action)
        pack = self.context_curator.run(
            conn,
            action=action,
            assessment=assessment,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
        recent = select_recent_turn_messages(conn, session_id=action.session_id, limit=memory_cfg.history_turns_for_prompt)
        messages = self.dm.build_messages(pack, player_text=action.text, recent_messages=recent)
        dm_raw, _repaired = self.dm.run_non_streaming(messages, repair=True)
        self.critic.run(dm_raw)
        dm_struct = parse_dm_text(dm_raw)
        result = self.state_keeper.persist(
            conn,
            session_id=action.session_id,
            player_text=action.text,
            dm_raw=dm_raw,
            dm_struct=dm_struct,
            recalled_world=pack.recalled_world,
            dice_events=pack.dice_events,
        )
        conn.commit()
        return result
```

Update `src/one_person_dnd/agents/__init__.py`:

```python
from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.agents.context_curator import ContextCuratorAgent
from one_person_dnd.agents.pipeline import TurnPipeline

__all__ = ["ActionJudgeAgent", "ContextCuratorAgent", "TurnPipeline"]
```

- [ ] **Step 5: Run pipeline tests**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_turn_pipeline -v
```

Expected: all tests pass.

## Task 5: Route Non-Streaming Turns Through Pipeline

**Files:**

- Modify: `src/one_person_dnd/web/routes/game.py`
- Test: `tests/test_turn_pipeline.py`

- [ ] **Step 1: Extract session prompt state helper**

In `src/one_person_dnd/web/routes/game.py`, create a helper near the top:

```python
def _build_session_prompt_state(
    *,
    session_title: str,
    current_scene: str,
    session_state: str,
    pinned_world_notes: str,
    cheat_enabled: bool,
    cheat_prompt: str,
    state_block: str,
) -> tuple[str, str]:
    state_parts: list[str] = []
    if current_scene:
        state_parts.append(f"当前场景：{current_scene}")
    if session_title:
        state_parts.append(f"会话：{session_title}")
    if pinned_world_notes:
        state_parts.append("【置顶世界设定】\n" + pinned_world_notes)
    if session_state:
        state_parts.append("【主角/队伍状态】\n" + session_state)
    effective_cheat_prompt = cheat_prompt if cheat_enabled else ""
    if effective_cheat_prompt:
        state_parts.append("【CheatDirective（仅在本会话生效）】\n" + effective_cheat_prompt)
    if (state_block or "").strip():
        state_parts.append("【本回合额外上下文】\n" + (state_block or "").strip())
    return "\n\n".join(state_parts).strip(), effective_cheat_prompt
```

- [ ] **Step 2: Replace non-streaming turn internals**

In `game_turn`, after loading session/sidebar values, replace manual dice/message/client/persist code with:

```python
from one_person_dnd.agents.pipeline import TurnPipeline
from one_person_dnd.domain.actions import PlayerAction
```

Then:

```python
merged_state_block, effective_cheat_prompt = _build_session_prompt_state(
    session_title=session_title,
    current_scene=current_scene,
    session_state=session_state,
    pinned_world_notes=pinned_world_notes,
    cheat_enabled=cheat_enabled,
    cheat_prompt=cheat_prompt,
    state_block=state_block,
)
tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
memory_cfg = load_memory_config(paths.config_path)
client = create_llm_client(llm_cfg)
action = PlayerAction(
    campaign_id=campaign_id,
    session_id=session_id,
    text=player_text,
    manual_tags=tag_list,
    extra_context=(state_block or "").strip(),
)
conn = get_connection(paths.db_path)
try:
    result = TurnPipeline(dm_client=client).run_non_streaming(
        conn,
        action=action,
        memory_cfg=memory_cfg,
        state_block=merged_state_block,
        cheat_prompt=effective_cheat_prompt,
    )
finally:
    conn.close()
```

Keep the existing template response shape.

- [ ] **Step 3: Keep logging minimal**

Remove detailed per-stage timing from `game_turn` for the first pipeline pass, or log only:

```python
logger.info("turn_done web_non_stream session=%s turn=%s", session_id, result.turn_index)
```

Detailed timing can return after pipeline stage tracing exists.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_turn_pipeline tests.test_actions tests.test_context_pack -v
```

Expected: all tests pass.

## Task 6: Route Streaming Context Through The Same Pipeline Pieces

**Files:**

- Modify: `src/one_person_dnd/web/routes/game.py`
- Modify: `src/one_person_dnd/agents/pipeline.py`

- [ ] **Step 1: Add pipeline preparation method**

Add to `TurnPipeline`:

```python
def prepare_messages(
    self,
    conn: sqlite3.Connection,
    *,
    action: PlayerAction,
    memory_cfg: MemoryConfig,
    state_block: str = "",
    cheat_prompt: str = "",
) -> tuple[list, list[dict], list]:
    assessment = self.action_judge.run(action)
    pack = self.context_curator.run(
        conn,
        action=action,
        assessment=assessment,
        memory_cfg=memory_cfg,
        state_block=state_block,
        cheat_prompt=cheat_prompt,
    )
    recent = select_recent_turn_messages(conn, session_id=action.session_id, limit=memory_cfg.history_turns_for_prompt)
    messages = self.dm.build_messages(pack, player_text=action.text, recent_messages=recent)
    return messages, pack.recalled_world, pack.dice_events
```

Use `prepare_messages` inside `run_non_streaming` to avoid duplicate context assembly.

- [ ] **Step 2: Update streaming route**

In `_gen()` inside `game_turn_stream`, replace `build_turn_messages_and_preview` with:

```python
action = PlayerAction(
    campaign_id=campaign_id,
    session_id=session_id,
    text=player_text,
    manual_tags=tag_list,
    extra_context=(state_block or "").strip(),
)
pipeline = TurnPipeline(dm_client=client)
messages, recalled_world, dice_events = pipeline.prepare_messages(
    conn,
    action=action,
    memory_cfg=memory_cfg,
    state_block=merged_state_block,
    cheat_prompt=cheat_prompt if cheat_enabled else "",
)
```

Keep this invariant:

```python
dm_raw, repaired = ensure_dm_protocol_output(client, messages, dm_raw, max_retries=0)
```

- [ ] **Step 3: Persist through StateKeeperAgent**

Replace direct `persist_turn` call in streaming route with:

```python
result = pipeline.state_keeper.persist(
    conn,
    session_id=session_id,
    player_text=player_text,
    dm_raw=dm_raw,
    dm_struct=dm_struct,
    recalled_world=recalled_world,
    dice_events=dice_events,
)
conn.commit()
```

- [ ] **Step 4: Run compile and tests**

Run:

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

Expected: all tests pass.

## Task 7: Play-First Game UI And Responsive CSS

**Files:**

- Modify: `src/one_person_dnd/web/templates/base.html`
- Modify: `src/one_person_dnd/web/templates/game.html`
- Modify: `src/one_person_dnd/web/templates/index.html`
- Modify: `src/one_person_dnd/web/static/style.css`

- [ ] **Step 1: Simplify global navigation**

In `base.html`, change nav labels to player-facing labels and remove `/setup` from primary navigation:

```html
<nav class="nav">
  <a href="/game">游玩</a>
  <a href="/saves">冒险</a>
  <a href="/memory/world">世界</a>
  <a href="/threads">剧情线</a>
  <a href="/models">模型</a>
</nav>
```

- [ ] **Step 2: Fix home model setup link**

In `index.html`, change the not-configured CTA:

```html
<p><a class="btn" href="/models">去配置模型</a></p>
```

- [ ] **Step 3: Reframe game sidebar sections**

In `game.html`, change `信息栏` into `冒险面板` and group sections in this order:

1. Character/status and pending changes.
2. World/pinned notes/recalled context.
3. Threads link and session metadata.
4. System/cheat/advanced JSON.

For Phase 1, keep existing forms but rename headings:

```html
<div class="card__title">冒险面板</div>
...
<div class="panel-section">
  <div class="panel-section__title">角色与状态</div>
  ...
</div>
```

- [ ] **Step 4: Add responsive nav and grid CSS**

Append to `style.css`:

```css
.panel-section {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 12px;
}
.panel-section__title {
  font-weight: 700;
  margin-bottom: 8px;
}

@media (max-width: 980px) {
  .header__inner {
    align-items: flex-start;
    flex-direction: column;
  }
  .nav {
    flex-wrap: wrap;
    gap: 8px 12px;
  }
  .grid {
    grid-template-columns: 1fr;
  }
  .table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }
}

@media (max-width: 520px) {
  .container {
    padding: 12px;
  }
  .page-title-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .chat-history {
    min-height: 300px;
  }
  .btn,
  .input--compact {
    max-width: 100%;
  }
}
```

- [ ] **Step 5: Verify mobile overflow manually**

Run:

```bash
PYTHONPATH=src python -m one_person_dnd --port 8010 --no-browser
```

Open these pages at 390px width:

- `/`
- `/game`
- `/saves`
- `/models`
- `/new`

Expected: no page has document width larger than viewport width. Stop the server after verification.

## Task 8: Documentation Sync

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RUNBOOK.md`
- Modify: `docs/superpowers/specs/2026-06-15-one-person-dnd-system-redesign.md` if implementation deviates from the spec.

- [ ] **Step 1: Update `AGENTS.md` structure boundaries**

Add bullets for new modules:

```markdown
- Domain objects live in `src/one_person_dnd/domain/`.
- Turn context assembly lives in `src/one_person_dnd/context/`.
- Turn agents and the shared pipeline live in `src/one_person_dnd/agents/`.
- LLM provider presets live in `src/one_person_dnd/llm/providers.py`; DeepSeek reuses OpenAI-compatible transport.
```

- [ ] **Step 2: Update architecture docs**

In `docs/ARCHITECTURE.md`, update the module diagram to include `domain/`, `context/`, `agents/`, and provider presets. Replace the old direct turn flow with:

```text
PlayerAction -> ActionJudgeAgent -> ContextCuratorAgent -> DungeonMasterAgent -> ContinuityCriticAgent -> StateKeeperAgent
```

- [ ] **Step 3: Update README**

Mention DeepSeek in the model setup section:

```markdown
`/models` 提供 DeepSeek 和 OpenAI-compatible custom 两类配置入口。DeepSeek 默认使用 `https://api.deepseek.com/v1` 和 `deepseek-chat`。
```

- [ ] **Step 4: Update runbook**

Add DeepSeek troubleshooting:

```markdown
### DeepSeek test fails

Check that the active profile uses `provider = deepseek`, `base_url = https://api.deepseek.com/v1`, a non-empty API key, and a valid model such as `deepseek-chat`.
```

- [ ] **Step 5: Check docs for stale language**

Run:

```bash
rg -n "setup|OpenAI-compatible|DeepSeek|ContextPack|TurnPipeline|domain/|agents/" README.md AGENTS.md docs/ARCHITECTURE.md docs/RUNBOOK.md
```

Expected: references describe the current implementation after Phase 1, not only the future spec.

## Task 9: Final Verification

**Files:**

- All changed files.

- [ ] **Step 1: Run compile**

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
```

Expected: exit code 0.

- [ ] **Step 2: Run full unit tests**

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

Expected: all tests pass.

- [ ] **Step 3: Run app smoke test**

```bash
PYTHONPATH=src python -m one_person_dnd --port 8010 --no-browser
```

Open:

- `http://127.0.0.1:8010/`
- `http://127.0.0.1:8010/models`
- `http://127.0.0.1:8010/game`
- `http://127.0.0.1:8010/saves`

Expected:

- Home points model setup to `/models`.
- `/models` exposes DeepSeek.
- `/game` loads with play-first labels.
- `/saves` does not horizontally overflow on mobile width.

- [ ] **Step 4: Inspect git diff**

```bash
git status --short
git diff --stat
```

Expected:

- New architecture files, tests, provider preset, route/template/CSS edits, and docs updates are visible.
- No runtime files such as `api_config.ini` or `.one_person_dnd/one_person_dnd.sqlite3` are staged or included.
