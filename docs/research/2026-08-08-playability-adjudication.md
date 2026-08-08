# 可玩性裁决研究：SRD 5.2.1、确定性重试与最小 interface

> 调研日期：2026-08-08
> 目标：为 `one_person_dnd` 建立一套小而可信的行动裁决核心；不是实现完整 D&D 战斗规则。
> 来源标准：规则只采用 Wizards / D&D Beyond 官方 SRD 与 Basic Rules；工程语义只采用 Python、IETF、SQLite、OpenAI 官方文档，并结合当前仓库源码做设计推论。

## 结论先行

1. **规则基线用 SRD 5.2.1 的能力检定交集。** 首版只实现 `ability_check`；攻击检定、豁免、先攻、AC、伤害、法术资源和行动经济明确不做。这样能先改善探索与社交的“角色数值没有参与结果”问题，又不会伪装成完整 5E 引擎。
2. **裁决必须早于 LLM。** 系统先决定是否检定、能力/技能、DC、熟练、优劣势和骰子结果，再把同一份不可变记录交给 DM 叙事；LLM 不选骰面、不事后改 DC，也不拥有成功/失败事实。
3. **“重试”不是“重掷”。** 同一玩家提交的 `attempt_id` 无论经过网络重试、LLM 超时重试还是应用重启，都必须复用同一条已落盘裁决；只有玩家明确使用重掷规则或发起新行动，才创建新的 attempt。
4. **推荐一个 public entry point：** `ActionAdjudicator.adjudicate(request) -> AdjudicationRecord`。角色卡解析、规则选择、DC、优劣势抵消、掷骰、去重和持久化都藏在这个深 Module 后面。
5. **停止线清楚。** 做完能力检定闭环、历史回放和重试幂等后停止；不要顺手扩成战棋、怪物 stat block、完整职业特性或第二套 prompt 裁决器。

## 一、当前代码的真实缺口

| 当前位置 | 已验证行为 | 对可玩性的影响 |
| --- | --- | --- |
| [`agents/action_judge.py`](../../src/one_person_dnd/agents/action_judge.py) | 用关键词分类行动；只要文本里出现骰子表达式就立刻调用随机掷骰；探索、社交、战斗在没骰子时只给 `roll_may_be_needed` 信号。 | 系统知道“可能要判定”，但没有把角色能力、熟练、DC 和结果闭环起来。 |
| [`engine/dice.py`](../../src/one_person_dnd/engine/dice.py) | `roll_expr()` 直接使用进程级 `random.randint()`，没有注入随机源，也没有稳定 attempt 标识。 | 同一个失败请求重新提交会重新掷骰；测试和历史重建也可能无意消费全局随机状态。 |
| [`domain/actions.py`](../../src/one_person_dnd/domain/actions.py) | `PlayerAction` 只有 campaign/session/text/tags/extra context；`ActionAssessment` 只有类型、原始骰子、signals、warnings。 | interface 表达不了规则版本、能力/技能、DC、修正拆分、成功与否或重试身份。 |
| [`domain/characters.py`](../../src/one_person_dnd/domain/characters.py) | `abilities` 是无约束 `dict[str, Any]`；没有 level、skill proficiencies 或规则就绪状态。 | 即使角色卡写了 DEX，也不能稳定推导熟练加值；新旧 JSON 的含义可能漂移。 |
| [`web/routes/new_adventure.py`](../../src/one_person_dnd/web/routes/new_adventure.py) | 新冒险生成 schema 只要求人物名、种族、职业、背景、目标、HP、金币和物品。 | 新建角色默认没有六项属性、等级与技能熟练，规则引擎没有可靠输入。 |

当前 `TurnPipeline.prepare_messages()` 会先运行 ActionJudge 再调用模型，因此 **一次 `OpenAICompatClient.chat()` 内部的瞬时网络重试会复用已经生成的消息和骰子**；这部分方向是对的。缺口发生在整个 POST/SSE 请求重做时：新的 `PlayerAction` 会再次运行 ActionJudge。`turn_logs` 也只有 `(session_id, turn_index)` 唯一约束，没有提交标识。更隐蔽的是 [`web/turn_presenter.py`](../../src/one_person_dnd/web/turn_presenter.py) 在展示历史时会重新运行 `ActionJudgeAgent`；未来裁决如果仍这样重算，旧回合会受新角色状态、新规则版本和新随机数影响。

因此本轮不能只给 `roll_expr()` 增加一个 seed。需要同时冻结 **规则输入快照、裁决记录、提交身份和历史读取路径**。

## 二、规则调研与项目取舍

### 2.1 版本选择

D&D Beyond 当前把 [SRD 5.2.1](https://www.dndbeyond.com/srd) 作为 2024 规则集的最新 SRD；官方页面也明确区分 SRD 5.1（2014 rules）和 SRD 5.2.x（2024 rules）。[SRD 5.1 → 5.2.1 转换指南](https://media.dndbeyond.com/compendium-images/srd/guide/converting-to-srd-5.2.1.pdf#page=1) 说明 “D20 Test” 是能力检定、攻击检定和豁免的统称。

本项目应把持久化的规则 profile 写成具体版本，例如 `srd_5_2_1_solo_checks_v1`，不要只写含混的 `5e`。本文研究范围内的能力修正、熟练加值、DC 和优劣势与 2014 基本规则高度一致；采用 5.2.1 的主要产品收益，是它更明确地要求 **有 meaningful failure、结果不确定且叙事上有趣时才掷骰**。[SRD 5.2.1, Playing the Game, pp. 5–6](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=6)

### 2.2 D20 Test 的核心等式

[SRD 5.2.1](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=6) 给出的流程是：掷 d20；加入相关能力修正、适用的熟练加值及情境修正；总值达到或超过目标数即成功。能力检定和豁免的目标数叫 DC，攻击检定的目标数叫 AC。

对本项目，能力检定的机械结果应固定为：

```text
selected_d20 + ability_modifier + proficiency_modifier + circumstance_modifier
>= dc
```

`margin = total - dc` 可以持久化用于解释，但首版不应由 margin 自动发明“大成功 / 部分成功 / 大失败”等非 SRD 层级。DM 可以基于二元事实叙述代价或挫折，但不能翻转机械结果。

### 2.3 Ability modifier

[SRD 5.2.1 的 Ability Modifiers 表](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=6) 将 10–11 映射为 +0、12–13 为 +1、14–15 为 +2，并一直覆盖到 30。等价公式是：

```text
floor((ability_score - 10) / 2)
```

该公式也由 Wizards 的 [2014 Basic Rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/step-by-step-characters#AbilityScores) 明确给出。首版只接收 1–30 的整数 ability score；不要把角色卡里已经写好的 `+3` 猜成 score 3 或反过来。

项目取舍：新角色必须写六项 canonical scores；旧角色缺少某项时可临时使用 +0，但必须在记录和 UI 中带 `ability_defaulted_to_10`，不能静默伪造。非法或含混值进入 `needs_input`，不掷骰。

### 2.4 Proficiency

[SRD 5.2.1 proficiency 规则](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=8) 规定：相关 skill/tool/save/weapon 具有熟练时才加入 Proficiency Bonus；同一个数值不能重复加入。角色 1–4 级为 +2、5–8 级 +3、9–12 级 +4、13–16 级 +5、17–20 级 +6。

首版项目规则：

| 输入 | 处理 |
| --- | --- |
| 有 level 且相关 skill 在 `skill_proficiencies` | 加一次对应 PB。 |
| 有 skill proficiency、没有 level | 明示 default level 1，PB +2，并记录 warning。 |
| 没有相关 skill proficiency | 不加 PB；不能因为职业“看起来应该会”而猜。 |
| Expertise、Jack of All Trades、tool + skill 联动 | 首版不实现，避免半套职业特性。 |

### 2.5 Difficulty Class

[SRD 5.2.1 Typical Difficulty Classes](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=6) 是 5 / 10 / 15 / 20 / 25 / 30，对应 very easy 到 nearly impossible；GM 最终决定 DC。

本地 AI 游戏如果让 LLM 在看到骰点后再报 DC，会造成不可验证的事后裁决。因此 DC 必须在掷骰前由确定性 policy 选择并进入同一条记录。首版自动 policy 建议只开放三档：

| 项目档位 | DC | 使用条件 |
| --- | ---: | --- |
| easy | 10 | 有可信场景事实明确降低难度，但仍有 meaningful failure。 |
| standard | 15 | 没有可信难度事实时的默认不确定任务。 |
| hard | 20 | 有可信场景事实明确增加风险或阻力。 |

DC 5 的任务通常应直接成功而不掷骰；DC 25/30 只有世界规则、场景状态或人工规则明确指定时才使用。玩家写在 `player_text` 或 `extra_context` 里的“这很容易 / DC 5”不是可信难度来源。

### 2.6 Advantage / Disadvantage

[SRD 5.2.1](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=8) 规定：有 Advantage 时掷两个 d20 取高，有 Disadvantage 时取低；同类来源不叠加；两者同时存在时完全抵消，即使一边来源更多也是掷一个 d20。若规则允许 reroll，在优劣势检定里也只重掷其中一颗。

项目实现应存下所有来源用于解释，但先归一成 `normal | advantage | disadvantage` 再掷骰。首版只接受可信结构化来源，例如角色 condition、系统 scene fact 或明确的规则条目；不要直接把玩家自称“我占优势”当成 Advantage。

### 2.7 Natural 1 / 20

SRD 5.2.1 把 natural 20 自动命中、natural 1 自动失手明确限定在 **attack roll**。[SRD 5.2.1, Attack Rolls](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf#page=7) 能力检定仍按 total 与 DC 比较。

因此本轮的能力检定不能把 20 强制改成成功，也不能把 1 强制改成失败。UI 可以显示“自然 20 / 自然 1”作为骰面事实，但 `outcome` 只由总值与 DC 决定。

## 三、哪些规则适合现在做，哪些明确不做

| 范围 | 本轮决定 | 理由 |
| --- | --- | --- |
| 探索 / 社交 ability check | **做** | 最直接覆盖当前自由文本主循环；角色能力、技能和环境可以真正影响结果。 |
| meaningful-failure gate | **做** | 避免“开普通门、走到桌边”也掷骰，减少骰子噪音。 |
| modifier、PB、DC、Adv/Disadv、二元结果 | **做** | 是小而完整的 SRD 能力检定闭环。 |
| 透明记录与 retry idempotency | **做** | 这是本地 AI 游戏比纸笔桌面额外需要的信任层。 |
| 攻击、豁免、完整 combat loop | **不做** | 当前角色卡没有稳定的 AC、武器攻击、save proficiencies、资源和敌人 stat block；半套实现会制造错误确定性。 |
| Initiative、行动经济、法术位、伤害、死亡豁免 | **不做** | 属于另一个纵向切片，需要权威 combat state，不是能力检定的顺手扩展。 |
| Expertise、被动检定、组队检定、tool 联动、Heroic Inspiration | **不做** | 都是真实规则，但不是首版可玩性 P0；先保留可扩展字段，不实现效果。 |
| margin 分级、critical ability check、自创 luck 倍率 | **不做** | 不是本文采用的 SRD 核心语义，避免把 house rule 伪装成官方规则。 |

`/game/roll` 可以继续作为独立的原始骰子计算器。玩家在行动文本中写 `1d20+5` 时，首版应把它标记为 `manual_roll`，而不是再叠加角色能力后做第二次 canonical ability check；原始骰点也不能单独证明任务成功。

## 四、确定性骰子与可重试语义

### 4.1 “确定性”应定义为结果可重放，不是 seed 可猜

Python 3.12 官方文档说明，模块级函数绑定到一个隐藏的全局 `Random` 实例；可以创建独立 `Random` 避免共享状态，也可以用 seed 重现序列，但大多数算法可能跨 Python 版本变化，稳定保证主要落在基础 `random()` 序列。[Python 3.12 `random`](https://docs.python.org/3.12/library/random.html#notes-on-reproducibility)

这意味着 `Random(attempt_id).randint(1, 20)` 不是最佳持久合同：客户端知道 attempt 时可能预测骰点，算法升级也可能改变派生序列。更稳的本地游戏语义是：

1. 首次 attempt 由独立 `D20Roller` 产生不可预知骰面。
2. 在任何 LLM 请求前，把完整 adjudication record 原子写入 SQLite。
3. 之后相同 attempt 永远读取记录，不重新生成。
4. 测试通过 `SequenceRoller` 注入固定骰面，不依赖全局 seed。

生产 adapter 可使用 `random.SystemRandom` 或 `secrets`；它们自身不承诺可重放，**可重放由数据库记录保证**。这也让升级 Python 后旧回合仍然稳定。

### 4.2 retry 和 reroll 必须是不同领域动作

[RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) 将 idempotent 定义为重复相同请求与执行一次具有相同 intended effect，并要求客户端不要自动重试非幂等请求，除非应用语义能证明它幂等或确认原请求未执行。当前回合接口是 POST，因此需要应用层 attempt identity，不能靠 HTTP 方法替我们保证。

| 场景 | 标识语义 | 期望结果 |
| --- | --- | --- |
| LLM client 的一次瞬时重试 | 同一 `attempt_id` | 同一 check、DC、骰面和结果；不新增记录。 |
| SSE 断线 / 浏览器重新提交 | 同一 `attempt_id` | 复用记录；若 turn 已完成则返回已完成 turn，不再调用 LLM。 |
| 应用崩溃后恢复 | 同一 `attempt_id` | 从 SQLite 恢复冻结裁决，再继续或显示失败状态。 |
| 玩家明确重掷 | 新 `attempt_id`，并记录 `reroll_of` | 新骰面；这是游戏动作，不是技术 retry。 |
| 玩家稍后再次尝试相同文字 | 新 `attempt_id` | 可产生新检定；相同文本不代表相同领域动作。 |

OpenAI 官方文档说明模型输出本质上会变化，并建议固定模型快照和运行 eval；它还提供 `X-Client-Request-Id` 用于超时排查。[OpenAI API Overview](https://developers.openai.com/api/reference/overview#backwards-compatibility) 这个 header 是可观测性标识，不是本地 turn 的幂等凭证。项目必须在调用任意 OpenAI-compatible provider 之前拥有自己的 `attempt_id` 和冻结裁决。

### 4.3 SQLite 落盘合同

SQLite 官方文档说明写入发生在 transaction 中，且同一时间只有一个 write transaction；`UNIQUE` 约束保证指定列组合唯一。[Transactions](https://www.sqlite.org/lang_transaction.html) [UNIQUE constraints](https://www.sqlite.org/lang_createtable.html#uniqueconst)

建议新增 `adjudication_records`，至少包含：

```text
session_id, attempt_id, request_fingerprint,
policy_version, record_json, created_at
UNIQUE(session_id, attempt_id)
```

同一 key 命中时先比较 `request_fingerprint`：相同则返回原记录，不同则报 `AttemptConflict`。`turn_logs` 同时增加 `attempt_id` 并约束 `UNIQUE(session_id, attempt_id)`，防止“服务端已经完成、客户端没收到 final”后产生第二个 turn。新记录必须在 LLM 调用前 commit；completed turn 再与它绑定。

## 五、Design It Twice：最小 interface 方案

本节是并行设计中的 **“最小 interface、最大 leverage”** 方案。它刻意不追求插件化规则 DSL 或让每个调用方自由组合步骤。

### 5.1 Seam 与问题框定

Seam 放在 `TurnPipeline` 接收规范化 `PlayerAction` 之后、组装 `ContextPack` 和调用 DM 之前。调用方只知道“一次玩家行动需要一份稳定裁决”；调用方不应知道如何解析角色 JSON、选技能、定 DC、抵消优劣势、掷骰或去重。

约束如下：

| 约束 | interface 后果 |
| --- | --- |
| 同时服务非流式、SSE、历史回放和测试 | 返回一个 canonical、可序列化、不可变的 `AdjudicationRecord`。 |
| 同一技术 retry 不得重掷 | request 必须带稳定 `attempt_id`；Module 内部拥有 ledger。 |
| 当前角色 JSON 宽松且有 legacy shape | Module 内部读取并 normalize canonical character facts，不让 route 解析。 |
| 规则必须早于语言模型 | interface 不依赖 LLM，也不接受 LLM 给出的骰面或事后 DC。 |
| 将来可加 attack/save，但本轮不能扩大 | record 保留 `test_kind` 与 `policy_version`，当前 adapter 只产生 `ability_check`。 |

### 5.2 Public interface：一个入口

```python
@dataclass(frozen=True)
class AdjudicationRequest:
    attempt_id: str
    action: PlayerAction


@dataclass(frozen=True)
class AdjudicationRecord:
    attempt_id: str
    policy_version: str
    request_fingerprint: str
    status: Literal["no_check", "resolved", "needs_input", "unsupported"]
    action_type: str
    check: CheckResolution | None
    manual_rolls: tuple[DiceEvent, ...]
    signals: tuple[str, ...]
    warnings: tuple[str, ...]


class ActionAdjudicator:
    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationRecord: ...
```

`CheckResolution` 是返回类型的一部分，不是第二个入口：

```python
@dataclass(frozen=True)
class CheckResolution:
    test_kind: Literal["ability_check"]
    ability: Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    skill: str | None
    dc: int
    dc_reason: str
    roll_mode: Literal["normal", "advantage", "disadvantage"]
    d20s: tuple[int, ...]
    selected_d20: int
    ability_modifier: int
    proficiency_modifier: int
    circumstance_modifier: int
    modifier_sources: tuple[str, ...]
    total: int
    margin: int
    outcome: Literal["success", "failure"]
```

Module 的 constructor wiring 可以接收 SQLite facts/ledger adapter、rules policy 与 roller，但这些属于应用装配和内部 seam；route、ContextPack、prompt builder、presenter 和普通测试都只跨上面这个外部 interface。

### 5.3 Interface 不变量

| 不变量 | 可验证含义 |
| --- | --- |
| attempt identity | 同一 `(session_id, attempt_id)` 和同一 request fingerprint 返回相同 record；不同 fingerprint 必须 `AttemptConflict`。 |
| decide before roll | `test_kind/ability/skill/DC/roll_mode` 先确定，roller 才能被调用；失败路径不能留下“有骰面但无规则”的半记录。 |
| one coherent check | 一次 action 最多一个 canonical check；`no_check/needs_input/unsupported` 的 `check` 必须为 `None`。 |
| arithmetic | `d20s` 长度只能是 1 或 2；selected 必须来自 d20s；PB 最多加一次；`total` 与各修正相等；`outcome == success` 当且仅当 `total >= dc`。 |
| replay over recompute | 记录在 LLM 前 commit；历史页只读取记录，规则版本、角色状态或 Python 升级都不能重算旧回合。 |

另外，natural 1/20 只能作为骰面标签存在，不能覆盖 ability-check 的 arithmetic；manual roll 不能同时作为第二次 canonical check。

### 5.4 预期状态与错误模式

`no_check`、`needs_input` 和 `unsupported` 是正常领域结果，不抛异常：routine action 不需要骰子；含混/损坏的角色数值需要补充；真正的 attack/save 在本轮不支持但仍可让 DM 做非机械叙事。

| 异常 | 触发条件 | 调用方行为 |
| --- | --- | --- |
| `InvalidAdjudicationInput` | 空 attempt、空行动、campaign/session 不匹配。 | 在调用 LLM 前返回可操作错误。 |
| `AttemptConflict` | 同一 attempt key 被不同 action payload 重用。 | 409/领域冲突；绝不能用旧骰子配新行动。 |
| `AdjudicationStoreBusy` | SQLite write transaction 超时或锁冲突。 | fail closed；不调用 LLM、不在内存中临时重掷。 |
| `AdjudicationStoreCorrupt` | 已存 record 不能通过 schema/arithmetic 校验。 | 停止该 attempt 并提示恢复/诊断，不能悄悄重算。 |

### 5.5 使用例

```python
action = PlayerAction(
    campaign_id=campaign_id,
    session_id=session_id,
    text="我趁守卫转身，借着绳索翻过湿滑栏杆",
)
record = adjudicator.adjudicate(
    AdjudicationRequest(attempt_id=form_attempt_id, action=action)
)

# ContextPack 和 prompt 只消费这份 record；不会再各自解析或掷骰。
messages = pipeline.prepare_messages(action=action, adjudication=record)
```

假设角色 DEX 14、3 级且熟练 Acrobatics，可信 scene facts 同时给出“绳索帮助”和“表面湿滑”，二者抵消为 normal；policy 先定 DC 15；若 d20 为 12，则记录为 `12 + 2 + 2 = 16`、`margin=1`、`success`。同一 `form_attempt_id` 在 SSE 断线后重试，会读取同一条 12，而不是再掷一次。

### 5.6 Implementation 隐藏什么

一次 `adjudicate()` 在 seam 后完成整个闭环：

1. canonicalize action 并计算 request fingerprint；查询已有 attempt。
2. 读取角色卡与可信 session/world facts，normalize level、ability scores、skills 和 conditions。
3. 判断 `no_check / ability_check / unsupported`；选择 ability、skill、DC 和优劣势来源。
4. 对新 attempt 调用 roller，计算 breakdown/outcome，并在 transaction 中插入唯一 record。
5. 对已有 attempt 校验 fingerprint 与 record invariant 后原样返回，不重新读取当前角色状态。

这里应 **replace** 当前 `ActionJudgeAgent + roll_events_from_text` 在 turn path 上的组合，而不是再叠一层 wrapper。新 record 可以保留兼容的 `action_type/signals/warnings`，让现有 UI 迁移；`roll_events_from_text()` 只留给 manual dice 功能。

### 5.7 依赖分类与 Adapter

| 依赖 | 分类 | 设计 |
| --- | --- | --- |
| ability/PB/DC/Adv 计算、action policy、character normalization | in-process | 全部藏在 Module implementation；直接通过 public interface 测试。 |
| SQLite facts + adjudication ledger | local-substitutable | 内部 port；生产 `SqliteAdjudicationStore`，测试 `MemoryAdjudicationStore`。不要把 repo 暴露给 route。 |
| d20 entropy | in-process、可替换 | 内部 `D20Roller` seam；生产系统随机 adapter，测试固定序列 adapter。持久结果而非 seed 是重放合同。 |
| LLM provider | true external，但在本 Module 之外 | DM 只消费 record；OpenAI-compatible client 绝不能成为 adjudication dependency。 |

production + test adapter 都是真实用途，因此内部 seam 有价值；外部 interface 仍只有一个 entry point。

### 5.8 Depth、locality 与 deletion test

这个 Module 的 leverage 高：非流式 route、SSE route、prompt、UI、历史和测试都只学习一个 record。改变 DC policy、补角色 normalization、修正优劣势或更换 roller 时，调用方不变。

如果删除它，以下复杂度会重新散回多个调用方：角色 JSON 解析、检定门槛、技能/能力映射、PB、DC、优势抵消、骰子注入、attempt 去重、SQLite 原子写入和历史重放。这通过 deletion test，说明它不是 pass-through。

### 5.9 Trade-offs

| 收益 | 代价 |
| --- | --- |
| 一个入口最大化 depth，调用方无法把“先看骰点再定 DC”拼错。 | union status 使调用方仍需处理 `no_check/resolved/needs_input/unsupported` 四种结果。 |
| 规则、随机、幂等和历史合同集中，locality 强。 | Module implementation 会比现在的关键词 Agent 大，需要按内部私有函数组织。 |
| policy 可以迭代而不扩大外部 surface。 | 首版扩展点少；house rule 必须作为有版本的内部 policy，而不是 route 随意传参数。 |
| ledger 保证跨重启 replay。 | 首次裁决多一次短 SQLite transaction，并需要 schema migration。 |
| 不提供 `plan()` / `roll()` 两段式入口，避免调用方乱序。 | 暂时不能做“先给玩家看 DC，再点击确认掷骰”的 UI；真有该产品需求时再新增第二入口。 |

## 六、推荐的实现落点与顺序

这不是要求新造很多 public 模块。推荐只把一个外部 interface 暴露为 `ActionAdjudicator`；内部可以按现有仓库边界放置类型、repo 和迁移。

| 顺序 | 改动 | 完成证据 |
| ---: | --- | --- |
| 1 | 扩充角色规则快照：level、六项 ability scores、skill proficiencies；`/new` 生成并校验；legacy 缺失有明确 warning。 | character normalization 单测覆盖 party/top-level、英文缩写与非法值。 |
| 2 | 新增 adjudication record + attempt schema；实现一个 `adjudicate()` 和内部 SQLite/roller adapters。 | arithmetic、DC、PB、Adv/Disadv、no-check、unsupported 测试全部跨 public interface。 |
| 3 | TurnPipeline 在 prompt 前调用；non-stream 与 SSE 使用同一 record；LLM error 后同 attempt 可恢复。 | 同一 attempt 两次请求只有一条 record、同一骰面；不同 payload 冲突。 |
| 4 | `turn_logs` 绑定 attempt；ContextPack、TurnResult、presenter 与 UI 显示 modifier/DC/outcome/reasons。 | 历史刷新不调用 roller；角色升级后旧回合显示不变。 |
| 5 | 更新玩家文档并跑完整验证；到此停止本轮。 | compileall、完整 unittest、route smoke；若 UI 改动则检查三个既定桌面尺寸。 |

## 七、interface 级验收矩阵

| Case | 输入 | 必须观察到 |
| --- | --- | --- |
| meaningful gate | routine movement vs. locked-door attempt | 前者 `no_check` 且 roller 0 次；后者 resolved 且 roller 1 次。 |
| modifiers | score 14、level 3、relevant proficiency、DC 15、d20 11 | `11 + 2 + 2 = 15`，success，PB 只加一次。 |
| advantage algebra | 两个 advantage sources + 一个 disadvantage source | 完全抵消为 normal，只掷 1 颗，而不是“净 advantage”。 |
| natural face | ability check 分别掷 20 但 total < DC、掷 1 但 total >= DC | 前者 failure、后者 success；只附骰面标签。 |
| retry | 相同 attempt + 相同 payload 调用两次 | record byte-equivalent、roller 只调用一次、数据库一行。 |
| conflict | 相同 attempt + 不同 player text | `AttemptConflict`，不调用 roller/LLM。 |
| crash boundary | record commit 后模拟 LLM timeout，再用同 attempt 恢复 | 骰面/DC/outcome 不变；不会生成第二条 turn。 |
| history | 保存后改变角色属性和 policy version，再刷新历史 | 读取旧 record；不 normalize 当前角色、不调用 roller。 |

## 最终建议

首版不要把“规则深度”理解成实现更多规则名词。真正提升可玩度的最小纵向切片是：

```text
玩家行动
  → 决定是否需要有意义的 ability check
  → 冻结 ability / skill / DC / proficiency / advantage
  → 只掷一次并持久化
  → 把不可变成功或失败事实交给 DM 叙事
  → retry 永远重放，reroll 必须显式发生
```

`ActionAdjudicator.adjudicate()` 是推荐的唯一外部 interface。它足够深，能同时解决角色数值不参与、骰子重试漂移、流式/非流式重复逻辑和历史重算四个问题；又足够窄，可以在能力检定闭环完成后按用户要求收口。
