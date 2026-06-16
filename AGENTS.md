# AGENTS.md

本文件是后续 Agent 在本仓库工作的操作手册。先读 `README.md` 获取用户视角，再读本文件确认维护规则；涉及结构或排障时继续读 `docs/ARCHITECTURE.md` 和 `docs/RUNBOOK.md`。

## 项目事实

- 这是一个 Python 3.12、`src/` layout 的 FastAPI + Jinja2 本地 Web 应用。
- 启动入口是 `python -m one_person_dnd`，实现位于 `src/one_person_dnd/launcher.py`。
- 本地配置是项目根 `api_config.ini`，运行时数据库是 `.one_person_dnd/one_person_dnd.sqlite3`。二者都在 `.gitignore` 中，不要提交。
- LLM 当前通过 OpenAI-compatible `/chat/completions` transport 工作；`openai_compat` 和 `deepseek` 已有 provider preset，DeepSeek 默认 `https://api.deepseek.com/v1` + `deepseek-chat`。
- 测试框架是标准库 `unittest`，CI 命令见 `.github/workflows/ci.yml`。

## 当前重构目标

- 系统级目标见 `docs/superpowers/specs/2026-06-15-one-person-dnd-system-redesign.md`。
- Phase 1 已引入 `domain/`、`context/`、`agents/`、`llm/providers.py`，非流式和流式回合都复用 `TurnPipeline` 的 context 准备路径。
- 每次推进结构、模型 provider、UI 信息架构或运行方式时，同步更新本文件、`README.md`、`docs/ARCHITECTURE.md` 和 `docs/RUNBOOK.md` 中受影响的部分。
- `AGENT.md` 只作为兼容入口指向本文件，不要把它扩写成第二套规则。

## 常用命令

```bash
pip install -r requirements.txt
pip install -e .
python -m one_person_dnd --no-browser
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
```

如果当前环境尚未 `pip install -e .`，可用 `PYTHONPATH=src` 临时运行编译和测试；正式开发仍应使用 Python 3.12 并完成 editable install。

## 结构边界

- Web app factory 在 `src/one_person_dnd/web/app.py`，路由统一从 `src/one_person_dnd/web/routes/__init__.py` include。
- 每个页面/功能路由放在 `src/one_person_dnd/web/routes/*.py`，模板放在 `src/one_person_dnd/web/templates/`。
- Domain objects live in `src/one_person_dnd/domain/`.
- Turn context assembly lives in `src/one_person_dnd/context/`.
- Turn agents and the shared pipeline live in `src/one_person_dnd/agents/`.
- DM next-action response quality checks live in `src/one_person_dnd/agents/response_evaluator.py`; keep them separate from protocol/JSON checks in `ContinuityCriticAgent`.
- LLM provider presets live in `src/one_person_dnd/llm/providers.py`; DeepSeek reuses OpenAI-compatible transport. `/models` should keep DeepSeek as the first quick-start path, with custom OpenAI-compatible endpoints behind the advanced/custom form. Editing an existing profile with a blank API Key must preserve the stored key, and templates must not render saved keys back into an input value.
- Character sheet parsing and prompt summaries live in `src/one_person_dnd/domain/characters.py`; do not add ad hoc character JSON parsing in routes or prompt builders. The shared summary includes HP/gold/inventory plus abilities, conditions, and notes for both prompt context and the character panel.
- Character sheet change previews and canonical JSON merge behavior live in `src/one_person_dnd/domain/state_changes.py`; use `preview_state_delta()` for review UI and `merge_state_delta()` when applying approved deltas.
- 数据库迁移只改 `src/one_person_dnd/db/schema.py`，按 `SCHEMA_VERSION` 顺序追加 `_apply_schema_vN`，不要跳号。
- DB 读写应通过 `src/one_person_dnd/db/repos/` 中的 repo 模块，避免把 SQL 散进模板或上层业务。
- 回合构建、上下文召回和 Agent 编排放在 `src/one_person_dnd/context/` 与 `src/one_person_dnd/agents/`；`engine/orchestrator.py` 只保留协议修复、持久化、摘要 rollup 和兼容 `run_turn()` wrapper。不要在路由或 `orchestrator.py` 里重新拼一套 turn prompt builder。
- Prompt 协议集中在 `src/one_person_dnd/engine/prompt_builder.py`，解析集中在 `src/one_person_dnd/engine/parser.py`。
- `web/routes/game.py` 只负责把表单变成 `PlayerAction` 和少量 route-scoped overrides。不要在路由里拼接当前场景、角色状态、置顶世界设定或掷骰结果；这些只能由 `ContextPack`/Agent pipeline 读取和注入一次。
- `ContextPack.recalled_context` 是 UI 和 Agent 调试合同：每个条目应包含 `kind`、`title`、`source`、`status`、`reason`、`preview`。`status=included` 表示已进入 prompt，`status=skipped` 表示因 `[memory].context_chars_for_prompt` 预算被裁剪，只用于解释召回；UI 需要显示“已裁剪”。非流式 partial、流式 final renderer 和 `TurnResult` 都要透传它；不要只更新旧的 `recalled_world`。`/game` 的“本回合参考”空状态也必须说明角色、世界、剧情线、故事记忆、掷骰和行动判定等来源，不要只写 WorldBible。
- `ContextPack` 在返回前按字符预算筛选 block：角色/场景/掷骰/行动判定/金手指/置顶世界设定属于核心上下文，应优先保留；低优先级 `story_memory` 应先被裁剪。改 block priority 或预算策略时，同步 `tests/test_context_pack.py`、`tests/test_prompt_builder.py` 和 `tests/test_ui_templates.py`。

## 维护注意

- SSE 路由 `POST /game/turn/stream` 在流结束后调用 `ensure_dm_protocol_output(..., max_retries=0)`。不要在流式分支追加第二次非流式修复调用，否则某些 provider 不关闭 stream 时会让前端看起来卡住。完成后的 DM 文本必须交给 `TurnPipeline.persist_dm_output()`，以复用 critic 检查和持久化规则。
- 非流式回合可以做一次协议修复：`ensure_dm_protocol_output(..., max_retries=1)`。协议修复后，`TurnPipeline.run_non_streaming()` 会运行 `ContinuityCriticAgent` 和 `ResponseEvaluatorAgent`；当 warning 属于可修复协议/可玩性问题，或下一步选项重复、过于笼统、替玩家宣布结果时，允许追加一次 playability repair prompt，再把修复后的 DM 文本交给 `persist_dm_output()`。不要对 `malformed_state_delta` 做自动重写；它仍由 `persist_dm_output()` 清空结构化 delta 并保留原始 turn log。
- `ActionJudgeAgent` 的 `signals` / `warnings` 是 prompt 和新回合 UI 合同的一部分。新增行动类型、越权判断、需要状态变更的信号时，要同步测试 `tests/test_actions.py`，并确认 `ContextPack` 仍把 action assessment 注入 prompt，`TurnResult` / 非流式 partial / 流式 final renderer 仍显示“系统判定”。
- `ContinuityCriticAgent` 不只是记录警告：非流式路径会用它的可修复 warning 触发一次 DM 输出修复；`TurnPipeline.persist_dm_output()` 遇到 `malformed_state_delta` 时会清空结构化 state delta，避免不可应用 JSON 进入玩家待审队列；未被修复或修复后仍存在的 warnings 会进入 `TurnResult.critic_warnings`，并在新回合 UI 中显示为“DM 审查”。非流式和流式都应经过这个共享入口；改 critic warning 名称时必须同步 `TurnPipeline`、路由序列化、服务器 partial 和流式 final renderer。
- `ResponseEvaluatorAgent` 负责评估 DM 给出的下一步选项，而不是协议分隔符：重复选项、`继续`/`等待` 这类不可行动选项、以及“成功说服/让 NPC 立刻服从”等替玩家宣布结果的选项会进入 `TurnResult.response_warnings` 并在 UI 显示为“反应评估”。改 warning 名称或修复规则时必须同步 `tests/test_response_evaluator.py`、pipeline、路由序列化、服务器 partial 和流式 final renderer。流式路径仍不能为 response warnings 追加第二次 LLM 调用。
- DM 必须输出这些分隔符段：`===NARRATION===`、`===CHOICES===`、`===DM_NOTES===`、`===MEMORY===`。可选段是 `===STATE_DELTA===` 和 `===THREAD_UPDATES===`。
- `STATE_DELTA` 不直接改角色卡。它先写入 `state_change_requests`，角色面板用 `preview_state_delta()` 展示可读预览，再由 `/character/change/apply` 通过 `validate_state_delta_json` 校验并用 `merge_state_delta()` 合并。不要把原始 JSON 作为主要审查 UI。
- `THREAD_UPDATES` 不直接改剧情线。它先写入 `state_change_requests`，角色/冒险审查面板用 `preview_thread_updates_json()` 展示可读预览，再由 `/character/change/apply` 调用 `apply_thread_updates_json()` 更新 `plot_threads`。Prompt schema 必须保持 `{"updates":[...]}`；已有线程用 `id` 更新，新线程用 `title` 创建。
- `character_sheets` 是玩家属性的权威 JSON；`ContextPack` 会通过 `summarize_character_sheet()` 注入可读摘要，角色面板也复用同一摘要。`/character/quick_adjust` and `/character/quick_state` should update the same primary character object: use `party[0]` for party sheets, but preserve top-level legacy sheets instead of silently creating a competing `party[0]`.
- 角色面板里会改状态的表单（快捷改值、状态备注、角色卡保存、待确认变更应用/拒绝）必须有 `hx-indicator` 和 `role="status" aria-live="polite"` 的提交反馈，避免玩家点完不知道是否正在处理。
- 游戏页 UI 应保持 play-first，但顺序要跟随游玩状态：空会话先展示行动输入区；已有历史的会话先展示故事记录，并通过紧凑粘性输入区保持下一步行动容易触达。故事优先模式下，常见桌面宽度（含 1920px 级窗口）应让故事记录独占主行，冒险面板下移；只有超宽屏才保留并排面板。行动输入和快速掷骰放在下方紧凑排列，不要重新做右侧工具栏把叙事挤窄；移动端也不能把故事记录压成一条几乎不可读的窄缝。快速掷骰必须紧跟行动输入区，不要被空历史或管理面板隔开。桌面 1280x720 和 520px 以下的小屏布局都要压缩顶部状态条、故事预览、行动框和快速掷骰高度，避免会话/状态 chrome 把行动循环推到首屏下方；矮桌面 story-first 卡片不能用固定高度加 `overflow: hidden` 裁掉行动输入或快速掷骰。紧凑故事布局不能仅因上次偏好恢复空的高级选项展开，但有未发送的本回合额外线索草稿时仍要自动展开并聚焦；`input--compact` 在 inline form 内不能被通用 `.input { width: 100%; }` 覆盖成整行。冒险面板使用角色/世界/剧情/系统四个标签；角色卡/待确认变更默认优先展示，开放 `plot_threads` 必须直接显示在“剧情”标签中，金手指、原始 JSON、prompt 类控制放进系统或高级区。`/new` 是新冒险一级入口，顶部导航和首页不要只把玩家引向存档/管理页。
- 行动输入的 Cmd/Ctrl+Enter 快捷提交必须复用发送按钮状态：空输入、DM 未连接或回合请求进行中时不能通过快捷键绕过禁用按钮。
- DM `CHOICES` 在历史回合 partial 和流式 final renderer 中都应渲染为 `data-choice-action` 按钮；`dice_events`、`action_assessment`、`critic_warnings` 和 `response_warnings` 也要在服务器渲染 partial 和流式 final renderer 中保持一致。`dice_events` 必须显示在玩家行动消息下方，不要塞进 DM 叙事消息。改回合 UI 时两条路径必须一起更新。
- `/threads` 页面不要嵌套 `<form>`；关闭/重开等状态操作应是更新表单之外的独立表单。
- `/threads` 页面仍是手动维护入口；DM 建议的 `THREAD_UPDATES` 只能通过玩家确认后的 pending request 应用。
- `.one_person_dnd/` 是用户本地存档，调试时可以复制备份，但不要随手删除或纳入提交。
- `api_config.ini` 可能含 API key。日志、测试输出、文档示例都不要泄露真实密钥。
- README 面向玩家/开发者入口，`AGENTS.md` 面向 Agent 维护规则，`docs/` 面向结构和运维细节；不要把同一段长说明复制到多处。

## 验证标准

改业务逻辑后至少运行：

```bash
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
```

未安装包时的临时验证命令：

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

改 Web 路由、模板或启动逻辑时，还要本地启动：

```bash
python -m one_person_dnd --no-browser
```

然后访问 `http://127.0.0.1:8000`，至少检查首页、`/models`、`/saves`、`/game` 能加载。需要真实 LLM 的功能可用 `/models` 的测试按钮验证。

## 文档更新规则

- 新增页面或路由：更新 `README.md` 的能力/使用流程，更新 `docs/ARCHITECTURE.md` 的路由表。
- 新增配置项：更新 `api_config.example.ini`、`README.md` 配置说明和 `docs/RUNBOOK.md`。
- 新增表或迁移：更新 `docs/ARCHITECTURE.md` 数据模型，并在 `AGENTS.md` 保留必要维护规则。
- 新增排障经验：优先放 `docs/RUNBOOK.md`，只有会影响下次 Agent 改代码的红线才放回本文件。
