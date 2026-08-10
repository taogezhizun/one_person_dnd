"""Sole bilingual source for action adjudication and turn-quality labels.

``web.labels`` derives its legacy code-to-Chinese compatibility maps from this
catalog; keep both locale variants together here so server and browser
renderers cannot drift.
"""

MESSAGES: dict[str, tuple[str, str]] = {
    "action.type.exploration": ("探索", "Exploration"),
    "action.type.social": ("社交", "Social"),
    "action.type.combat": ("战斗", "Combat"),
    "action.type.rest": ("休息", "Rest"),
    "action.type.inventory": ("物品", "Inventory"),
    "action.type.meta": ("系统/元指令", "System / meta"),
    "action.signal.explicit_roll": ("已识别掷骰", "Dice roll detected"),
    "action.signal.state_change_likely": ("可能影响角色状态", "May change character state"),
    "action.signal.time_passes": ("时间会推进", "Time will pass"),
    "action.signal.roll_may_be_needed": ("可能需要掷骰", "A roll may be needed"),
    "action.signal.dm_should_adjudicate_outcome": ("结果由 DM 判定", "The DM adjudicates the outcome"),
    "action.signal.adjudication_unsupported": ("本轮规则暂不支持", "Not supported by the current rules"),
    "action.signal.manual_roll_not_canonical": ("手动骰仅作原始结果", "Manual roll is shown as a raw result only"),
    "action.signal.no_check_needed": ("无需系统检定", "No system check needed"),
    "action.signal.adjudication_needs_input": ("角色规则数据需补充", "Character rules data is incomplete"),
    "action.signal.ability_check_resolved": ("属性检定已结算", "Ability check resolved"),
    "action.warning.possible_overreach": ("行动可能越权", "The action may overreach"),
    "action.warning.declared_success": ("行动描述已包含结果", "The action declares its own result"),
    "action.warning.npc_outcome_claim": ("人物结果需要 DM 判定", "The DM must decide the NPC outcome"),
    "action.warning.unsupported_attack_save_or_combat": ("战斗/攻击/豁免尚未自动结算", "Combat, attacks, and saves are not auto-resolved yet"),
    "action.warning.invalid_level_for_proficiency": ("角色等级无效，无法计算熟练", "Invalid character level; proficiency cannot be calculated"),
    "action.warning.proficiency_level_defaulted_to_1": ("缺少等级，熟练暂按 1 级计算", "Level is missing; proficiency uses level 1 for now"),
    # The Chinese intent values are also compatibility keys found in frozen
    # adjudication records. Keep them stable unless persisted records gain an
    # explicit locale-neutral intent code or a migration/alias is added.
    "adjudication.intent.deception": ("用谎言误导对方", "Mislead the target with a lie"),
    "adjudication.intent.intimidation": ("迫使对方屈服", "Force the target to yield"),
    "adjudication.intent.persuasion": ("改变对方的决定", "Change the target's decision"),
    "adjudication.intent.insight": ("判断他人的真实意图", "Read another person's true intentions"),
    "adjudication.intent.avoid_detection": ("避免被发现", "Avoid being detected"),
    "adjudication.intent.agility": ("以灵巧动作克服障碍", "Overcome an obstacle with agility"),
    "adjudication.intent.strength": ("以力量克服障碍", "Overcome an obstacle with strength"),
    "adjudication.intent.sleight": ("不被察觉地操纵物品", "Manipulate an object without being noticed"),
    "adjudication.intent.lock": ("打开上锁的装置", "Open a locked mechanism"),
    "adjudication.intent.investigation": ("从线索推导结论", "Draw a conclusion from the clues"),
    "adjudication.intent.perception": ("发现不明显的线索", "Notice a subtle clue"),
    "adjudication.intent.survival": ("在野外追踪或求生", "Track or survive in the wild"),
    "adjudication.intent.arcana": ("回忆或辨认奥术知识", "Recall or identify arcane lore"),
    "adjudication.intent.history": ("回忆历史知识", "Recall historical lore"),
    "adjudication.intent.nature": ("辨认自然知识", "Identify natural lore"),
    "adjudication.intent.religion": ("回忆宗教知识", "Recall religious lore"),
    "adjudication.intent.medicine": ("判断或处理伤病", "Assess or treat an injury"),
    "adjudication.intent.animal_handling": ("控制或安抚动物", "Control or calm an animal"),
    "adjudication.intent.performance": ("以表演影响观众", "Influence an audience through performance"),
    "critic.empty_dm_response": ("DM 没有返回内容", "The DM returned no content"),
    "critic.missing_required_protocol_delimiters": ("DM 输出缺少必要段落", "The DM response is missing required sections"),
    "critic.empty_narration": ("叙事内容为空", "Narration is empty"),
    "critic.choice_count_out_of_range": ("行动建议数量不适合继续游玩", "The number of action suggestions is not playable"),
    "critic.malformed_state_delta": ("状态变更建议格式有误", "The proposed state change is malformed"),
    "critic.malformed_thread_updates": ("剧情线更新建议格式有误", "The proposed plot-thread update is malformed"),
    "critic.adjudication_outcome_conflict": ("DM 叙事与系统检定结果冲突", "The narration conflicts with the resolved check"),
    "critic.unresolved_check_declared": ("角色数据不足时 DM 提前宣布了检定结果", "The DM declared a result before missing character data was supplied"),
    "response.duplicate_choices": ("行动建议重复", "Action suggestions are duplicated"),
    "response.non_actionable_choice": ("行动建议过于笼统", "An action suggestion is too vague"),
    "response.choice_declares_outcome": ("行动建议替玩家宣布结果", "An action suggestion declares the player's outcome"),
}

for _ability in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
    MESSAGES[f"action.warning.ability_defaulted_to_10:{_ability}"] = (
        f"缺少 {_ability}，本次暂按 10 计算",
        f"{_ability} is missing; this check uses 10",
    )
    MESSAGES[f"action.warning.invalid_ability_score:{_ability}"] = (
        f"{_ability} 数值无效，需要修正角色卡",
        f"{_ability} is invalid; update the character sheet",
    )
