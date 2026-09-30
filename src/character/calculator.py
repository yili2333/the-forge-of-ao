"""
人物卡派生值计算器

原则:
1. 全部为 stateless 纯函数，输入 CharacterSheet 输出计算结果
2. 不修改传入的 sheet
3. 计算顺序: 基础 → 装备 → 效果 → 条件 → 结果
4. 2024 版规则优先，同时兼容 2014 版基本公式
5. 复杂到需要查规则库的部分（具体技能描述、法术细节）不在这里处理
"""

from __future__ import annotations

from .models import (
    AbilityName,
    AbilityScores,
    ArmorCategory,
    CharacterSheet,
    Condition,
    Item,
    ItemType,
    ProficiencyLevel,
    Skill,
    SKILL_ABILITY,
    WeaponProperty,
)


# ============================================================
#  基础数值
# ============================================================

def ability_modifier(score: int) -> int:
    """标准 D&D 5e 公式: (score - 10) // 2，支持负分"""
    return (score - 10) // 2


def proficiency_bonus_for_level(total_level: int) -> int:
    """根据总等级返回熟练加值 (Lv1-4 = +2, Lv5-8 = +3, ...)"""
    if total_level <= 0:
        return 2
    return 2 + (total_level - 1) // 4


# ============================================================
#  护甲等级 (AC)
# ============================================================

def compute_ac(sheet: CharacterSheet) -> int:
    """
    根据装备和效果计算 AC。
    只处理"普通"情况，不处理魔武僧的多样化 AC 公式（留给 classes 模块补）。

    规则:
    - 无甲:        10 + DEX
    - 轻甲:        base + DEX
    - 中甲:        base + min(DEX, 2)
    - 重甲:        base   (DEX 不参与)
    - 盾牌:        +2
    - 魔法武器加值: +n
    - active_effects 的 ac_bonus: 累加
    """
    dex_mod = sheet.ability_scores.modifier(AbilityName.DEX)

    armor = sheet.equipped_armor()
    if armor is None:
        ac = 10 + dex_mod
    else:
        base = armor.armor_class_base
        cat = armor.armor_category
        if cat == ArmorCategory.LIGHT:
            ac = base + dex_mod
        elif cat == ArmorCategory.MEDIUM:
            cap = armor.armor_max_dex_bonus if armor.armor_max_dex_bonus is not None else 2
            ac = base + min(dex_mod, cap)
        elif cat == ArmorCategory.HEAVY:
            ac = base
        else:
            # 未知类别当轻甲处理
            ac = base + dex_mod
        ac += armor.magical_bonus

    shield = sheet.equipped_shield()
    if shield is not None:
        ac += max(2, shield.armor_class_base) + shield.magical_bonus

    for effect in sheet.active_effects:
        ac += effect.ac_bonus

    return ac


# ============================================================
#  先攻
# ============================================================

def compute_initiative(sheet: CharacterSheet) -> int:
    """先攻 = DEX 修正 + 其他加值 (武器精通 Vex / 快速反应专长等)"""
    return sheet.ability_scores.modifier(AbilityName.DEX) + sheet.initiative_bonus


# ============================================================
#  豁免
# ============================================================

def saving_throw_modifier(sheet: CharacterSheet, ability: AbilityName) -> int:
    mod = sheet.ability_scores.modifier(ability)
    if ability in sheet.saving_throws.proficient:
        mod += sheet.proficiency_bonus
    # 效果加值
    for effect in sheet.active_effects:
        mod += effect.save_bonus
    return mod


# ============================================================
#  技能
# ============================================================

def skill_modifier(sheet: CharacterSheet, skill: Skill) -> int:
    ability = SKILL_ABILITY[skill]
    base = sheet.ability_scores.modifier(ability)
    level = sheet.skills.get(skill)
    pb = sheet.proficiency_bonus
    if level == ProficiencyLevel.PROFICIENT:
        base += pb
    elif level == ProficiencyLevel.EXPERTISE:
        base += pb * 2
    elif level == ProficiencyLevel.HALF:
        base += pb // 2
    return base


# ============================================================
#  被动值
# ============================================================

def passive_score(sheet: CharacterSheet, skill: Skill) -> int:
    """被动检定 = 10 + 修正 + 效果加值。不处理优势/劣势（需专长时加 ±5）。"""
    return 10 + skill_modifier(sheet, skill)


def passive_perception(sheet: CharacterSheet) -> int:
    return passive_score(sheet, Skill.PERCEPTION)


def passive_investigation(sheet: CharacterSheet) -> int:
    return passive_score(sheet, Skill.INVESTIGATION)


def passive_insight(sheet: CharacterSheet) -> int:
    return passive_score(sheet, Skill.INSIGHT)


# ============================================================
#  攻击与伤害
# ============================================================

def weapon_attack_bonus(sheet: CharacterSheet, weapon: Item) -> int:
    """
    武器攻击命中加值。
    - 近战默认 STR；有 finesse 时取 STR/DEX 较大者
    - 远程默认 DEX；有 thrown 时默认 STR（除非 finesse）
    - 熟练时 +PB
    - 魔法加值 +n
    - 效果 attack_bonus 加成
    """
    props = set(weapon.weapon_properties)
    str_mod = sheet.ability_scores.modifier(AbilityName.STR)
    dex_mod = sheet.ability_scores.modifier(AbilityName.DEX)

    is_ranged = weapon.weapon_category and "ranged" in weapon.weapon_category.value

    if is_ranged:
        ability_mod = dex_mod
        if WeaponProperty.THROWN in props and WeaponProperty.FINESSE not in props:
            ability_mod = str_mod
    else:
        if WeaponProperty.FINESSE in props:
            ability_mod = max(str_mod, dex_mod)
        else:
            ability_mod = str_mod

    total = ability_mod + weapon.magical_bonus

    # 熟练判定: 角色熟练列表里有此武器名或其类别
    weap_profs = {p.lower() for p in sheet.weapon_proficiencies}
    if weapon.name.lower() in weap_profs or (
        weapon.weapon_category and weapon.weapon_category.value in weap_profs
    ):
        total += sheet.proficiency_bonus

    for effect in sheet.active_effects:
        total += effect.attack_bonus

    return total


def spell_save_dc(sheet: CharacterSheet, class_name: str | None = None) -> int | None:
    """
    法术豁免 DC = 8 + PB + 施法属性修正。非施法者返回 None。

    class_name:
      - None（默认）→ 使用主施法属性（primary_spellcasting_ability）
      - 指定职业名   → 使用该职业的施法属性（多职业时按职业查询）
    """
    if class_name and class_name in sheet.spellcasting_abilities:
        ability = sheet.spellcasting_abilities[class_name]
    else:
        ability = sheet.primary_spellcasting_ability()
    if ability is None:
        return None
    return 8 + sheet.proficiency_bonus + sheet.ability_scores.modifier(ability)


def spell_attack_bonus(sheet: CharacterSheet, class_name: str | None = None) -> int | None:
    """
    法术攻击加值 = PB + 施法属性修正。

    class_name:
      - None（默认）→ 使用主施法属性（primary_spellcasting_ability）
      - 指定职业名   → 使用该职业的施法属性（多职业时按职业查询）
    """
    if class_name and class_name in sheet.spellcasting_abilities:
        ability = sheet.spellcasting_abilities[class_name]
    else:
        ability = sheet.primary_spellcasting_ability()
    if ability is None:
        return None
    return sheet.proficiency_bonus + sheet.ability_scores.modifier(ability)


def spell_stats_by_class(sheet: CharacterSheet) -> dict[str, dict]:
    """
    返回每个施法职业的 DC 和攻击加值。
    单职业时 key 为 "default"；多职业时 key 为职业名。

    示例返回值：
      {"Wizard": {"dc": 15, "attack_bonus": 7},
       "Cleric": {"dc": 14, "attack_bonus": 6}}
    """
    if sheet.spellcasting_abilities:
        return {
            cls_name: {
                "dc": 8 + sheet.proficiency_bonus + sheet.ability_scores.modifier(ability),
                "attack_bonus": sheet.proficiency_bonus + sheet.ability_scores.modifier(ability),
                "ability": ability.value,
            }
            for cls_name, ability in sheet.spellcasting_abilities.items()
        }
    # 单职业兼容路径
    ability = sheet.spellcasting_ability
    if ability is None:
        return {}
    return {
        "default": {
            "dc": 8 + sheet.proficiency_bonus + sheet.ability_scores.modifier(ability),
            "attack_bonus": sheet.proficiency_bonus + sheet.ability_scores.modifier(ability),
            "ability": ability.value,
        }
    }


# ============================================================
#  HP
# ============================================================

def max_hp_by_formula(sheet: CharacterSheet, method: str = "average") -> int:
    """
    根据职业等级推算最大 HP（不含 CON 修正加值之外的特殊来源）。
    method:
        "average" - 平均值 (推荐，和 PHB 一致)
        "fixed"   - 等同 average
    注意: 此函数仅为"初始化建卡"时计算，平时应直接读 sheet.hit_points.maximum。
    """
    con_mod = sheet.ability_scores.modifier(AbilityName.CON)
    total = 0
    for i, cls in enumerate(sheet.class_levels):
        for lvl in range(1, cls.level + 1):
            if i == 0 and lvl == 1:
                # 1 级满血: 生命骰上限 + CON
                total += cls.hit_die_size + con_mod
            else:
                # 后续等级: 取平均 (hit_die / 2 + 1) + CON
                total += cls.hit_die_size // 2 + 1 + con_mod
    return max(1, total)


# ============================================================
#  负重
# ============================================================

def carry_capacity(sheet: CharacterSheet) -> float:
    """负重上限 = STR * 15（以磅为单位）"""
    return sheet.ability_scores.strength * 15


def current_load(sheet: CharacterSheet) -> float:
    return sum(i.weight * i.quantity for i in sheet.inventory)


def is_encumbered(sheet: CharacterSheet) -> bool:
    return current_load(sheet) > carry_capacity(sheet)


# ============================================================
#  耗竭 (2024 版)
# ============================================================

def exhaustion_penalty(sheet: CharacterSheet) -> int:
    """
    2024 版耗竭: 每级 -2 应用到 d20 检定与攻击，10 级则死亡。
    返回该角色当前应承受的 d20 减值 (负数或 0)。
    """
    lvl = sheet.exhaustion_level
    if lvl <= 0:
        return 0
    if lvl >= 10:
        # 实际上到 10 级就死了，但保险起见不返回崩溃值
        return -20
    return -2 * lvl


# ============================================================
#  优势/劣势聚合
# ============================================================

def has_advantage_tag(sheet: CharacterSheet, tag: str) -> bool:
    """
    检查角色是否对某类检定 (如 "stealth" / "attack_while_invisible") 具有优势。
    tag 用字符串自由描述，匹配 active_effects.advantage_on。
    """
    tag = tag.lower()
    for effect in sheet.active_effects:
        if any(t.lower() == tag for t in effect.advantage_on):
            return True
    # 某些条件提供隐式优势
    if Condition.INVISIBLE in sheet.conditions and tag in ("attack", "attack_melee", "attack_ranged"):
        return True
    return False


def has_disadvantage_tag(sheet: CharacterSheet, tag: str) -> bool:
    tag = tag.lower()
    for effect in sheet.active_effects:
        if any(t.lower() == tag for t in effect.disadvantage_on):
            return True
    # 常见条件导致的劣势
    disabling_conditions = {
        Condition.POISONED,
        Condition.FRIGHTENED,
        Condition.PRONE,
        Condition.RESTRAINED,
    }
    if tag == "attack" and any(c in sheet.conditions for c in disabling_conditions):
        return True
    return False


# ============================================================
#  综合快照 (用于 API /character/{id}/summary)
# ============================================================

def compute_derived_stats(sheet: CharacterSheet) -> dict:
    """
    一次性算出所有派生值，返回 dict。
    用于前端展示 / LLM 上下文，不修改 sheet。

    active_effects 中的数值修正（ac_bonus / save_bonus / speed_modifier /
    hp_max_modifier / attack_bonus）已由各子函数自动折叠进结果。
    此处额外暴露两个效果汇总字段：
      hp_max_effective   - 含 hp_max_modifier 效果的最大 HP
      speed_effective    - 含 speed_modifier 效果的步行速度
    """
    hp_max_mod = sum(e.hp_max_modifier for e in sheet.active_effects)
    speed_mod  = sum(e.speed_modifier   for e in sheet.active_effects)

    stats = {
        "total_level": sheet.total_level,
        "proficiency_bonus": sheet.proficiency_bonus,
        "ability_modifiers": {
            ability.value: sheet.ability_scores.modifier(ability)
            for ability in AbilityName
        },
        "ac": compute_ac(sheet),
        "initiative": compute_initiative(sheet),
        "passive_perception": passive_perception(sheet),
        "passive_investigation": passive_investigation(sheet),
        "passive_insight": passive_insight(sheet),
        "saving_throws": {
            ability.value: saving_throw_modifier(sheet, ability)
            for ability in AbilityName
        },
        "skills": {
            skill.value: skill_modifier(sheet, skill)
            for skill in Skill
        },
        "spell_save_dc": spell_save_dc(sheet),           # 主施法职业 DC（向后兼容）
        "spell_attack_bonus": spell_attack_bonus(sheet), # 主施法职业攻击加值（向后兼容）
        "spell_stats_by_class": spell_stats_by_class(sheet),  # 多职业各自的 DC/攻击加值
        "carry_capacity": carry_capacity(sheet),
        "current_load": current_load(sheet),
        "encumbered": is_encumbered(sheet),
        "exhaustion_penalty": exhaustion_penalty(sheet),
        # 效果汇总
        "hp_max_effective": sheet.hit_points.maximum + hp_max_mod,
        "speed_effective": sheet.speed.walk + sheet.speed.temp_modifier + speed_mod,
    }
    return stats
