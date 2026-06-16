# One Person DND System Redesign

## Purpose

This spec defines the target redesign for `one_person_dnd`: a local-first solo DND/TRPG web app where one player can start, sustain, and branch an adventure with LLM assistance, while world canon, character state, story continuity, dice, and multi-agent guardrails stay coherent across turns.

The redesign preserves the existing FastAPI + Jinja2 + SQLite foundation, but changes the project from a collection of feature pages into a game system with explicit domain boundaries, a turn pipeline, a context contract, an agent layer, and a more playable UI.

## Current State

The app already has useful primitives:

- Campaigns, sessions, snapshots, forks, and local SQLite storage.
- OpenAI-compatible chat completion support.
- WorldBible entries, StoryJournal entries, PlotThreads, character sheet JSON, session state, pinned notes, dice, and cheat directives.
- A shared turn orchestrator for non-streaming and streaming routes.
- A local Web UI with game, saves, model, memory, thread, setup, and new-adventure pages.

The main structural problem is that these primitives are wired together as route-level features instead of as a coherent game engine. The turn pipeline currently mixes web form handling, context assembly, prompt protocol, LLM calls, persistence, and UI-side state concepts. The UI exposes internal concepts such as `Campaign`, `Session`, `WorldBible`, `StoryJournal`, `state_delta`, and raw JSON before the player has a clear play loop.

## Design Goals

1. **Project structure supports growth**
   - Separate domain models, context assembly, agent orchestration, LLM providers, persistence, and web presentation.
   - Keep route handlers thin and focused on HTTP concerns.
   - Keep DB repositories as persistence adapters, not the place where game rules live.
   - Keep coding-agent-facing docs current as the structure changes, especially `AGENTS.md`, `AGENT.md`, architecture docs, runbooks, and implementation specs.

2. **Solo DND is genuinely playable**
   - The primary loop is: player acts, system interprets action, dice/state/context are applied, DM narrates, choices appear, changes are reviewed, continuity is preserved.
   - The player should not need to manually understand prompt engineering to keep the adventure coherent.
   - Manual controls remain available, but as advanced or sidebar tools.

3. **Context is systematic**
   - World facts, character state, story memory, open threads, recent turns, scene, dice, and player intent flow through a typed `ContextPack`.
   - Every turn uses the same context contract, regardless of streaming mode or page entry point.
   - Context assembly records why each block was included so the UI can explain recall.

4. **Agent layer improves game flow**
   - Agents are small roles in one turn pipeline, not independent background services.
   - The first implementation can use deterministic agents where LLM calls are not required.
   - LLM-backed agents are introduced only when their output changes game quality enough to justify cost and latency.

5. **UI becomes play-first**
   - The game page focuses on story, actions, choices, dice, character status, and continuity.
   - Admin-like controls move into structured tabs or advanced panels.
   - Mobile and narrow-window layouts must not overflow horizontally.
   - Visual hierarchy must distinguish primary actions, secondary actions, dangerous actions, empty states, and review queues.

6. **DeepSeek is first-class**
   - DeepSeek is exposed as a model preset/provider option.
   - Internally it can reuse the OpenAI-compatible client.
   - The UI should help users configure `deepseek-chat` without needing to know endpoint details.

## Target Project Structure

```text
src/one_person_dnd/
  domain/
    models.py             # Campaign, Session, CharacterSheet, WorldEntry, PlotThread, Turn domain objects
    actions.py            # PlayerAction, DiceNeed, ActionRisk, ActionAssessment
    state.py              # StateDelta, ChangeRequest, apply/merge helpers
  context/
    pack.py               # ContextPack and ContextBlock dataclasses
    builder.py            # Build ContextPack from repos and turn input
    selection.py          # World/story/thread selection policies
  agents/
    base.py               # AgentResult, Agent interface, TurnPipelineState
    action_judge.py       # Evaluate player action and dice/state needs
    context_curator.py    # Build and explain context pack
    dungeon_master.py     # Main DM generation
    continuity_critic.py  # Detect contradictions and protocol violations
    response_evaluator.py # Evaluate next-action choice quality
    state_keeper.py       # Extract/apply pending state and memory updates
    pipeline.py           # Orchestrate one turn
  llm/
    client.py             # Existing OpenAI-compatible transport
    providers.py          # Provider definitions and presets, including DeepSeek
  engine/
    dice.py               # Existing dice parser/roller
    parser.py             # Existing DM protocol parser
    guardrails.py         # Existing validation and future game safety checks
  db/
    repos/                # Persistence adapters
  web/
    routes/               # Thin HTTP layer
    viewmodels/           # Page-specific view data shaping
    templates/
    static/
```

This structure can be introduced incrementally. Existing modules do not need to be deleted in the first pass; the first milestone should route new turn logic through `context/` and `agents/` while keeping the old public routes stable.

## Project Knowledge And Agent Docs

The redesign must include documentation as part of the architecture, not as an afterthought. Coding agents should be able to enter the repository, read the root docs, and know which files own which responsibilities.

Required agent-facing documents:

- `AGENTS.md`: the primary coding-agent rulebook for repository facts, red lines, validation commands, and active redesign pointers.
- `AGENT.md`: a thin compatibility pointer to `AGENTS.md`, kept intentionally small to avoid split-brain instructions.
- `README.md`: user/developer entry point for setup, launch, and current capabilities.
- `docs/ARCHITECTURE.md`: current-state architecture, updated after structural changes land.
- `docs/RUNBOOK.md`: local run, smoke test, backup/reset, and troubleshooting instructions.
- `docs/superpowers/specs/2026-06-15-one-person-dnd-system-redesign.md`: target-state redesign spec.

Documentation maintenance rules:

- When moving code into `domain/`, `context/`, or `agents/`, update `AGENTS.md` structure boundaries in the same change.
- When adding a provider, route, config key, DB table, or runtime file, update the docs that expose it to users and future agents.
- Keep `AGENTS.md` concise. Put deep architecture and product rationale in `docs/`, not in root agent instructions.
- Do not let `AGENT.md` become a second rulebook; it should continue pointing to `AGENTS.md`.

## Turn Pipeline

The target turn pipeline is:

```text
PlayerAction
  -> ActionJudgeAgent
  -> ContextCuratorAgent
  -> DungeonMasterAgent
  -> ContinuityCriticAgent
  -> ResponseEvaluatorAgent
  -> StateKeeperAgent
  -> Persisted TurnResult
  -> UI render/update
```

### PlayerAction

The HTTP route converts form data into a `PlayerAction` object:

- `campaign_id`
- `session_id`
- `text`
- `manual_tags`
- `extra_context`
- `submitted_at`

Routes should not assemble prompt blocks directly.

### ActionJudgeAgent

Purpose:

- Classify action type: exploration, social, combat, rest, inventory, meta, unsafe/unsupported.
- Detect dice expressions already present in text.
- Suggest whether a roll is needed when no explicit roll is present.
- Mark possible player-overreach, such as declaring NPC outcomes or rewriting world facts.

Initial implementation:

- Deterministic rules only.
- Reuse `engine.dice.roll_events_from_text`.
- Produce an `ActionAssessment` included in `ContextPack`.

### ContextCuratorAgent

Purpose:

- Build one `ContextPack`.
- Include world entries by manual tags and simple keyword matches.
- Include current scene, pinned world notes, character state, open threads, summaries, recent turns, dice, and action assessment.
- Apply `[memory].context_chars_for_prompt` before prompt construction, keeping core context ahead of low-priority memories.
- Return a `recalled_context` list for the UI with `status=included` or `status=skipped` so trimmed recalls are visible but not mistaken for prompt input.

Initial implementation:

- No extra LLM call.
- Move logic out of `engine.orchestrator.build_turn_messages_and_preview`.

### DungeonMasterAgent

Purpose:

- Convert `ContextPack` + `PlayerAction` into LLM messages.
- Call the active model.
- Support streaming and non-streaming entry points.
- Keep the existing delimiter protocol in the first phase.

Initial implementation:

- Reuse `OpenAICompatClient`.
- Keep `ensure_dm_protocol_output` for non-streaming.
- Streaming must not add a second repair LLM call.

### ContinuityCriticAgent

Purpose:

- Check DM output against hard rules and known state.
- Detect missing required sections, impossible state changes, or obvious world contradiction.
- Decide whether to accept, repair, warn, or convert to pending review.

Initial implementation:

- Deterministic checks only:
  - required delimiter presence,
  - empty narration detection,
  - malformed state delta detection,
  - contradiction warning hooks reserved for later.

### ResponseEvaluatorAgent

Purpose:

- Evaluate the DM's next-step reaction after the response has been parsed.
- Detect repeated, vague, or non-actionable choices that would stall solo play.
- Detect choices that announce player success, failure, rewards, kills, or NPC compliance instead of offering an action to attempt.

Initial implementation:

- Deterministic checks only.
- Non-streaming turns may use these warnings in the same single playability repair pass as Critic warnings.
- Streaming turns surface warnings to the UI but must not make a second LLM call after the stream ends.

### StateKeeperAgent

Purpose:

- Persist turn log, memory suggestion, state change requests, thread update requests, and summary rollups.
- Keep player approval in the loop for state and thread mutations.

Initial implementation:

- Move `persist_turn` responsibilities behind an agent-like interface.
- Preserve current DB schema unless a small additive table is needed for agent traces.

## ContextPack Contract

`ContextPack` is the system's core continuity contract.

```python
@dataclass(frozen=True)
class ContextBlock:
    kind: str
    title: str
    content: str
    source: str
    priority: int = 0
    tokens_hint: int | None = None

@dataclass(frozen=True)
class ContextPack:
    campaign_id: int
    session_id: int
    action_text: str
    blocks: list[ContextBlock]
    recalled_world: list[dict]
    dice_events: list[DiceEvent]
    assessment: ActionAssessment
```

Required block kinds:

- `system_rules`
- `world_bible`
- `plot_threads`
- `story_memory`
- `character_state`
- `scene_state`
- `dice`
- `action_assessment`
- `recent_turns`
- `cheat_directive`

The UI should be able to show which WorldBible and story blocks were recalled for the turn.

## DeepSeek Provider Design

DeepSeek should be a provider preset, not a separate transport in the first phase.

Provider definition:

```python
ProviderPreset(
    id="deepseek",
    label="DeepSeek",
    provider="openai_compat",
    base_url="https://api.deepseek.com/v1",
    default_model="deepseek-chat",
    allows_empty_api_key=False,
)
```

UI behavior:

- `/models` offers provider options: OpenAI-compatible custom, DeepSeek.
- Selecting DeepSeek fills base URL and model defaults.
- The saved DB profile still stores provider/base URL/model/API key so existing code can load it.

Transport behavior:

- `OpenAICompatClient` remains responsible for `/chat/completions`.
- If DeepSeek later needs provider-specific error handling, add it as a small adapter in `llm/providers.py`.

## UI Information Architecture

### Global navigation

Use player-facing labels:

- Play
- Adventure
- Character
- World
- Threads
- Models

Hide or de-emphasize legacy `/setup`; the recommended model setup path is `/models`.

### Home

Home should be a launch dashboard:

- Current adventure/session.
- Model readiness.
- Primary action: continue playing.
- Secondary actions: create adventure, manage model.
- No split between old config and new model setup.

### Game page

The game page should become a play cockpit:

Main column:

- Scene title and short status.
- Story transcript.
- Player action composer.
- Suggested choices from the last DM response.
- Dice panel close to the action composer.

Right panel tabs:

- Character: HP, gold, inventory, notes, pending state changes.
- World: pinned rules, recalled context, WorldBible quick links.
- Threads: open plot threads and next steps.
- System: model, session, snapshots, cheat directive, advanced JSON.

Mobile:

- Main column first.
- Right panel becomes bottom tabs or collapsible sections.
- No horizontal overflow.

### Admin pages

Saves, models, world, and threads should be usable management pages, but not the emotional center of the app. They should use:

- Clear empty states.
- Primary/secondary/danger button hierarchy.
- Cards for repeated items, not nested cards for every section.
- Tables only when horizontal scanning is genuinely useful.

## Data Model Changes

First phase should avoid destructive migrations.

Recommended additive tables:

```sql
CREATE TABLE IF NOT EXISTS turn_agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_log_id INTEGER,
  session_id INTEGER NOT NULL,
  agent_name TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json_text TEXT,
  output_json_text TEXT,
  error_text TEXT,
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (turn_log_id) REFERENCES turn_logs(id) ON DELETE SET NULL
);
```

This table is useful but not required for the first implementation if it slows the first milestone. If added, it should be optional for UI display.

## Phased Delivery

### Phase 1: Skeleton That Changes the Shape

Deliver:

- New `domain/`, `context/`, `agents/`, and `llm/providers.py` modules.
- `ContextPack` and deterministic `ActionJudgeAgent` / `ContextCuratorAgent`.
- `TurnPipeline` that wraps existing DM generation and persistence.
- Existing `/game/turn` and `/game/turn/stream` call into the pipeline.
- DeepSeek provider preset on `/models`.
- Game page information architecture improved enough that play is the primary task.
- Mobile layout no longer horizontally overflows on `/`, `/game`, `/saves`, `/models`, `/new`.
- `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, and `docs/RUNBOOK.md` updated to match the new structure and DeepSeek/provider behavior.

Acceptance:

- Existing tests pass.
- New tests cover provider presets, action assessment, context pack assembly, and pipeline behavior with a fake DM client.
- Manual smoke test can create/select a model profile, open `/game`, submit a deterministic/fake turn in tests, and inspect recalled context.

### Phase 2: Playability and Character State

Deliver:

- Human-friendly character panel replacing raw JSON as the default.
- Inventory, HP, gold, notes, and conditions as structured fields.
- Pending state changes rendered as readable diffs.
- Better new-adventure flow that creates starter world, character, scene, and initial thread together.
- Open thread updates can be reviewed and applied from the game page.

Acceptance:

- A player can start an adventure without touching raw JSON.
- State changes remain reviewable before applying.
- Story continuity survives at least 20 turns in a scripted test using fake LLM output.

### Phase 3: LLM-Backed Critic and Richer Agents

Deliver:

- Optional LLM-backed continuity critic.
- Optional LLM-backed action judge for ambiguous actions.
- Agent trace UI for why a response was accepted, repaired, or flagged.
- Better context budget strategy.

Acceptance:

- Critic can flag a known contradiction in tests with a fake provider.
- The game still works with all critic features disabled.

### Phase 4: Visual Polish and Long Campaign Ergonomics

Deliver:

- Polished responsive UI.
- Better transcript rendering, choice buttons, scene summaries, and session timeline.
- Search/filter for WorldBible, StoryJournal, and Threads.
- Snapshot restore/fork UI with clearer risk messaging.

Acceptance:

- Desktop and mobile screenshots show no horizontal overflow.
- Primary player workflows are reachable in one or two clicks from the game page.

## First Implementation Scope

The next implementation plan should target Phase 1 only. It should not attempt to finish the entire vision in one pass.

Concrete first-pass requirements:

1. Add provider preset support with DeepSeek.
2. Add `domain.actions`, `context.pack`, `context.builder`, and deterministic agent modules.
3. Route non-streaming turn through `TurnPipeline`.
4. Route streaming turn through the same pipeline stages up to the streaming LLM call, preserving the no-second-repair rule.
5. Add unit tests for the new pure-Python pieces.
6. Improve game page layout and global responsive CSS enough to remove the known mobile overflow.
7. Update `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, and `docs/RUNBOOK.md` after code changes.

## Non-Goals For Phase 1

- Full visual redesign of every page.
- Full DND 5e rules engine.
- Autonomous background agents.
- Destructive database migrations.
- Replacing FastAPI/Jinja2.
- Requiring a real DeepSeek key in automated tests.

## Open Decisions

1. Whether to keep `/setup` as a hidden legacy route or remove it from navigation.
2. Whether Phase 1 should add `turn_agent_runs` immediately or defer trace persistence.
3. Whether the first UI pass should use tabs in the game sidebar or simpler collapsible sections.
4. Whether action judging should ever block a player action, or only warn and let the player continue.

Recommended defaults:

- Keep `/setup` route but remove it from primary navigation.
- Defer `turn_agent_runs` until the pipeline shape is stable.
- Use sidebar tabs on desktop and collapsible sections on mobile.
- Warn rather than block player actions in Phase 1.
