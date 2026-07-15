# Runbook

This runbook is for local development, smoke testing, backups, and troubleshooting.

## Install

Use Python 3.12.

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Run Locally

```bash
python -m one_person_dnd --no-browser
```

Open:

```text
http://127.0.0.1:8000
```

Override port:

```bash
python -m one_person_dnd --port 8010 --no-browser
```

## Configure LLM

Recommended path:

1. Open `/models`.
2. Review existing profile cards first. If none is suitable, expand `添加模型`.
3. Use the DeepSeek quick-start option for the common path; it submits `base_url = https://api.deepseek.com/v1` and `model = deepseek-chat`.
4. For custom OpenAI-compatible servers, open the advanced custom form, then set `base_url`, `api_key`, `model`, and timeout.
5. Click test.
6. Set the profile active.

When editing an existing profile, leave the API Key field blank to keep the stored key. The edit form should not render the saved key back into the page.

Legacy path:

1. Copy `api_config.example.ini` to `api_config.ini`.
2. Fill `[llm] base_url`, `api_key`, and `model`.
3. Start the app; `/models` will import the legacy `[llm]` config as `默认配置` if no DB profile exists.

`api_key` may be empty for local OpenAI-compatible servers. The client will omit the `Authorization` header when the key is blank.

## Smoke Test

After a code or dependency change:

```bash
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
python -m one_person_dnd --no-browser
```

If the package is not installed in the current shell, use:

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

Then check:

- `/` loads and reports LLM configured when an active DB profile exists from `/models`, even if legacy `api_config.ini [llm]` is absent.
- `/` leads with the active campaign, current chapter, character/DM state, recent story, and last-played time; `继续故事` is primary and `新冒险` is secondary.
- `/models` lists existing profile cards before the folded creation area; DeepSeek appears first inside creation, custom OpenAI-compatible fields remain advanced, and blank edit keys preserve stored credentials without rendering them.
- `/saves` lists existing adventures and chapters before folded creation forms. Restoring a snapshot must show a destructive confirmation and create an automatic safety snapshot before changing current state.
- `/memory/world` loads.
- `/game` loads with a story-first desktop layout. Empty chapters show the composer before empty history; chapters with turns show history first. The latest DM choices appear next to the composer and only fill the textarea, while historical choices are collapsed. Action assessment and dice stay under the player action; recalled context stays in World; critic/response diagnostics stay in System. At 1280×720, 1920×1080, and 2560×1440 there must be no horizontal page overflow, the sidebar should remain about 400px within its draggable limits, long history must scroll internally, and the composer must remain reachable. The maximum page content width is about 2160px. The pending-review callout remains hidden at zero, Cmd/Ctrl+Enter obeys the visible send-button state, and character mutation forms keep visible polite submission feedback.

With a working LLM profile:

- `/models` test returns a response.
- `/new` can produce an editable proposal, generate a readable preview, and create a new campaign/first session without mutating the previously active save.
- `/game` can submit a turn and append a DM response; any DM choice buttons should fill the player input when clicked.
- `/character/panel` shows a readable character overview when a character sheet exists, including abilities, inventory, conditions, and notes; HP/gold quick adjustment and status/inventory/note saving should preserve existing character fields, while raw JSON remains available in the advanced section.

## Backup and Reset Local Data

Runtime data is local and ignored by Git:

```text
api_config.ini
.one_person_dnd/one_person_dnd.sqlite3
```

Backup:

```bash
cp api_config.ini api_config.ini.backup
cp .one_person_dnd/one_person_dnd.sqlite3 .one_person_dnd/one_person_dnd.sqlite3.backup
```

Reset the database only:

```bash
mv .one_person_dnd/one_person_dnd.sqlite3 .one_person_dnd/one_person_dnd.sqlite3.bak
python -m one_person_dnd --no-browser
```

Reset config only:

```bash
mv api_config.ini api_config.ini.bak
cp api_config.example.ini api_config.ini
```

Do not run destructive reset commands unless the user explicitly wants to discard local saves.

## Troubleshooting

### Startup shows missing python-multipart

Install dependencies and restart:

```bash
pip install -r requirements.txt
python -m one_person_dnd --no-browser
```

### Port 8000 is already in use

Run on another port:

```bash
python -m one_person_dnd --port 8010 --no-browser
```

### LLM test fails with 404

Check `base_url`.

Accepted examples:

```text
http://localhost:8000/v1
http://localhost:8000/v1/chat/completions
```

The client appends `/chat/completions` unless the URL already ends with it.

### LLM test fails with authorization errors

Check that the API key belongs to the selected provider. For local servers with no key, leave `api_key` blank; the client will not send a bearer token.

### DeepSeek test fails

Check that the active profile uses `provider = deepseek`, `base_url = https://api.deepseek.com/v1`, a non-empty API key, and a valid model such as `deepseek-chat`.

### Streaming response appears stuck

Some OpenAI-compatible providers do not reliably send `[DONE]` or close the stream. The client treats read inactivity as end-of-stream only after receiving tokens. Increase `timeout_seconds` in the active profile if long pauses are expected.

Do not add a second non-streaming repair request to the streaming route; see `AGENTS.md`.

### DM response is not split into choices

The parser expects exact delimiter lines:

```text
===NARRATION===
===CHOICES===
===DM_NOTES===
===MEMORY===
```

Non-streaming turns can attempt one delimiter repair call and, after `ContinuityCriticAgent` plus `ResponseEvaluatorAgent` review, one additional playability repair call for empty narration, out-of-range choice counts, duplicate choices, vague choices, or choices that announce player success/results. Streaming turns parse and evaluate best-effort after the stream ends and must not make the Critic/ResponseEvaluator repair call.

### DM choices are repetitive or declare outcomes

Check `src/one_person_dnd/agents/response_evaluator.py`. It should warn with `duplicate_choices`, `non_actionable_choice`, or `choice_declares_outcome`, and `TurnPipeline.run_non_streaming()` may use those warnings for the single playability repair call. Streaming output should only surface `TurnResult.response_warnings` as “反应评估”; it must not issue a second LLM request after the stream ends.

### State changes do not apply automatically

This is expected. DM `===STATE_DELTA===` creates a pending request. The player applies or rejects it from the character panel. The panel uses `domain.state_changes.preview_state_delta()` to show HP/gold/inventory-style previews where possible, then `/character/change/apply` uses `guardrails.validate_state_delta_json()` and `domain.state_changes.merge_state_delta()` before writing the character sheet.

Malformed `STATE_DELTA` JSON should not create a pending request on either non-streaming or streaming turns. `ContinuityCriticAgent` emits `malformed_state_delta`, and `TurnPipeline.persist_dm_output()` suppresses that structured delta before persistence while keeping the raw DM output in `turn_logs`. Do not include `malformed_state_delta` in the automatic Critic repair set; state deltas must stay reviewable instead of silently rewritten. Critic warnings are also carried in `TurnResult.critic_warnings` and rendered as “DM 审查” for newly generated turns. Streaming still must not make a second LLM repair call; it only reuses the shared post-stream critic/persistence step.

The character panel and turn prompt share the same parser: `domain.characters.summarize_character_sheet()`. If HP/gold/inventory/conditions/notes appear wrong, inspect the active session's `character_sheets.json_text` and make sure the first `party` entry or top-level legacy fields contain those values.

`/character/quick_adjust` and `/character/quick_state` should preserve top-level legacy sheets. `quick_state` should write player-entered items to `inventory`; if an item only appears under `notes`, inspect the status/inventory form and `web/routes/character.py`. If a legacy sheet unexpectedly gains a new `party[0]` that shadows top-level fields, check the primary-character selection helper in `web/routes/character.py`.

If an approved partial party delta unexpectedly removes fields, check that the apply path still calls `merge_state_delta()` rather than a route-local deep merge or a plain list replacement.

### Prompt context appears duplicated

Check `src/one_person_dnd/context/builder.py` first. Web turn routes should pass only the optional per-turn extra context field and enabled cheat directive into `TurnPipeline`; current scene, session state, pinned world notes, character sheet summary, dice, and action assessment are owned by ContextPack assembly.

Legacy callers that import `engine.run_turn()` should still follow the same path, because `run_turn()` is a compatibility wrapper over `TurnPipeline.run_non_streaming()`. If prompt behavior diverges between old and new entrypoints, check for a reintroduced prompt builder in `engine/orchestrator.py`.

### Recalled context is missing from the game page

Check the full path instead of only `recalled_world`: `context.builder._build_recalled_context()` should populate `ContextPack.recalled_context`; `TurnPipeline.prepare_messages()` should return it; `TurnPipeline.persist_dm_output()` and `TurnResult` should keep it; `web/routes/game.py` should send it as `recalled_context` in both non-streaming template context and streaming final JSON. The server partial and inline streaming renderer should both render the “本回合参考” block.

### Recalled context is shown as skipped

This means the block was recalled but not injected into the prompt because `[memory].context_chars_for_prompt` was exhausted. Check `api_config.ini [memory]` first, then `context.builder._apply_context_budget()`. Character state, scene state, dice, action assessment, cheat directives, and pinned world notes should win over low-priority `story_memory`; if the UI shows important core context as “已裁剪”, re-check block priorities and the core-block predicate.

### Thread updates stay player-approved

This is expected. DM `===THREAD_UPDATES===` is persisted as a pending request. The character/adventure review panel shows a readable preview and lets the player apply or reject it. Applying uses `domain.thread_updates.apply_thread_updates_json()` and updates `plot_threads`; malformed JSON or unsupported status values are rejected with an error on the request.

## CI Parity

GitHub Actions runs:

```bash
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
```

Keep local verification aligned with these commands unless the workflow changes.
