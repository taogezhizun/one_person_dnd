# one_person_dnd

中文 | [English](README.en.md)

`one_person_dnd` 是一个本地运行的单人 TRPG / DND Web 应用。你在浏览器里描述行动，LLM 扮演 DM 讲述剧情、给出可选行动，并把冒险、会话、世界设定、角色卡、剧情线和回合记录保存到本地 SQLite。

这个项目适合用来跑个人文字冒险、测试 LLM 叙事流程，或者作为“本地优先的单人 DND 桌面 Web 工具”继续改造。

## 你可以用它做什么

- 创建多个冒险和会话，保留不同存档、快照、恢复点和分支。
- 用 DeepSeek 或 OpenAI-compatible 模型作为 DM。
- 通过“新冒险”向导生成初始世界设定和角色卡。
- 在 `/game` 页面持续游玩：阅读故事、输入行动、点击 DM 给出的可选行动、快速掷骰。
- 维护世界设定、剧情线、角色状态、物品、HP、金币和备注。
- 审查 DM 建议的角色卡变更和剧情线更新，确认后才写入存档。
- 查看“本回合参考”，理解 DM 这次参考了哪些角色、世界、剧情、掷骰和行动判定信息。

## 快速开始

要求：Python 3.12。

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m one_person_dnd
```

默认会打开：

```text
http://127.0.0.1:8000
```

如果不想自动打开浏览器：

```bash
python -m one_person_dnd --no-browser
```

指定地址或端口：

```bash
python -m one_person_dnd --host 127.0.0.1 --port 8000 --no-browser
```

## 第一次游玩

1. 打开 `/models`，配置一个模型。
   - 推荐先用首屏的 DeepSeek 快速配置：填入 API Key 后保存。
   - 自定义 OpenAI-compatible 服务可以在高级配置里填写 `base_url`、`model` 和可选 API Key。
2. 打开 `/new`，让 LLM 生成初始世界设定和角色卡。
3. 打开 `/game` 开始行动。新会话会先显示行动输入区和快速掷骰；已有历史的会话会先显示故事记录，再显示下一步行动区。
4. 如果 DM 提供可选行动，可以直接点击按钮带入输入框，再编辑或发送。
5. 如果 DM 提出角色状态或剧情线变更，先在游戏页的冒险面板中预览，再选择应用或拒绝。

## 常用页面

| 页面 | 用途 |
| --- | --- |
| `/models` | 管理模型配置、测试连接、选择当前 DM。 |
| `/new` | 生成新冒险的世界设定和角色卡。 |
| `/game` | 主游玩页面。 |
| `/saves` | 管理冒险、会话、快照、恢复和分叉。 |
| `/memory/world` | 管理 WorldBible 世界设定。 |
| `/memory/story` | 查看剧情摘要。 |
| `/threads` | 管理剧情线和任务线。 |

## 游戏页怎么读

- **故事对话**：当前冒险的主要阅读区域。
- **下一步行动**：输入你想做的事；输入中包含 `d20`、`1d20+5`、`2d6-1` 这类表达式时，系统会自动掷骰并把结果交给 DM。
- **可选行动**：DM 给出的下一步建议，可以点击后再编辑。
- **系统判定**：系统对玩家行动的初步分类，例如探索、社交、战斗，或提醒该行动可能需要 DM 判定。
- **DM 审查 / 反应评估**：当模型输出格式不完整、选项不可玩、选项重复或替玩家宣布结果时，页面会显示提示。
- **本回合参考**：展示本回合进入 prompt 或被裁剪的角色、世界、剧情线、故事记忆、掷骰和行动判定信息。
- **冒险面板**：集中管理角色、世界、剧情线和系统工具。

## 本地数据和配置

项目默认把运行数据放在仓库目录内，方便备份和迁移：

- `api_config.ini`：本地配置，可能包含 API Key，不会提交到 Git。
- `.one_person_dnd/one_person_dnd.sqlite3`：本地 SQLite 数据库，不会提交到 Git。
- `api_config.example.ini`：可提交的配置示例。

`/models` 中保存的模型 profile 优先于旧版 `api_config.ini [llm]`。如果数据库里还没有 profile，应用会把已有 `[llm]` 配置导入为“默认配置”。

## 备份

```bash
cp api_config.ini api_config.ini.backup
cp .one_person_dnd/one_person_dnd.sqlite3 .one_person_dnd/one_person_dnd.sqlite3.backup
```

不要把 `api_config.ini`、`.one_person_dnd/` 或真实 API Key 提交到 Git。

## 开发者入口

常用验证命令：

```bash
python -m compileall -q src/one_person_dnd
python -m unittest discover -s tests -p "test*.py"
```

如果当前环境还没有 `pip install -e .`，可以临时使用：

```bash
PYTHONPATH=src python -m compileall -q src/one_person_dnd
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py"
```

项目结构：

```text
src/one_person_dnd/
  launcher.py              # CLI 参数、Uvicorn 启动、自动打开浏览器
  config.py                # api_config.ini 读写
  llm/                     # OpenAI-compatible client 和 provider presets
  domain/                  # PlayerAction、ActionAssessment、CharacterSummary 等领域对象
  context/                 # ContextPack、上下文选择和组装
  agents/                  # ActionJudge、ContextCurator、DM、Critic、ResponseEvaluator、StateKeeper、TurnPipeline
  engine/                  # prompt、DM 协议解析、回合编排、掷骰、guardrails
  db/                      # SQLite schema、迁移和 repo 层
  web/                     # FastAPI routes、Jinja2 templates、static assets
tests/                     # unittest 测试
```

更多维护文档：

- [AGENTS.md](AGENTS.md)：给后续 Agent 的项目约定、维护边界和验证命令。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块、路由、数据模型、回合流程和 prompt/memory 机制。
- [docs/RUNBOOK.md](docs/RUNBOOK.md)：本地运行、配置、备份、排障和发布前检查。
