# AGENTS.md

本文件是后续 Agent 在本仓库工作的操作手册。先读 `README.md` 获取用户视角，再读本文件确认维护规则；涉及结构或排障时继续读 `docs/ARCHITECTURE.md` 和 `docs/RUNBOOK.md`。

## 项目事实

- 这是一个 Python 3.12、`src/` layout 的 FastAPI + Jinja2 本地 Web 应用。
- 启动入口是 `python -m one_person_dnd`，实现位于 `src/one_person_dnd/launcher.py`。
- 本地配置是项目根 `api_config.ini`，运行时数据库是 `.one_person_dnd/one_person_dnd.sqlite3`。二者都在 `.gitignore` 中，不要提交。
- LLM 当前通过 OpenAI-compatible `/chat/completions` transport 工作；`openai_compat` 和 `deepseek` 已有 provider preset，DeepSeek 默认 `https://api.deepseek.com/v1` + `deepseek-chat`。
- 测试框架是标准库 `unittest`，CI 命令见 `.github/workflows/ci.yml`。

## 当前重构状态

- Phase 1 已引入 `domain/`、`context/`、`agents/`、`llm/providers.py`，非流式和流式回合都复用 `TurnPipeline` 的 context 准备路径；历史、非流式 partial 和流式 final 的浏览器回合数据统一经 `web/turn_presenter.py` 组装。当前回合主路径还会在 LLM 前经 `adjudication.ActionAdjudicator` 冻结并提交一次可重放的属性检定。
- 每次推进结构、模型 provider、UI 信息架构或运行方式时，同步更新本文件、`README.md`、`docs/ARCHITECTURE.md` 和 `docs/RUNBOOK.md` 中受影响的部分。
- `AGENT.md` 只作为兼容入口指向本文件，不要把它扩写成第二套规则。
- 不要提交本地 Coding Agent / IDE 工具产物，例如 `.cursor*`、`.codex/`、`.claude/`、`.agents/`、`.vscode/`、`.idea/`、`docs/superpowers/`。

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
- Web 回合展示合同放在 `src/one_person_dnd/web/turn_presenter.py`。路由和历史读取都应先生成同一份 canonical turn 字典；不要在 `game.py` 的三个分支分别序列化掷骰、行动判定、诊断和待审状态。
- Domain objects live in `src/one_person_dnd/domain/`.
- 属性检定的公开入口只放在 `src/one_person_dnd/adjudication/`：调用方使用 `ActionAdjudicator.adjudicate(AdjudicationRequest)`，不要在 route、prompt builder 或 Agent 中自行拼 ability/PB/DC/优劣势/骰点。首版只覆盖有失败意义的探索/社交 ability check；攻击、豁免和完整战斗必须明确保持 unsupported。
- Turn context assembly lives in `src/one_person_dnd/context/`.
- Turn agents and the shared pipeline live in `src/one_person_dnd/agents/`.
- DM next-action response quality checks live in `src/one_person_dnd/agents/response_evaluator.py`; keep them separate from protocol/JSON checks in `ContinuityCriticAgent`.
- LLM provider presets live in `src/one_person_dnd/llm/providers.py`; DeepSeek reuses OpenAI-compatible transport. `/models` is browse-first: existing profiles render as readable cards before a progressively disclosed creation area. DeepSeek remains the first quick-start option inside that creation area, with custom OpenAI-compatible endpoints behind the advanced/custom form. Editing an existing profile with a blank API Key must preserve the stored key, templates must never render saved keys back into an input value, and password fields should use `autocomplete="new-password"`.
- Character sheet parsing and prompt summaries live in `src/one_person_dnd/domain/characters.py`; do not add ad hoc character JSON parsing in routes or prompt builders. The shared summary includes HP/gold/inventory plus abilities, conditions, and notes for both prompt context and the character panel.
- Character sheet change previews and canonical JSON merge behavior live in `src/one_person_dnd/domain/state_changes.py`; use `preview_state_delta()` for review UI and `merge_state_delta()` when applying approved deltas.
- 数据库迁移只改 `src/one_person_dnd/db/schema.py`，按 `SCHEMA_VERSION` 顺序追加 `_apply_schema_vN`，不要跳号。
- 数据库连接统一经 `db/conn.py`，保持外键、WAL、NORMAL synchronous 和 5 秒 busy timeout；不要在 route 中自行 `sqlite3.connect()`。
- DB 读写应通过 `src/one_person_dnd/db/repos/` 中的 repo 模块，避免把 SQL 散进模板或上层业务。
- 回合构建、上下文召回和 Agent 编排放在 `src/one_person_dnd/context/` 与 `src/one_person_dnd/agents/`；`engine/orchestrator.py` 只保留协议修复、持久化、摘要 rollup 和兼容 `run_turn()` wrapper。不要在路由或 `orchestrator.py` 里重新拼一套 turn prompt builder。
- Prompt 协议集中在 `src/one_person_dnd/engine/prompt_builder.py`，解析集中在 `src/one_person_dnd/engine/parser.py`。
- `web/routes/game.py` 只负责把表单变成 `PlayerAction` 和少量 route-scoped overrides。不要在路由里拼接当前场景、角色状态、置顶世界设定或掷骰结果；这些只能由 `ContextPack`/Agent pipeline 读取和注入一次。
- `ContextPack.recalled_context` 是 UI 和 Agent 调试合同：每个条目应包含 `kind`、`title`、`source`、`status`、`reason`、`preview`。`status=included` 表示已进入 prompt，`status=skipped` 表示因 `[memory].context_chars_for_prompt` 预算被裁剪，只用于解释召回；UI 需要显示“已裁剪”。非流式 partial、流式 final renderer 和 `TurnResult` 都要透传它；不要只更新旧的 `recalled_world`。`/game` 的“本回合参考”空状态也必须说明角色、世界、剧情线、故事记忆、掷骰和行动判定等来源，不要只写 WorldBible。
- `ContextPack` 在返回前按字符预算筛选 block：角色/场景/掷骰/行动判定/金手指/置顶世界设定属于核心上下文，应优先保留；低优先级 `story_memory` 应先被裁剪。改 block priority 或预算策略时，同步 `tests/test_context_pack.py`、`tests/test_prompt_builder.py` 和 `tests/test_ui_templates.py`。

## 维护注意

- SSE 路由 `POST /game/turn/stream` 在流结束后调用 `ensure_dm_protocol_output(..., max_retries=0)`。不要在流式分支追加第二次非流式修复调用，否则某些 provider 不关闭 stream 时会让前端看起来卡住。完成后的 DM 文本必须交给 `TurnPipeline.persist_dm_output()`，以复用 critic 检查和持久化规则。
- 非流式回合可以做一次协议修复：`ensure_dm_protocol_output(..., max_retries=1)`。协议修复后，`TurnPipeline.run_non_streaming()` 会运行 `ContinuityCriticAgent` 和 `ResponseEvaluatorAgent`；当 warning 属于可修复协议/可玩性问题，或下一步选项重复、过于笼统、替玩家宣布结果时，允许追加一次 playability repair prompt，再把修复后的 DM 文本交给 `persist_dm_output()`。不要对 `malformed_state_delta` 做自动重写；它仍由 `persist_dm_output()` 清空结构化 delta 并保留原始 turn log。
- `ActionJudgeAgent` 只保留旧调用方兼容分类；正常回合必须把冻结的 `AdjudicationRecord` 投影为 `ActionAssessment`。`signals` / `warnings` 仍是 prompt 和 UI 合同；改代码名时同步 `tests/test_actions.py`、`tests/test_adjudication.py`、labels、ContextPack 和两种 renderer。
- `ContinuityCriticAgent` 不只是记录警告：非流式路径会用可修复 warning 触发一次 DM 输出修复；冻结检定冲突/未结算却宣布结果也属于可修复项，repair prompt 必须重复不可变数值。`persist_dm_output()` 遇到 `malformed_state_delta` 或 `malformed_thread_updates` 时要清空对应结构化段，避免不可应用 JSON 进入待审队列。非流式和流式都应经过共享入口；流式仍不得追加修复 LLM 调用。中文显示文案统一在 `web/labels.py`。
- `ResponseEvaluatorAgent` 负责评估 DM 给出的下一步选项，而不是协议分隔符：重复选项、`继续`/`等待` 这类不可行动选项、以及“成功说服/让 NPC 立刻服从”等替玩家宣布结果的选项会进入 `TurnResult.response_warnings`，并在“系统”标签的回合诊断中显示。改 warning 代码名或修复规则时必须同步 `tests/test_response_evaluator.py`、pipeline、路由序列化。中文显示文案统一在 `web/labels.py`（`RESPONSE_WARNING_LABELS`）单一来源，Jinja partial 和流式 final renderer 都从它读取，不必再手动同步三份拷贝。流式路径仍不能为 response warnings 追加第二次 LLM 调用。
- DM 必须输出这些分隔符段：`===NARRATION===`、`===CHOICES===`、`===DM_NOTES===`、`===MEMORY===`。可选段是 `===STATE_DELTA===` 和 `===THREAD_UPDATES===`。
- `STATE_DELTA` 不直接改角色卡。它先写入 `state_change_requests`，角色面板用 `preview_state_delta()` 展示可读预览，再由 `/character/change/apply` 通过 `validate_state_delta_json` 校验并用 `merge_state_delta()` 合并。不要把原始 JSON 作为主要审查 UI。
- `THREAD_UPDATES` 不直接改剧情线。它先写入 `state_change_requests`，角色/冒险审查面板用 `preview_thread_updates_json()` 展示可读预览，再由 `/character/change/apply` 调用 `apply_thread_updates_json()` 更新 `plot_threads`。Prompt schema 必须保持 `{"updates":[...]}`；已有线程用 `id` 更新，新线程用 `title` 创建。
- `character_sheets` 是玩家属性的权威 JSON；`ContextPack` 会通过 `summarize_character_sheet()` 注入可读摘要，角色面板也复用同一摘要。`/character/quick_adjust` and `/character/quick_state` should update the same primary character object: use `party[0]` for party sheets, but preserve top-level legacy sheets instead of silently creating a competing `party[0]`. `/character/quick_state` owns structured `conditions`、`inventory` 和 `notes`，不要把玩家输入的物品只塞进 notes。
- 新冒险角色必须写入 `level`、六项 canonical ability scores（STR/DEX/CON/INT/WIS/CHA）和 `skill_proficiencies`。旧角色缺属性时检定可暂按 10 并显示 warning；含混/非法属性或参与熟练计算的非法等级必须 `needs_input` 且不掷骰。
- 角色面板里会改状态的表单（快捷改值、状态/物品/备注、角色卡保存、待确认变更应用/拒绝）必须有 `hx-indicator` 和 `role="status" aria-live="polite"` 的提交反馈，避免玩家点完不知道是否正在处理。
- 游戏页 UI 应保持 play-first，但顺序要跟随游玩状态：空章节先展示行动输入区；已有历史的章节先展示故事记录，并通过紧凑输入区保持下一步行动容易触达。桌面使用故事区与冒险面板双栏布局，内容最大宽度约 2160px，冒险面板默认约 400px、可在约 340–520px 间拖拽；故事记录框右下角提供高度拖拽手柄。故事记录高度和冒险面板宽度都按 session 存入 `localStorage`，可双击对应手柄或点“重置布局”恢复默认。本轮设计只以 1280×720、1920×1080、2560×1440 桌面尺寸为验收目标，不新增第三栏、移动端专项方案或亮色主题。行动输入和快速掷骰放在故事区下方紧凑排列；最新一回合的 DM 建议紧邻输入区横向排列，点击只填入输入框，历史建议收在对应回合下。长故事记录必须在剩余可用高度内独立滚动，不能把输入区推出视口；待确认变更为 0 时不要显示待审 callout。当前冒险没有 WorldBible 且当前章节没有置顶世界设定时，`/game` 应显示轻量世界观提醒；玩家可去 `/new` 创建新冒险、去 `/memory/world/new` 手写，或通过 `/game/world-setup/skip` 为当前 session 持久跳过。紧凑故事布局不能仅因上次偏好恢复空的高级选项展开，但有未发送的本回合额外线索草稿时仍要自动展开并聚焦；`input--compact` 在 inline form 内不能被通用 `.input { width: 100%; }` 覆盖成整行。冒险面板使用角色/世界/剧情/系统四个标签；角色卡/待确认变更默认优先展示，World tab 必须直接显示当前 campaign 的 WorldBible 条目摘要并保留置顶世界设定编辑，开放 `plot_threads` 必须直接显示在“剧情”标签中，金手指、原始 JSON、prompt 类控制和回合质量诊断放进系统或高级区。`/new` 是新冒险一级入口，顶部导航和首页不要只把玩家引向存档/管理页。
- 行动输入的 Cmd/Ctrl+Enter 快捷提交必须复用发送按钮状态：空输入、DM 未连接或回合请求进行中时不能通过快捷键绕过禁用按钮。
- 行动表单的 `attempt_id` 是技术重试合同：同一未修改草稿失败后重试必须沿用；玩家修改行动、标签或本回合线索时必须清空并生成新 id；成功后才清空。`TurnPipeline.prepare_turn()` 必须在 LLM 前 commit 裁决记录，已完成 attempt 直接重放旧 turn，不得再调模型或新增 turn。历史只能读 `adjudication_json`，不能重新掷骰。
- DM `CHOICES` 在历史回合 partial 和流式 final renderer 中都应渲染为 `data-choice-action` 按钮；最新回合建议要同步提升到输入区附近，历史回合建议默认收起。`dice_events`、`action_assessment`、`critic_warnings` 和 `response_warnings` 也要在服务器渲染 partial 和流式 final renderer 中保持一致；`dice_events` 显示在玩家行动下方，critic/response warnings 显示在“系统”标签的诊断区，不要塞进 DM 叙事。
- `/new` 的模型提案和完整生成都只是预览；只有 `/new/apply` 才创建新的 campaign 与首个 session，并写入对应世界设定和角色卡。不得复用或覆盖当前 campaign/session。提案中的冒险名、首章标题和生成后的可读预览都应允许玩家编辑，原始 JSON 只放高级区。
- `/saves/session/restore` 是整个 session 叙事的完整回退，不只是场景/角色状态：`session_snapshots.narrative_json` 保存全部 `turn_logs`/`story_journal_entries`/`plot_threads`/`session_summaries`；恢复前创建自动安全快照，再在同一事务替换叙事、清空 pending request，并从带有效原 request fingerprint 的已恢复 turn 重建 `adjudication_records`。不能保留快照之后或未完成的 attempt ledger。`narrative_json` 为 NULL 的旧快照仍只恢复状态、不删除叙事。`/saves/session/fork` 仍只复制场景/角色字段，新分支叙事为空。
- `/setup` 只作为兼容入口重定向到 `/models`，不要恢复第二套模型配置表单，也不要通过旧模板回显已保存 API Key。
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
