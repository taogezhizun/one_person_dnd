# one_person_dnd

`one_person_dnd` 是一个单人 TRPG / DND Web 应用：玩家在浏览器里行动，LLM 作为 DM 叙事、给出选项，并把战役、会话、世界设定、角色卡、剧情摘要和回合记录持久化到本地 SQLite。

## 当前能力

- 一键启动本地 Web 应用，默认打开 `http://127.0.0.1:8000`。
- 多战役、多会话存档，并支持会话快照、恢复和分叉。
- 顶部导航和首页都提供“新冒险”入口，可直接进入 LLM 新冒险向导初始化世界设定和角色卡。
- `/models` 首屏提供 DeepSeek 快速配置，只需填写 API Key；OpenAI-compatible 自定义端点保留在高级配置中，并支持多个模型 profile、连通性测试和安全编辑（编辑时留空 API Key 会保留原 Key）。
- 游戏回合支持普通响应和 SSE 流式响应；两种模式共用回合上下文、DM 输出审查、下一步反应评估和待确认状态变更流程。普通响应会在 DM 输出空叙事、选项数量不可玩或下一步选项质量较差时触发一次修复；流式响应保持不追加第二次阻塞 LLM 调用。
- 游戏回合已拆成 `PlayerAction -> ContextPack -> TurnPipeline`，由行动评估、上下文整理、DM、连续性检查、反应评估和状态持久化几个 Agent 协作；新回合会把行动类型、判定信号和越权提醒显示为“系统判定”，并在 DM 输出仍触发协议/可玩性警告时显示“DM 审查”，在下一步选项重复、笼统或替玩家宣布结果时显示“反应评估”。
- 回合上下文由 `ContextPack` 统一组装；Web 路由只传玩家行动、手动标签、本回合额外线索和会话级金手指，避免重复注入场景/角色/世界状态。新回合会把角色、世界、剧情线、故事记忆、骰子和行动判定等召回来源显示为“本回合参考”，方便玩家理解 DM 参考了什么。
- DM 输出按协议解析为叙事、行动选项、DM 备注、剧情记忆、角色状态变更建议和剧情线更新建议；状态和剧情线变更都会先进入玩家确认流程。
- DM 给出的行动选项会以按钮展示，点击后填入玩家输入框，玩家可直接编辑并发送下一步行动。
- WorldBible 世界设定、StoryJournal 剧情摘要、PlotThreads 主线线程会注入 prompt，帮助长篇冒险保持连续性。
- 游戏页按游玩状态调整主列顺序：新会话优先展示玩家行动输入区；已有历史的会话先展示故事记录，并让压缩后的行动输入区保持粘性可达。已有故事时，常见桌面宽度会让故事记录独占主行，右侧冒险面板下移；只有超宽屏才保留并排面板，避免右侧工具栏挤窄叙事。桌面和移动端都会压缩顶部状态、故事预览和行动区高度；矮桌面窗口会把故事历史限制成可滚动窗口，避免长历史把行动区推远或裁掉。小屏故事预览仍保留可读高度，不会只剩一条窄缝；紧凑故事布局不会仅因上次偏好自动展开空的高级选项，避免把快速掷骰挤出首屏。有待确认状态或剧情线更新时，会在主游玩流中提示玩家审查。
- 角色卡以 JSON 保存，但游戏页会显示可读的角色概览，包括身份、HP、金币、物品、属性、当前状态和备注；角色标签里可直接快速改 HP/金币，也可维护状态备注，原始 JSON 仍保留在高级区。
- 内置掷骰表达式识别与手动掷骰，支持 `d20`、`1d20+5`、`2d6-1` 这类格式；快速掷骰紧跟玩家行动输入，方便边行动边判定。
- 新冒险向导可用 LLM 生成世界设定和初始角色卡。

## 环境要求

- Python 3.12

## 安装

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## 启动

```bash
python -m one_person_dnd
```

启动后会按配置自动打开浏览器。禁用自动打开：

```bash
python -m one_person_dnd --no-browser
```

覆盖监听地址或端口：

```bash
python -m one_person_dnd --host 127.0.0.1 --port 8000 --no-browser
```

查看 CLI 参数：

```bash
python -m one_person_dnd --help
```

## 首次使用流程

1. 打开 `/models` 创建或选择一个模型配置。首屏的 DeepSeek 快速配置默认使用 `https://api.deepseek.com/v1` 和 `deepseek-chat`，填写 API Key 后保存即可；自定义 `base_url` 位于高级的 OpenAI-compatible 配置中，例如 `http://localhost:8000/v1`，也兼容直接填到 `/chat/completions`。
2. 打开 `/new` 用 LLM 生成初始世界设定和角色卡；需要多战役或多会话时，再到 `/saves` 创建、选择、快照或分叉。
3. 打开 `/memory/world` 录入地点、NPC、组织、规则等 WorldBible 条目，并用逗号分隔标签。
4. 打开 `/threads` 维护进行中的主线或任务线；开放剧情线也会直接显示在 `/game` 的“剧情”标签中。
5. 打开 `/game` 继续冒险。新会话会先给行动输入框和快速掷骰；已有历史会话会先显示故事记录，再给行动输入框和快速掷骰。行动文本里的掷骰表达式会被自动掷骰，并注入给 DM；系统判定会显示行动类型、可能需要掷骰或越权的信号，掷骰结果会显示在玩家行动下方；本回合参考会显示被召回的世界、角色、剧情线、故事记忆和行动判定；DM 审查会提示不完整协议、空叙事、选项数量异常或错误状态变更；反应评估会提示 DM 给出的下一步选项是否重复、太笼统或替玩家宣布结果；DM 给出的可选行动可以点击后作为下一步输入。
6. 在游戏页查看待审提示，进入冒险面板的“角色”标签确认角色卡与剧情线变更预览，并维护 HP/金币、当前状态和角色备注；在“世界”标签维护当前场景、临时状态备注和置顶世界设定；在“剧情”标签查看开放剧情线、下一步和会话入口；金手指和角色卡 JSON 位于高级区。

## 配置和本地数据

项目优先使用根目录本地文件，便于移动和备份：

- `api_config.ini`：本地配置文件，包含 `[server]`、`[llm]`、`[app]`、`[memory]` 等段；不会提交到 Git。
- `api_config.example.ini`：可提交的示例配置。
- `.one_person_dnd/one_person_dnd.sqlite3`：SQLite 运行时数据库；不会提交到 Git。

`/models` 中的 DB profile 优先于旧版 `api_config.ini [llm]`，首页和游戏页都会按同一套 active profile 判断模型是否可用。如果数据库里没有 profile，应用会把已有 `[llm]` 导入为“默认配置”。

`[memory]` 控制回合 prompt 的上下文规模：`history_turns_for_prompt` 控制最近对话轮数，`story_journal_for_prompt` 控制剧情记忆条数，`context_chars_for_prompt` 控制 `ContextPack` 注入 prompt 的上下文字符预算。超过预算的低优先级记忆会在“本回合参考”里标记为“已裁剪”，用于解释召回但不会进入本回合 prompt。

## 项目结构

```text
src/one_person_dnd/
  __main__.py              # python -m one_person_dnd 入口
  launcher.py              # CLI 参数、Uvicorn 启动、自动打开浏览器
  config.py                # api_config.ini 读写
  paths.py                 # 项目根、本地数据路径
  llm/client.py            # OpenAI-compatible chat 和 SSE client
  llm/providers.py         # DeepSeek / OpenAI-compatible provider presets
  domain/                  # PlayerAction、ActionAssessment、CharacterSummary 等领域对象
  context/                 # ContextPack、上下文选择和组装
  agents/                  # ActionJudge、ContextCurator、DM、Critic、ResponseEvaluator、StateKeeper、TurnPipeline
  engine/                  # prompt、DM 协议解析、回合编排、掷骰、guardrails
  db/schema.py             # SQLite schema 和顺序迁移
  db/repos/                # 数据访问层
  web/app.py               # FastAPI app factory
  web/routes/              # 页面和表单路由
  web/templates/           # Jinja2 模板
  web/static/style.css     # 页面样式
tests/                     # unittest 测试
```

## 开发与验证

```bash
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
```

CI 会在 Python 3.12 上执行依赖安装、源码编译和 `unittest`。

## 更多文档

- `AGENTS.md`：给后续 Agent 的项目约定、维护边界和验证命令。
- `docs/ARCHITECTURE.md`：模块、路由、数据模型、回合流程和 prompt/memory 机制。
- `docs/RUNBOOK.md`：本地运行、配置、备份/重置、排障和发布前检查。
