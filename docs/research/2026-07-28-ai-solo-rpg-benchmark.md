# 本地优先 AI 单人文字 TRPG 产品与技术基准调研

- 调研日期：2026-07-28
- 目标产品：本地运行、浏览器交互、LLM 扮演 DM、SQLite 保存长期状态的单人文字 TRPG / D&D 应用
- 证据范围：仅使用产品官方页面、官方帮助中心、官方开源仓库、框架官方文档和原始研究论文
- 使用方式：这是架构与体验重构的输入，不是照搬竞品功能的清单

## 结论先行

1. **最值得守住的定位不是“缩小版 VTT”，而是“玩家拥有数据的长期单人冒险运行器”。** AI Dungeon 和 NovelAI 擅长自由文本共创，Friends & Fables 擅长规则与世界状态，Foundry VTT 擅长可搬运的世界文档和备份；当前产品最有差异化的组合，是本地所有权、低启动摩擦、可解释上下文和玩家确认后才落盘的状态变更。[AI Dungeon 基础玩法](https://help.aidungeon.com/faq/the-basics) [Friends & Fables 产品页](https://fables.gg/) [NovelAI Text Adventure](https://docs.novelai.net/en/text/textadventure/) [Foundry 自托管说明](https://foundryvtt.com/article/hosting/)
2. **核心循环必须始终只有一条主线：读局面 → 表达意图 → 看 DM 裁决与叙事 → 修正或接受 → 继续。** “模型、世界设定、原始 JSON、prompt、诊断”都应服务这条循环，不能和“下一步行动”竞争首要注意力。
3. **自由输入与建议选项不是二选一。** 自由输入负责玩家主权；2–4 个可编辑建议负责降低空白页压力。Hidden Door 明确把“无限自由会造成选择瘫痪”作为设计问题，用上下文相关选项让 AI 补全；AI Dungeon 和 NovelAI 则保留 Do / Say / Story 或 Do / Say 等意图模式。[Hidden Door 交互原型说明](https://www.hiddendoor.co/blog/techcrunch-demo) [AI Dungeon Action 类型](https://help.aidungeon.com/faq/how-to-play) [NovelAI 两种输入模式](https://docs.novelai.net/en/text/textadventure/)
4. **长期一致性不是“塞更多上下文”，而是分层状态与可解释检索。** 成熟产品都区分常驻事实、触发式世界知识、近期历史、压缩摘要与相关记忆；AI Dungeon 和 Friends & Fables 还让玩家查看本次实际送入模型的内容。[AI Dungeon Context 预算](https://help.aidungeon.com/faq/what-goes-into-the-context-sent-to-the-ai) [Friends & Fables View Context](https://help.fables.gg/articles/4035786-what-game-state-can-ace-see-update) [NovelAI Lorebook](https://docs.novelai.net/en/text/lorebook/)
5. **结构化状态应由确定性代码拥有，LLM 只提出候选变化。** Friends & Fables 会让 AI 更新物品和 NPC，但也承认模型会出错并提供重写、编辑与人工修正；当前项目的“预览后应用”更适合本地长期存档，不应为了看起来更自动而取消这条边界。[Friends & Fables 入门与纠错](https://help.fables.gg/articles/8524229-getting-started) [Friends & Fables 角色与物品](https://help.fables.gg/articles/4931727-creating-a-character)
6. **“撤销、重试、编辑、分支”不是高级编辑功能，而是生成式游戏的基础容错。** AI Dungeon 把单个 Action 的编辑、撤销、重做和删除放进基本模型；NovelAI 导出会保留 retry history；Foundry 在更新或重要操作前强调备份。[AI Dungeon Adventures](https://help.aidungeon.com/faq/what-are-adventures) [NovelAI 导出说明](https://docs.novelai.net/en/faq/) [Foundry Backups](https://foundryvtt.com/article/backups/)
7. **本地优先必须落实为“可运行、可备份、可导出、可检查”，而不只是数据库放在本机。** 原始 local-first 论文强调离线、长期可读、隐私与最终所有权，并建议至少提供 JSON/PDF 等稳定格式导出；SQLite 官方把单文件、原子事务、跨平台与长期兼容列为应用文件格式优势。[Local-first 原始论文网页](https://www.inkandswitch.com/essay/local-first/) [SQLite 应用文件格式](https://www.sqlite.org/appfileformat.html)
8. **流式体验的关键不是 token 动画，而是完整状态机。** UI 应明确准备上下文、等待首字、流式生成、校验、保存、成功/失败；断线后保留草稿并给出可执行恢复。SSE 本身是单向协议，FastAPI 新版原生 SSE 支持事件 ID、重连、keep-alive 与禁缓冲，但当前仓库固定的 FastAPI 0.115.6 早于该功能，不能直接照抄新版 API。[HTMX SSE](https://htmx.org/extensions/sse/) [FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
9. **安全边界应默认适合本地应用，同时为误暴露网络做防护。** 默认只监听 loopback；API Key 只在服务端读取；模板保持自动转义；HTMX 只请求同源、禁用动态脚本执行、敏感页面不进入 history localStorage；远程模型调用要明确告知“冒险内容会离开本机”。[HTMX 安全基础](https://htmx.org/essays/web-security-basics-with-htmx/) [HTMX Security 配置](https://htmx.org/docs/#security) [OpenAI API Key 建议](https://platform.openai.com/docs/api-reference/backward-compatibility) [OpenAI 数据控制](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)
10. **建议只做三轮有边界的优化。** 第一轮修可靠性与恢复，第二轮修结构化输出和长期连续性，第三轮才增加沉浸感或规则深度；地图、多人、创作者市场和复杂 VTT 不应进入这轮重构。

术语上也应诚实：远程 LLM 不可用时，现有应用可以浏览和修改本地存档，但不能继续生成 DM 回合，因此严格说是 **local-owned / local-first data**，还不是满足“network optional”的完整 local-first 应用；只有配置本地模型或提供离线降级玩法后，才应作更强承诺。[Local-first 的 network optional 原则](https://www.inkandswitch.com/essay/local-first/#3-the-network-is-optional)

## 一、产品基准

### 1. AI Dungeon：自由叙事、可修正行动、分层记忆

**产品定位与循环**

- 玩家可以 Quick Start 或从 Scenario 开始；Scenario 会把起始 prompt、Plot Essentials、Story Cards 等复制到新的 Adventure，所以“模板”和“实际存档”是两个不同对象。[What are Scenarios?](https://help.aidungeon.com/faq/what-are-scenarios)
- 回合输入分为 Do、Say、Story（另有 See 图像模式）；玩家随时可以 Undo、Redo、Retry、Edit，意味着模型错误被当成正常交互分支，而不是异常页。[The Basics](https://help.aidungeon.com/faq/the-basics) [How to Play](https://help.aidungeon.com/faq/how-to-play)
- Adventure 由一系列 Action 组成；每个 Action 可单独编辑、撤销、重做或删除。这是一种很适合文字冒险的细粒度事件日志模型。[What are Adventures?](https://help.aidungeon.com/faq/what-are-adventures)

**信息架构与前端交互**

- 主界面围绕故事和“Take a Turn”，复杂设置藏在 Adventure / Gameplay 设置中，避免把 prompt 工具变成游玩主界面。
- Do / Say / Story 是“输入意图提示”，而不是三套完全不同的页面；它们让系统知道玩家是在尝试行动、说话，还是直接共同创作叙事。
- Scenario 的公开/草稿、Adventure 的私有游玩、Story Card 的导入导出形成“创作资产 → 运行实例 → 可复用知识”的层次。

**后端、状态与 LLM 编排**

- 上下文分为 Required 与 Dynamic。Required 包括 Instructions、Plot Essentials、Story Summary、Author’s Note 和最后行动；Dynamic 包括 Story Cards、Memory Bank 与历史。Required 过长时也按优先级裁剪，而不是假设“常驻内容一定全部进入”。[What goes into Context](https://help.aidungeon.com/faq/what-goes-into-the-context-sent-to-the-ai)
- Plot Essentials 保存总是重要的短事实，Story Cards 由触发词激活，Memory System 结合自动摘要与相关记忆检索；这正是“常驻状态 + 条件知识 + 情节摘要 + 细粒度回忆”的四层模型。[Plot Essentials](https://help.aidungeon.com/faq/plot-essentials) [Story Cards](https://help.aidungeon.com/faq/story-cards) [Memory System](https://help.aidungeon.com/faq/the-memory-system)
- Context Viewer 把实际 context 成本和使用内容暴露给玩家，减少“AI 为什么忘了”的不可解释感。[Understanding Settings](https://help.aidungeon.com/understanding-settings)

**对本项目的启示**

- 保留单一自由输入框，但可以增加轻量的“行动 / 对话 / 描述”意图选择；默认仍是行动，避免先选模式才能输入。
- 把“重试上一回合、编辑并重跑、回退上一回合”提升为正常回合工具，并通过自动安全快照或 turn variant 保证可恢复。
- 继续强化现有 `ContextPack.recalled_context`，让它不仅显示“召回了什么”，还显示预算、优先级、裁剪原因和最终 token/字符占比。

### 2. Friends & Fables：AI GM + 结构化 5e 世界状态

**产品定位与循环**

- 官方定位是 D&D 启发的生成式文字 RPG：AI GM、世界构建、角色卡、战术 5e 战斗、地图、任务和多人被整合在同一个 campaign 中。[产品页](https://fables.gg/) [About](https://fables.gg/about)
- 首次流程是选 featured world、角色、物品、可选邀请伙伴，然后直接和 Franz 对话；世界、角色卡和其他管理入口在 sidebar 中。[Getting Started](https://help.fables.gg/articles/8524229-getting-started)
- 官方明确承认 AI 可能出错或循环，并把“重写该消息、直接编辑消息”作为玩家修复手段。[Getting Started](https://help.fables.gg/articles/8524229-getting-started)

**信息架构与前端交互**

- “故事对话”是主舞台，World / Character / Campaign Settings 是侧栏；这与当前项目的“故事 + 冒险面板”方向一致。
- 角色创建同时支持全手工与 AI 生成，生成后的结果仍可编辑；AI 生成是减少录入成本，不是夺走最终所有权。[Creating a Character](https://help.fables.gg/articles/4931727-creating-a-character)
- 战斗、地图、法术、物品和 NPC 都是结构化对象；这使 AI 叙事可以引用确定性状态，而不必从整段聊天里猜 HP 或库存。

**后端、状态与 LLM 编排**

- ACE 会按任务类型构造不同 context：叙事请求需要世界、记忆和人物，状态更新请求更偏向角色数值。常见 context 包括最近 5–8 条消息、campaign summary、队伍/附近/被提及人物和当前位置。[What game state can ACE see/update?](https://help.fables.gg/articles/4035786-what-game-state-can-ace-see-update)
- 玩家可以查看每条 GM 消息使用的 context。官方也直接说明“更多 context 不总是更好”，无关或冲突内容会降低表现。[What game state can ACE see/update?](https://help.fables.gg/articles/4035786-what-game-state-can-ace-see-update)
- ACE 大约每 5 回合创建压缩记忆，给记忆绑定地点和相关角色，再按当前情境检索；玩家也能手动把重要记忆固定到 Working Context。[Memories](https://help.fables.gg/articles/2838157-memories)
- NPC、角色、物品、法术等状态可在游玩中自动生成或更新，同时允许人工改正。[Creating a Character](https://help.fables.gg/articles/4931727-creating-a-character)

**对本项目的启示**

- 不要把所有输入都当成“讲下一段故事”。至少区分 `play_turn`、`out_of_character`、`state_edit` 和 `world_edit`，并让不同意图使用不同 ContextPack 策略。
- 当前“LLM 提议 → 玩家预览 → 确认写入”的状态边界比全自动更稳，应该保留；可优化的是预览文案和批量确认，而不是取消确认。
- 地点和人物是记忆检索最自然的稳定锚点。后续若升级召回，可先给 `story_memory` 增加 entity/location 关联，不必立刻引入向量数据库。
- 5e 全规则与战术地图是另一个产品量级，不应成为本轮架构重构前置条件。

### 3. Hidden Door：降低空白页压力的“卡牌式共创”

**产品定位与体验**

- Hidden Door 官方把产品描述为把虚构作品转成在线社交角色扮演游戏，视觉上接近互动图像小说，AI Narrator 负责和玩家即兴共创 NPC、物品、地点与冒险。[Press Kit](https://www.hiddendoor.co/press)
- 它的早期原型把角色、地点、主题和情节元素做成卡牌。玩家组合卡牌，AI 生成能容纳这些元素的 premise；这把“你想玩什么？”改造成低负担的选择与组合。[A Disruptive Demo](https://www.hiddendoor.co/blog/techcrunch-demo)
- 角色创建也使用上下文相关词块。官方直接指出“什么都能选”会让人瘫痪，因此先给合适选项，再允许进一步探索。[A Disruptive Demo](https://www.hiddendoor.co/blog/techcrunch-demo)
- 行动时，玩家选择或组合意图，AI 将其展开成完整行动，并用简单挑战反馈表示成功与否；结果计划与角色强弱和当前情境相关，但刻意不做重数值界面。[A Disruptive Demo](https://www.hiddendoor.co/blog/techcrunch-demo)

**公开的技术线索**

- 官方招聘页披露其 Story System 组合模块化 plot structures、传统/生成式 ML 和 decision-making story governor；服务端主要使用 Python，并提到 FastAPI、Pydantic、关系数据库。这不是完整架构文档，但足以说明其把“剧情治理”与“语言生成”分开，而不是只用一条巨型 prompt。[Story Systems 职位说明](https://www.hiddendoor.co/jobs/senior-software-ml-engineer-story-systems)
- 官方合作页强调使用可控架构保护授权 IP，并声明不使用合作方内容训练 LLM；Press Kit 同时把内容与安全标准列为平台能力。[Partners](https://www.hiddendoor.co/partners) [Press Kit](https://www.hiddendoor.co/press)

**对本项目的启示**

- `/new` 不应只有大文本框。增加 6–10 个可组合的“氛围 / 规模 / 主题 / 角色处境”建议，比继续增加说明文字更能降低启动压力。
- DM 下一步建议应该是可编辑的“意图种子”，不要写成已经成功的结果；点击后只填入输入框的现有做法是正确方向。
- “故事治理器”可对应当前确定性 Agent：行动判定、上下文策展、连续性检查、状态守门。无需新造抽象，只需让每个阶段的输入输出契约更清晰。

### 4. NovelAI Text Adventure：写作自由、上下文可调、完整导出

**产品定位与循环**

- Text Adventure 用隐藏的 `>` 把玩家输入标记为“玩家希望角色尝试什么”，AI 再解释并写出叙事结果；官方强调意图不等于已经发生的事实。[Text Adventure Mode](https://docs.novelai.net/en/text/textadventure/)
- UI 只提供 Do / Say 两个主要模式，同时保留特殊输入、直接编辑故事和高级快捷方式；新手能立即使用，专家仍有深度控制。[Text Adventure Mode](https://docs.novelai.net/en/text/textadventure/)
- 故事正文可直接修改；模型、预设、Memory、Author’s Note、Lorebook 与导出集中在侧栏设置，而不压过写作区。[Story Settings](https://docs.novelai.net/en/text/editor/storysettings/)

**上下文与数据**

- Memory 保存长期重要事实；Author’s Note 在更靠近输出的位置插入，用来强烈影响当前叙事焦点。[Story Settings](https://docs.novelai.net/en/text/editor/storysettings/)
- Lorebook 条目由关键词、正则、组合条件或 Always On 激活；条目标题只供人管理，真正送给模型的正文必须自洽。条目支持导入导出、分类与隐藏内容。[Lorebook](https://docs.novelai.net/en/text/lorebook/)
- Context 定义清晰：超出窗口的内容对模型等于未发生，Memory、Author’s Note 和 Lorebook 按插入规则进入。[Glossary: Context](https://docs.novelai.net/en/text/glossary/)
- `.story` / `.scenario` 导出包含设置、Memory、Author’s Note、Lorebook、模型模块与重试树；这比只导出纯文本更接近“可恢复的创作文件”。[NovelAI FAQ](https://docs.novelai.net/en/faq/)

**对本项目的启示**

- 把“叙事正文”和“玩家行动意图”在模型协议里继续分开；绝不能把玩家宣称的成功直接写入 canonical state。
- WorldBible 条目应保证正文自解释，不能依赖 UI 标题才知道主语是谁。
- 需要两种导出：给人阅读的 Markdown/JSON，以及可完整恢复的版本化存档包。只复制 SQLite 文件不够友好，只导出故事文本又无法恢复。
- 专家级 prompt/模型参数可以存在，但必须继续放在系统/高级区域。

### 5. SillyTavern：本地可控的多模型前端，以及它的复杂度代价

**产品定位与能力**

- 官方仓库把 SillyTavern 定义为本地安装的 LLM 前端，不提供托管服务，也不程序化追踪用户数据；它支持多种云端和自托管模型接口、移动布局、视觉小说模式、TTS、Lorebook 和大量 prompt 控制。[官方 GitHub README](https://github.com/SillyTavern/SillyTavern)
- Character 与 Persona 分开：Character 是 AI 身份，Persona 是玩家在对话中的身份；Persona 可锁定到 chat 或 character。[Characters](https://docs.sillytavern.app/usage/characters/) [Personas](https://docs.sillytavern.app/usage/core-concepts/personas/)
- World Info 可以绑定到 global、character、persona 或单个 chat，且有明确插入顺序和预算；Data Bank 进一步提供按范围挂载的 RAG 文档。[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/) [Data Bank](https://docs.sillytavern.app/usage/core-concepts/data-bank/)
- Prompt Manager 将 Main Prompt、World Info、Persona、Character、Examples、History 和 Post-History Instructions 列成可见结构，适合高级用户排查，但学习成本很高。[Prompt Manager](https://docs.sillytavern.app/usage/prompts/prompt-manager/)

**本地数据与安全**

- 用户可以下载完整数据备份，持久数据与应用代码分目录；官方迁移文档说明把数据从 Web 静态目录迁出，以增强可移植性和容器部署清晰度。[User Settings](https://docs.sillytavern.app/usage/user-settings/) [1.12 Data Migration](https://docs.sillytavern.app/installation/st-1.12.0-migration-guide/)
- 官方同时明确警告：服务端不应直接暴露到公网，多用户密码不构成真正隔离，聊天和 API Key 等数据在服务器文件系统中是明文。[Administration](https://docs.sillytavern.app/administration/) [Multi-user Mode](https://docs.sillytavern.app/administration/multi-user/)

**对本项目的启示**

- Provider 可插拔、本地模型可用、完整备份、角色与玩家身份分离都值得借鉴。
- 不应复制 SillyTavern 的“控制驾驶舱”作为默认体验。单人 TRPG 的专家能力要通过 progressive disclosure 出现，主界面只保留游玩所需信息。
- “本地保存”不等于“密钥安全”。campaign 导出必须排除 API Key；长期可考虑操作系统 Keychain，但至少要让凭据和可分享存档物理分离。

### 6. Foundry VTT：世界文档、权限、冷数据与备份

**产品和数据模型**

- Foundry 是单主机、多客户端架构；自托管时内容保存在本机硬盘，World 是游戏数据的主要容器。[Hosting Options](https://foundryvtt.com/article/hosting/)
- Actor、Item、Journal Entry、Scene 等是明确的文档类型，并通过右侧 sidebar 访问。玩家看见的是游戏画布/聊天，文档管理依角色权限开放。[Player Orientation](https://foundryvtt.com/article/player-orientation/) [Users and Permissions](https://foundryvtt.com/article/users/)
- Compendium 用于跨 World 复用并保存当前不需要的对象；内容按需加载，避免一个 World 因数百对象全部传输而逐渐变慢。[Compendium Packs](https://foundryvtt.com/article/compendium/)

**备份与恢复**

- 官方区分单个 Package Backup、全量 Snapshot 和手工备份，并建议在重要修改、会话结束或升级前创建备份。[Backups and Snapshots](https://foundryvtt.com/article/backups/)
- 官方提醒运行中的 World 数据频繁变化，备份应走内建工具或正确的用户数据备份流程，不能假设复制一半的活动文件仍然一致。[User Data Backup](https://foundryvtt.com/article/user-data-backup/)

**对本项目的启示**

- WorldBible、Character、PlotThread、Session、Turn 应继续作为不同领域对象，不要为了导出方便退回“一个巨大 JSON”。
- 可以借鉴 Compendium 思路：关闭章节、旧回合细节和低频世界条目不默认进入当前页或 prompt；按需查询、按需展开。
- 备份能力必须进入产品，而不仅是 README 中的一条 `cp` 命令。

## 二、跨产品设计共识

| 设计问题 | 一手来源中的成熟做法 | 本项目应采用的原则 |
| --- | --- | --- |
| 如何开始 | Quick Start、featured world、可编辑模板、上下文选项，避免空白页。[AI Dungeon](https://help.aidungeon.com/faq/what-are-scenarios) [F&F](https://help.fables.gg/articles/8524229-getting-started) [Hidden Door](https://www.hiddendoor.co/blog/techcrunch-demo) | 新冒险一屏完成“灵感种子 → 可编辑预览 → 创建”，提供示例但不强迫问卷。 |
| 如何行动 | 自由输入为主，Do / Say / Story 或轻量意图模式为辅。[AI Dungeon](https://help.aidungeon.com/faq/how-to-play) [NovelAI](https://docs.novelai.net/en/text/textadventure/) | 默认自由行动；模式只影响上下文和文案，不切换页面。 |
| 如何降低选择成本 | 上下文相关 choice chips，玩家仍可编辑。[Hidden Door](https://www.hiddendoor.co/blog/techcrunch-demo) | 2–4 个具体、互不重复、不替玩家宣布结果的建议，点击只填充。 |
| 如何面对模型错误 | Retry、Edit、Undo/Redo、消息重写与人工修正。[AI Dungeon](https://help.aidungeon.com/faq/what-are-adventures) [F&F](https://help.fables.gg/articles/8524229-getting-started) | 每回合都有恢复路径；失败不清空输入，不留下半持久化状态。 |
| 如何保持连续性 | 常驻事实 + 触发知识 + 摘要 + 相关记忆 + 近期历史。[AI Dungeon](https://help.aidungeon.com/faq/the-memory-system) [NovelAI](https://docs.novelai.net/en/text/lorebook/) [F&F](https://help.fables.gg/articles/2838157-memories) | 保持 ContextBlock 分层与预算；先做 entity/location 关联，再考虑更重的检索基础设施。 |
| 如何建立信任 | Context Viewer、手工固定记忆、可见状态卡。[AI Dungeon](https://help.aidungeon.com/faq/what-goes-into-the-context-sent-to-the-ai) [F&F](https://help.fables.gg/articles/4035786-what-game-state-can-ace-see-update) | 展示“本回合参考、被裁剪内容、状态变更候选、系统裁决”，不用暴露完整 system prompt。 |
| 如何长期拥有数据 | 完整导出、备份、稳定格式、本地文件。[NovelAI](https://docs.novelai.net/en/faq/) [SillyTavern](https://docs.sillytavern.app/usage/user-settings/) [Foundry](https://foundryvtt.com/article/backups/) | 一键导出可恢复包 + 人类可读故事；导入先校验 schema/version，绝不带凭据。 |
| 如何控制复杂度 | 主游玩区与高级设置分离，侧栏承载世界/角色/系统工具。 | 主故事、输入、当前建议永远优先；高级工具不创建第三个常驻栏。 |

## 三、建议的产品与信息架构

### 产品定义

> 一个在自己电脑上运行、由 AI 扮演 DM、能持续数十次会话并让玩家掌握每次状态变化的单人文字 TRPG。

面向用户的短文案可写“本地存档优先”；技术文档则应明确区分“数据归用户所有”和“所有能力均可离线”。

这个定义刻意不承诺：

- 完整 5e 规则引擎；
- 战术地图或多人实时协作；
- UGC 市场；
- 通用 AI 角色聊天；
- 自动替玩家接受所有状态变更。

### 一级导航

1. **继续冒险**：默认首页主行动，展示最近存档、角色、地点和“一键继续”。
2. **新冒险**：灵感种子、可编辑提案、世界/角色预览、最终创建。
3. **存档**：campaign、session、快照、分叉、导入导出。
4. **模型**：连接、测试、隐私说明；不进入常规游玩路径。
5. **高级资料管理**：世界设定和线程可以保留独立页面，但从游戏侧栏进入。

### `/game` 视觉层级

1. 紧凑状态条：冒险 / 章节 / 角色 / 地点 / DM 连接状态。
2. 故事区：可独立滚动；系统判定、骰子、诊断不混入 DM 叙事。
3. 行动区：自由输入、发送状态、最新建议、快速骰子。
4. 冒险面板：角色 / 世界 / 剧情 / 系统四个标签。
5. 每回合次级操作：重试、编辑并重跑、回退到此处、查看本回合参考。

### 关键体验状态

流式回合不应只有“按钮 disabled”：

```text
idle
  -> preparing_context
  -> waiting_first_token
  -> streaming
  -> validating
  -> persisting
  -> succeeded

任何阶段 -> failed（保留草稿、原始输出和可重试入口）
用户主动停止 -> cancelled（不写入完成回合）
```

前端文案应说人话，例如“正在整理角色与世界”“DM 正在回应”“正在检查角色变化”“正在保存本回合”。这比展示内部 Agent 名称更容易理解。

### 纠错与分支

- **重试 DM**：同一玩家行动生成新的 assistant variant，不立刻删除旧版本。
- **编辑并重跑**：从该 turn 前的快照/事件位置分出新 variant；旧分支可查看。
- **回退到此处**：明确会倒回回合、故事记忆、剧情线和待确认变化；操作前自动安全快照。
- **编辑事实**：角色、世界和剧情线修改走结构化表单与审计，不直接改历史叙事。

## 四、建议的技术架构

### 1. 保持模块化单体，不拆微服务

当前 FastAPI + Jinja2/HTMX + SQLite 对单机单用户足够合适。重构重点应是**收紧模块边界和事务边界**，不是增加网络服务：

```text
Web route
  -> Application use case / TurnPipeline
    -> deterministic ActionJudge
    -> ContextBuilder
    -> LLM port
    -> response parser / evaluator
    -> atomic persistence unit
  -> HTML partial / SSE event adapter
```

Hidden Door 的公开技术描述同样是 Python、FastAPI/Pydantic、关系数据库与独立 story governor 的组合，说明“模块化故事系统”不要求微服务。[Hidden Door Story Systems](https://www.hiddendoor.co/jobs/senior-software-ml-engineer-story-systems)

### 2. 把一次回合建模成有状态用例

建议新增或明确以下应用层对象，而不是让 route、LLM client 和 repo 互相知道细节：

- `TurnCommand`：session、player intent、manual context、模型选择、幂等键；
- `PreparedTurn`：行动判定、骰子、ContextPack、messages；
- `TurnEnvelope`：narration、choices、notes、memory、state/thread proposals、raw output；
- `TurnCommit`：持久化所需的完整数据；
- `TurnFailure`：阶段、是否可重试、面向玩家信息、内部诊断。

非流式与流式共享 preparation、validation、commit；只在“如何获得 raw output”和“如何报告进度”上不同。

### 3. 结构化输出采用 capability + fallback

OpenAI Structured Outputs 可以让支持模型按 JSON Schema 返回结果，并提供显式 refusal；但它仍可能因拒答、截断而没有正常 schema，而且当前产品必须兼容不同质量的 OpenAI-compatible provider。[OpenAI Structured Outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/)

因此建议：

1. Provider profile 声明 `supports_structured_output`、`supports_streaming` 等能力；
2. 支持时，非流式回合使用严格 `TurnEnvelope` schema；
3. 不支持时，继续使用分隔符协议；
4. 所有路径最终进入同一个 Pydantic/domain validator；
5. 即使 JSON 语法正确，也要经过业务校验和玩家确认；schema 不能证明数值或剧情事实正确。

流式路径继续“边收 narration 边显示，完成后统一解析与持久化”；不要为了修复结构再偷偷发第二次阻塞请求。

### 4. 持久化使用原子提交和可追溯 variant

- 一次成功回合产生的 turn log、memory、pending state/thread proposals 和必要 summary 变化，应在一个显式事务中提交。
- 给 turn 增加稳定的 logical turn id，并把重试结果作为 variant，而不是覆盖原始文本。
- pending 变化记录来源 turn variant；切换 variant 或回退时能确定哪些 proposal 已失效。
- session restore 继续遵守“先安全快照，再事务内整体恢复”的现有原则。

SQLite 的事务能保证多项更新全成或全不成；WAL 允许读写并发，但仍只有一个 writer，因此写事务应短小，不要在事务里等待 LLM。[SQLite Transactions](https://www.sqlite.org/lang_transaction.html) [SQLite WAL](https://www.sqlite.org/wal.html)

### 5. 数据分层与召回

建议继续使用以下层次：

| 层 | 权威性 | 默认进入 prompt | 更新方式 |
| --- | --- | --- | --- |
| Character / session state | canonical | 是，最高优先级 | 玩家直接编辑或确认 proposal |
| WorldBible hard facts | canonical | 置顶项是；其余按相关性 | 玩家维护 / 新冒险创建 |
| Open PlotThreads | canonical task state | 是或高优先级 | 玩家确认 thread proposal |
| Recent turns | event history | 最近 N 回合 | 每回合追加 |
| Story memory | derived memory | 按预算/相关性 | 从回合建议生成，可编辑/固定 |
| Chapter/campaign summary | derived compression | 是，低细节 | 确定性 rollup |

下一步召回优化优先级：

1. 为 memory/world/thread 增加角色、地点、主题等轻量关联；
2. 用 exact tag + 当前地点/人物 + recency + pinned 做确定性打分；
3. 把候选、分数、裁剪理由写入 recall manifest；
4. 建立连续性回归集后，再判断是否需要 embedding/RAG。

这是 AI Dungeon 的 required/dynamic、F&F 的 location/character memory 与 NovelAI keyword Lorebook 的共同方向。[AI Dungeon Context](https://help.aidungeon.com/faq/what-goes-into-the-context-sent-to-the-ai) [F&F Memories](https://help.fables.gg/articles/2838157-memories) [NovelAI Lorebook](https://docs.novelai.net/en/text/lorebook/)

### 6. SQLite 运行与备份

当前使用 WAL + `synchronous=NORMAL` 的方向适合单机 Web 应用，但需要补全产品级保障：

- 为连接设置合理 `busy_timeout`，把锁竞争转成有限等待和可读错误；
- 保持写事务短小；
- 不把数据库放到网络文件系统；SQLite 官方明确 WAL 依赖同一主机共享状态。[SQLite WAL](https://www.sqlite.org/wal.html)
- 一键备份使用 Python `sqlite3.Connection.backup()` 对应的 Online Backup API，或 `VACUUM INTO`，不要在应用运行时直接 `cp` 活跃数据库；官方指出活动事务中复制单文件可能得到不一致备份。[SQLite Backup API](https://www.sqlite.org/backup.html) [How to Corrupt: backup while active](https://www.sqlite.org/howtocorrupt.html)
- 备份完成后执行 `PRAGMA quick_check` 或定期 `integrity_check`，并记录 app schema version。
- 可恢复导出包包含：一致性数据库快照、`manifest.json`、人类可读 Markdown、可选媒体；不包含 API Key、运行日志和缓存。
- 把当前 `synchronous=NORMAL` 与 `FULL` 在真实回合保存和 snapshot restore 上做一次基准；个人长期存档更看重断电后的最近提交时，可接受轻微写入开销并改用 `FULL`。[PRAGMA synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous)
- 启动诊断记录 Python 实际链接的 SQLite 版本。SQLite 官方在 2026 年披露了极低概率但可能损坏 WAL 数据库的 WAL-reset 竞态，3.51.3+ 已修复，也有 3.44.6、3.50.7 回补；未修复版本宜提示升级，但不必把它描述成紧急故障。[SQLite WAL-reset bug](https://www.sqlite.org/wal.html#the_wal_reset_bug)

### 7. SSE 与前端边界

SSE 适合“POST 一次行动、服务端单向推送多个阶段/增量”，不需要 WebSocket。HTMX 官方也把 SSE 定义为单向、基于普通 HTTP、易穿过代理的机制。[HTMX SSE](https://htmx.org/extensions/sse/)

建议统一事件协议：

```text
event: phase
data: {"phase":"preparing_context","turn_id":"..."}

event: delta
data: {"text":"...","seq":12}

event: final
data: {"turn_id":"...","html":"...","warnings":[]}

event: error
data: {"turn_id":"...","code":"provider_timeout","retryable":true,"message":"..."}
```

实现要点：

- 每个事件有单调 `seq` 或 `id`，客户端忽略重复/乱序增量；
- 流式完成只以明确 final/done 为准，EOF 与 provider `[DONE]` 分别处理；
- 添加 keep-alive、`Cache-Control: no-cache` 和禁代理缓冲；
- 客户端断开后停止继续写浏览器流，但是否取消上游 LLM 需显式策略；
- `final` 事件优先携带服务端用 Jinja 渲染的 canonical turn fragment，并用 out-of-band fragment 同步角色/剧情/诊断区；`app.js` 只负责应用 fragment，不再复制一套回合 HTML renderer。这符合 HTML-over-the-wire 边界，也能减少流式与非流式 UI 漂移。[HTMX swapping](https://htmx.org/docs/#swapping) [`hx-swap-oob`](https://htmx.org/attributes/hx-swap-oob/)
- 回合落盘和 pending state/thread proposals 必须在发送 `final` 前同步成功；FastAPI `BackgroundTasks` 只适合非关键日志或清理，不能承载玩家存档提交。[FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- current FastAPI 0.115.6 只能保留手工 `StreamingResponse`；如果单独评估升级到 0.135+，再考虑原生 `EventSourceResponse`、事件 ID 与 keep-alive。[FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/)

### 8. 安全与隐私

**Web 层**

- 仅使用自己控制的相对 URL；Jinja2 保持自动转义；用户/LLM 文本只进入 HTML text context，不拼入 `<script>`、动态属性名或 `innerHTML`。[HTMX Security Basics](https://htmx.org/essays/web-security-basics-with-htmx/)
- 当前仓库 vendored HTMX 1.9.12 的默认值是 `selfRequestsOnly=false`、`allowScriptTags=true`、`allowEval=true`；应显式设置 `selfRequestsOnly = true`、`allowScriptTags = false`，如果现有交互允许，再评估 `allowEval = false` 和 CSP。[HTMX Security](https://htmx.org/docs/#security)
- 若未来渲染 Markdown 或允许模型生成富文本，必须做 allowlist 清洗并移除 `<script>`、`hx-*`、`data-hx-*`；也可以在纯内容容器外层用 `hx-disable`，避免“故事文本”被解释成行为。
- `/models`、角色原始 JSON、诊断等敏感页面使用 `hx-history="false"` 或关闭 history cache，避免快照进入 localStorage。[hx-history](https://htmx.org/attributes/hx-history/)
- 所有改变状态的 POST 增加 CSRF token 或严格 Origin 校验；“只绑定 localhost”不能替代浏览器请求防护。[HTMX CSRF](https://htmx.org/docs/#csrf-prevention)
- 默认监听 `127.0.0.1`。若将来允许局域网访问，必须新增明确的认证、CSRF、TLS/反代与安全说明，而不是只改 host。

**凭据与模型调用**

- API Key 只在服务器读取，不渲染回输入框；官方 API 参考建议从环境变量或服务端密钥管理系统加载。[OpenAI API Reference](https://platform.openai.com/docs/api-reference/backward-compatibility)
- campaign export 与凭据彻底分离；模型 profile 导出只保留 provider、endpoint、model 等非秘密字段。
- 自定义 endpoint 限制为 `http/https`，拒绝 URL 内嵌用户名/密码；限制重定向、响应体大小和超时。因为本产品也要支持本机模型，不能简单封禁 private IP，应把“允许本机 endpoint”和“允许远程 endpoint”做成明确配置。
- 远程 provider 会接收故事、角色和记忆；UI 应在模型卡片上显示“本机 / 远程”和隐私提示。OpenAI 官方说明 API 数据默认不用于训练（除非主动 opt in），但默认 abuse monitoring 日志仍可能保留至多 30 天；其他 provider 需要各自说明。[OpenAI Data Controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)

**LLM 权限边界**

- WorldBible、story memory、玩家输入都是不可信数据，不得覆盖 system/developer 规则；
- LLM 不能直接执行 SQL、改 canonical state、读取任意本地文件或调用外部工具；
- state/thread change 继续经过 schema validation、领域校验和玩家确认；
- 若未来支持公开共享或多人，再增加可配置内容分级/Moderation；OpenAI Moderation API 能对文本和图像做类别判断，但单机私人游戏不应被某个云厂商强耦合。[OpenAI Moderations](https://platform.openai.com/docs/api-reference/moderations)

## 五、三轮有边界的重构建议

### 第 1 轮：可靠游玩与可恢复性

目标：任何一次模型超时、断流、格式错误或保存失败，都不会让玩家丢输入或得到半个存档。

- 明确 turn 状态机和统一 SSE 事件；
- 统一非流式/流式的 `PreparedTurn -> TurnEnvelope -> TurnCommit`；
- 在调用远程模型前先用稳定 turn/request id 记录 `pending` 请求；失败时保留为可重试状态，成功提交时再一次性转成 completed，幂等键防止断线重试重复落回合；
- 一次回合原子提交，补锁等待与可读错误；
- 失败保留草稿和可重试入口；
- 增加“重试上一回合”和 variant，不直接覆盖；
- 一键创建一致性备份，campaign 导出排除密钥；
- 让流式 `final` 和非流式返回复用同一个服务端 turn partial；
- HTMX 同源、脚本执行、history cache、CSRF/Origin 与基础安全 header 加固。

验收：

- provider 首字超时、半途断流、缺 delimiter、非法 state delta、DB 锁定、浏览器中途刷新都有测试；
- 任一失败后 turn/memory/thread/pending state 不出现部分写入；
- 玩家输入可恢复，旧 DM variant 可查看；
- 备份可在临时数据库恢复并通过 quick check。

### 第 2 轮：连续性与解释性

目标：长冒险中，玩家能理解模型记得什么、为什么记得，并能修正错误记忆。

- Provider capability + typed `TurnEnvelope`，保留 delimiter fallback；
- memory/world/thread 增加 entity/location 关联；
- recall manifest 显示候选、最终纳入、裁剪原因和预算；
- 支持固定/取消固定一条记忆；
- 新冒险增加可组合灵感种子与更短的首次路径；
- 设计连续性回归集：角色状态、NPC 关系、地点事实、未完成线程、已用物品、跨章节摘要。

验收：

- 同一批固定案例能比较重构前后 context 与 DM 输出；
- 核心状态永不因 story memory 挤压而被裁剪；
- 玩家能从 UI 修正或固定错误/关键记忆；
- 非结构化 provider 仍可完整游玩。

### 第 3 轮：沉浸感与规则深度（可选）

目标：只在前两轮稳定后，增加能明显提高“像在玩”的能力。

按收益选择一到两个，不全做：

- 轻量 TTS，按段落播放 DM 叙事；
- 可插拔规则包（先做 d20 检定、难度、优势/劣势和资源消耗，不做完整 5e）；
- 回合内场景/NPC 卡片，以文字与小图标增强定位；
- 本地模型 provider preset 与隐私状态标识。

明确不做：

- 战术地图、实时多人、市场、第三常驻栏、移动端专项大改、完整 5e 数据库。

## 六、反模式清单

- 把所有世界、历史、角色和 memory 每回合全部塞给模型；
- 让 LLM 输出合法 JSON 就直接更新角色卡；
- 为了“Agent 化”把一个本地应用拆成多个服务；
- 流式路径结束后再发一次隐藏非流式请求，让界面长时间无反馈；
- 每次重试直接覆盖旧 DM 输出，无法审计发生过什么；
- campaign 导出包含 API Key；
- 运行中直接复制 WAL 数据库的主文件当备份；
- 用更多设置项代替清晰默认值；
- 把系统诊断、prompt 和原始 JSON放进故事阅读流；
- 在没有回归案例的情况下引入向量数据库或复杂 reranker；
- 因竞品有地图/多人，就偏离“本地优先单人文字冒险”的核心定位。

## 七、一手来源索引

### 产品

- AI Dungeon：[Basics](https://help.aidungeon.com/faq/the-basics)、[Adventures](https://help.aidungeon.com/faq/what-are-adventures)、[Scenarios](https://help.aidungeon.com/faq/what-are-scenarios)、[Context](https://help.aidungeon.com/faq/what-goes-into-the-context-sent-to-the-ai)、[Memory System](https://help.aidungeon.com/faq/the-memory-system)、[Story Cards](https://help.aidungeon.com/faq/story-cards)
- Friends & Fables：[产品页](https://fables.gg/)、[Getting Started](https://help.fables.gg/articles/8524229-getting-started)、[ACE Context](https://help.fables.gg/articles/4035786-what-game-state-can-ace-see-update)、[Memories](https://help.fables.gg/articles/2838157-memories)、[Character](https://help.fables.gg/articles/4931727-creating-a-character)
- Hidden Door：[Press Kit](https://www.hiddendoor.co/press)、[交互原型](https://www.hiddendoor.co/blog/techcrunch-demo)、[Partners](https://www.hiddendoor.co/partners)、[Story Systems](https://www.hiddendoor.co/jobs/senior-software-ml-engineer-story-systems)
- NovelAI：[Text Adventure](https://docs.novelai.net/en/text/textadventure/)、[Story Settings](https://docs.novelai.net/en/text/editor/storysettings/)、[Lorebook](https://docs.novelai.net/en/text/lorebook/)、[FAQ / Export](https://docs.novelai.net/en/faq/)
- SillyTavern：[官方仓库](https://github.com/SillyTavern/SillyTavern)、[Characters](https://docs.sillytavern.app/usage/characters/)、[Personas](https://docs.sillytavern.app/usage/core-concepts/personas/)、[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)、[Prompt Manager](https://docs.sillytavern.app/usage/prompts/prompt-manager/)、[Administration](https://docs.sillytavern.app/administration/)
- Foundry VTT：[Hosting](https://foundryvtt.com/article/hosting/)、[Player UI](https://foundryvtt.com/article/player-orientation/)、[Compendium](https://foundryvtt.com/article/compendium/)、[Backups](https://foundryvtt.com/article/backups/)、[Permissions](https://foundryvtt.com/article/users/)

### 技术

- HTMX：[Documentation](https://htmx.org/docs/)、[SSE Extension](https://htmx.org/extensions/sse/)、[Security Basics](https://htmx.org/essays/web-security-basics-with-htmx/)、[hx-history](https://htmx.org/attributes/hx-history/)
- FastAPI：[Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- SQLite：[Application File Format](https://www.sqlite.org/appfileformat.html)、[WAL](https://www.sqlite.org/wal.html)、[Transactions](https://www.sqlite.org/lang_transaction.html)、[Online Backup](https://www.sqlite.org/backup.html)、[Corruption / Safe Backup](https://www.sqlite.org/howtocorrupt.html)
- Local-first：[Ink & Switch 原始论文网页](https://www.inkandswitch.com/essay/local-first/)、[论文 PDF](https://www.inkandswitch.com/local-first/static/local-first.pdf)
- OpenAI：[Streaming Reference](https://platform.openai.com/docs/api-reference/chat/create)、[Structured Outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/)、[Data Controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)、[Moderations](https://platform.openai.com/docs/api-reference/moderations)
