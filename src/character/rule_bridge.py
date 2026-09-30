"""
人物卡 ↔ 规则 AI 桥接

职责:
1. 把 CharacterSheet 上下文注入到问题里，让规则 AI 知道"谁在问"
2. 根据角色特征提取应该检索的规则主题（职业特性、物种能力、持有法术等）
3. 提供 "is this action allowed?" 的轻量校验接口（不做完整仲裁，只抓硬约束）

注意:
- 纯函数模块，不持有 retriever 或 generator 实例
- 真正的检索/生成由 main.py 中的全局服务完成，这里只做数据加工
- 重检索/生成的工作不放在这里做，避免循环依赖
"""

from __future__ import annotations

from .models import (
    CharacterSheet,
    Condition,
    ItemType,
    ProficiencyLevel,
    Skill,
)
from .calculator import (
    compute_derived_stats,
    exhaustion_penalty,
    has_advantage_tag,
    has_disadvantage_tag,
)

# 英文 D&D 术语 → 中文，用于把角色卡中的英文字段翻译成数据库可检索的中文词。
# 构建为模块级常量，避免重复初始化。
def _build_en_to_zh() -> dict[str, str]:
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from term_mapper import DnDTermMapper
        mapper = DnDTermMapper()
        # zh_to_en 的反向映射；英文 value 统一小写作为 key
        return {v.lower(): k for k, v in mapper.zh_to_en.items()}
    except Exception:
        return {}

_EN_TO_ZH: dict[str, str] = _build_en_to_zh()


def _zh(term: str) -> str:
    """
    将英文 D&D 术语翻译为中文，供数据库检索使用。
    若无对应翻译则原样返回（可能本身已是中文）。
    """
    return _EN_TO_ZH.get(term.lower(), term)


# ============================================================
#  问题增强
# ============================================================

def build_enriched_question(
    question: str,
    sheet: CharacterSheet,
    *,
    include_stats: bool = True,
) -> str:
    """
    在问题前拼接一段角色上下文，让规则 AI 的检索与生成都带有"谁在问"的视角。

    包含内容:
    - 角色职业/等级/物种
    - 核心属性与修正值
    - 当前 HP / AC / 状态 / 效果
    - 装备的武器与法术位

    不包含完整背包（太长），也不包含 backstory 等描述字段。
    """
    context_lines = [sheet.to_context_summary()]

    if include_stats:
        derived = compute_derived_stats(sheet)
        extras = []
        if derived["spell_save_dc"] is not None:
            extras.append(f"法术豁免DC: {derived['spell_save_dc']}")
            extras.append(f"法术攻击加值: +{derived['spell_attack_bonus']}")
        if derived["exhaustion_penalty"] < 0:
            extras.append(f"耗竭惩罚: {derived['exhaustion_penalty']} (d20)")
        if extras:
            context_lines.append("  " + "  ".join(extras))

    context = "\n".join(context_lines)
    return (
        f"[角色上下文]\n{context}\n\n"
        f"[玩家问题]\n{question}\n\n"
        f"请结合角色的实际情况，严格依据【知识库规则文本】中的条目作答。"
        f"如果角色不符合某条规则的前置条件，请明确指出。"
        f"若知识库中无相关规则，输出\"📭 知识库未收录\"后停止，禁止使用训练数据补充。"
    )


# ============================================================
#  主题提取
# ============================================================

def extract_rule_topics(sheet: CharacterSheet) -> list[str]:
    """
    从角色身上提取应该预加载/优先检索的规则主题。
    用于:
    - 在对话开始时预热检索器的缓存
    - 把这些词作为"热主题"加入检索 query

    去重后返回。
    """
    topics: set[str] = set()

    # 职业 + 子职业 + 已选职业特性
    # class_name / subclass / chosen_features 在角色卡中通常为英文（如 "Barbarian"）
    # 过 _zh() 翻译成中文后数据库才能检索到
    for cls in sheet.class_levels:
        topics.add(_zh(cls.class_name))
        if cls.subclass:
            topics.add(_zh(cls.subclass))
        topics.update(_zh(f) for f in cls.chosen_features)

    # 物种 + 物种特性
    if sheet.species.name:
        topics.add(_zh(sheet.species.name))
    if sheet.species.lineage:
        topics.add(_zh(sheet.species.lineage))
    topics.update(_zh(t) for t in sheet.species.traits)

    # 背景 + 起源专长
    if sheet.background.name:
        topics.add(_zh(sheet.background.name))
    if sheet.background.origin_feat:
        topics.add(_zh(sheet.background.origin_feat))

    # 专长
    if sheet.origin_feat:
        topics.add(_zh(sheet.origin_feat))
    topics.update(_zh(f) for f in sheet.general_feats)
    topics.update(_zh(f) for f in sheet.fighting_style_feats)
    if sheet.epic_boon:
        topics.add(_zh(sheet.epic_boon))

    # 已装备武器
    for item in sheet.equipped_weapons():
        topics.add(_zh(item.name))
        if item.mastery:
            # 用中文格式，避免英文前缀无法被检索
            topics.add(f"武器精通：{_zh(item.mastery.value)}")

    # 法术与戏法
    for spell in sheet.spells_known:
        topics.add(_zh(spell.name))
    for cantrip in sheet.cantrips_known:
        topics.add(_zh(cantrip.name))

    # 当前状态也值得查 (GM 想知道状态的完整规则文本)
    # Condition.value 是英文小写（如 "blinded"），_zh() 转为中文（"目盲"）
    for cond in sheet.conditions:
        topics.add(_zh(cond.value))

    # 生效的效果名 (法术或能力)
    for effect in sheet.active_effects:
        topics.add(_zh(effect.name))

    # 过滤空字符串
    return sorted(t for t in topics if t.strip())


# ============================================================
#  动作可行性快速检查
# ============================================================

class ActionCheck:
    """
    动作可行性检查结果。

    hard_block = True: 规则硬性禁止 (如 unconscious 不能行动)
    warnings = []: 软提示 (如 poisoned 有劣势)
    notes = []: 角色上下文中与动作相关的提示 (如"你是游荡者，可以用灵巧武器偷袭")
    """
    def __init__(self) -> None:
        self.hard_block: bool = False
        self.block_reasons: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def block(self, reason: str) -> None:
        self.hard_block = True
        self.block_reasons.append(reason)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def to_dict(self) -> dict:
        return {
            "hard_block": self.hard_block,
            "block_reasons": self.block_reasons,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def check_can_act(sheet: CharacterSheet) -> ActionCheck:
    """
    检查角色当前能否行动。
    只检查硬约束，不做复杂判断。
    """
    result = ActionCheck()

    # 失能类状态 = 硬禁
    hard_conditions = {
        Condition.UNCONSCIOUS: "昏迷，无法行动",
        Condition.PARALYZED: "瘫痪，无法行动",
        Condition.PETRIFIED: "石化，无法行动",
        Condition.STUNNED: "震慑，不能进行动作或反应",
        Condition.INCAPACITATED: "失能，无法进行动作或反应",
    }
    for cond, reason in hard_conditions.items():
        if cond in sheet.conditions:
            result.block(reason)

    # HP 为 0 且未稳定
    if sheet.hit_points.is_dying:
        result.block("HP 为 0，正在死亡豁免")
    if sheet.hit_points.is_dead:
        result.block("已死亡")

    # 10 级耗竭 = 死亡
    if sheet.exhaustion_level >= 10:
        result.block("耗竭等级 10，已死亡")
    elif sheet.exhaustion_level > 0:
        result.warn(
            f"耗竭等级 {sheet.exhaustion_level}/10，所有 d20 检定 {exhaustion_penalty(sheet)}"
        )

    # 动作经济已用尽
    if sheet.action_used:
        result.warn("本轮动作已使用")
    if sheet.bonus_action_used:
        result.warn("本轮附赠动作已使用")
    if sheet.reaction_used:
        result.warn("反应已使用")

    return result


def check_can_attack_melee(sheet: CharacterSheet) -> ActionCheck:
    """检查近战攻击的前置条件。"""
    result = check_can_act(sheet)
    if result.hard_block:
        return result

    # 没装备近战武器
    melee_weapons = [
        w for w in sheet.equipped_weapons()
        if w.weapon_category and "melee" in w.weapon_category.value
    ]
    if not melee_weapons:
        result.warn("未装备近战武器，将使用无武装打击 (1 + STR)")
    else:
        result.note(
            "装备的近战武器: "
            + ", ".join(f"{w.name}({w.damage_dice})" for w in melee_weapons)
        )

    # 优势/劣势聚合
    if has_advantage_tag(sheet, "attack"):
        result.note("攻击具有优势")
    if has_disadvantage_tag(sheet, "attack"):
        result.warn("攻击具有劣势 (受困/恐惧/倒地等)")

    return result


def check_can_cast_spell(sheet: CharacterSheet, spell_level: int) -> ActionCheck:
    """检查施法的前置条件。spell_level=0 代表戏法。"""
    result = check_can_act(sheet)
    if result.hard_block:
        return result

    if not sheet.is_spellcaster():
        result.block("角色不是施法者")
        return result

    if spell_level > 0:
        available = sheet.spell_slots.available(spell_level)
        if available <= 0:
            # 检查是否有更高等级法术位可用
            higher = [
                lvl for lvl in sheet.spell_slots.slots
                if lvl >= spell_level and sheet.spell_slots.slots[lvl].current > 0
            ]
            if not higher:
                result.block(f"没有 {spell_level} 环或更高等级的法术位可用")
            else:
                result.note(
                    f"{spell_level} 环已耗尽，但可用更高等级法术位: "
                    + ", ".join(f"{l}环" for l in higher)
                )
        else:
            result.note(f"{spell_level} 环法术位剩余 {available}")

    if sheet.concentration_effect_id and spell_level > 0:
        # 假设要施展新集中法术会冲突
        result.warn(
            "角色当前正在集中一个法术，施展新的集中法术将终止旧的"
        )

    # 戴重甲且无重甲精通会影响某些职业施法（这里做通用提示）
    armor = sheet.equipped_armor()
    if armor and armor.armor_category and armor.armor_category.value == "heavy":
        wizard_like = any(
            c.class_name.lower() in ("wizard", "sorcerer", "warlock")
            for c in sheet.class_levels
        )
        if wizard_like:
            result.warn("作为法师/术士/邪术师穿重甲可能无法施法")

    return result


# ============================================================
#  综合快照：给 LLM 的一次性打包
# ============================================================

def character_snapshot_for_llm(sheet: CharacterSheet) -> dict:
    """
    返回一个 LLM 友好的字典摘要，包含:
    - summary_text: 简明自然语言上下文
    - derived: 派生数值
    - topics: 相关规则主题 (供检索器预热)
    - action_state: 能否行动的快速检查
    """
    return {
        "summary_text": sheet.to_context_summary(),
        "derived": compute_derived_stats(sheet),
        "topics": extract_rule_topics(sheet),
        "action_state": check_can_act(sheet).to_dict(),
    }
