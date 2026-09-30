"""
人物卡建卡器

提供组合式 API，从零开始构建一张 CharacterSheet：
    1. 选择属性生成方式（标准阵列 / 点数购买 / 掷骰 / 手动）
    2. 应用物种（species）
    3. 应用背景（background）
    4. 应用职业（可多职业）
    5. 设置技能/豁免熟练
    6. finalize() 计算派生值（最大 HP、AC 缓存等）

设计原则:
- **纯组合，不自动选择**: 调用者决定每一步用什么，builder 只负责把选择落到 sheet 上
- **手动 override 一律标记 non_standard=True**: 便于 DM 审批
- **预设是内置的最小集合**: 方便测试和快速建卡，真实游戏里的物种/背景/职业应由规则库或前端下拉菜单提供

与规则库的关系:
- builder 只存名字和基本数据，具体特性文本由规则库检索
- 比如 `apply_species(sheet, "Elf")` 只写物种名、基本速度、darkvision 等硬数据，
  精灵的 "Trance"、"Fey Ancestry" 这些需要规则库回答
"""

from __future__ import annotations

import random
from typing import Literal

from .models import (
    AbilityName,
    AbilityScores,
    ArmorCategory,
    Background,
    BuildMethod,
    CharacterSheet,
    ClassLevel,
    HitPoints,
    Item,
    ItemType,
    ProficiencyLevel,
    SavingThrowProficiencies,
    Senses,
    Size,
    Skill,
    Species,
    Speed,
)
from .calculator import (
    compute_ac,
    max_hp_by_formula,
    ability_modifier,
)


# ============================================================
#  属性生成
# ============================================================

STANDARD_ARRAY: list[int] = [15, 14, 13, 12, 10, 8]


# 点数购买成本表 (PHB)
POINT_BUY_COST: dict[int, int] = {
    8: 0, 9: 1, 10: 2, 11: 3, 12: 4,
    13: 5, 14: 7, 15: 9,
}


def point_buy_cost(scores: dict[AbilityName, int]) -> int:
    """
    计算一套属性在点数购买规则下的总成本。
    有超出 [8, 15] 的分数会抛 ValueError。
    """
    total = 0
    for ability, score in scores.items():
        if score not in POINT_BUY_COST:
            raise ValueError(
                f"属性 {ability.value}={score} 超出点数购买合法范围 (8-15)"
            )
        total += POINT_BUY_COST[score]
    return total


def point_buy_valid(scores: dict[AbilityName, int], budget: int = 27) -> bool:
    """检查一套属性是否符合 27 点购买规则（默认预算 27）"""
    try:
        return point_buy_cost(scores) <= budget
    except ValueError:
        return False


def roll_4d6_drop_lowest(rng: random.Random | None = None) -> int:
    """掷 4d6 去最低：返回单个属性值"""
    rng = rng or random.Random()
    rolls = sorted(rng.randint(1, 6) for _ in range(4))
    return sum(rolls[1:])  # 去掉最低


def roll_ability_array(rng: random.Random | None = None) -> list[int]:
    """生成 6 个属性值（4d6 去最低 × 6）"""
    return [roll_4d6_drop_lowest(rng) for _ in range(6)]


def apply_ability_scores(
    sheet: CharacterSheet,
    scores: dict[AbilityName, int],
    method: BuildMethod,
) -> CharacterSheet:
    """
    把属性值写入 sheet。
    如果 method=MANUAL 或 method=POINT_BUY 但预算超标，会打 non_standard 标记。
    """
    for ability, value in scores.items():
        if value < 1 or value > 30:
            raise ValueError(f"属性值 {value} 超出合法范围 [1, 30]")
        setattr(sheet.ability_scores, ability.value, value)

    sheet.build_method = method

    if method == BuildMethod.MANUAL:
        sheet.non_standard = True
    elif method == BuildMethod.POINT_BUY and not point_buy_valid(scores):
        sheet.non_standard = True
    elif method == BuildMethod.STANDARD_ARRAY:
        actual = sorted(scores.values())
        if actual != sorted(STANDARD_ARRAY):
            sheet.non_standard = True

    return sheet


# ============================================================
#  物种预设
# ============================================================

SPECIES_PRESETS: dict[str, Species] = {
    "Human": Species(
        name="Human",
        lineage="",
        size=Size.MEDIUM,
        base_walking_speed=30,
        traits=["Resourceful", "Skillful", "Versatile"],
    ),
    "Elf": Species(
        name="Elf",
        lineage="High Elf",
        size=Size.MEDIUM,
        base_walking_speed=30,
        granted_senses={"darkvision": 60},
        traits=["Darkvision", "Fey Ancestry", "Keen Senses", "Trance"],
    ),
    "Dwarf": Species(
        name="Dwarf",
        lineage="",
        size=Size.MEDIUM,
        base_walking_speed=30,
        granted_senses={"darkvision": 120},
        traits=["Darkvision", "Dwarven Resilience", "Dwarven Toughness", "Stonecunning"],
    ),
    "Halfling": Species(
        name="Halfling",
        lineage="",
        size=Size.SMALL,
        base_walking_speed=30,
        traits=["Brave", "Halfling Nimbleness", "Luck", "Naturally Stealthy"],
    ),
    "Tiefling": Species(
        name="Tiefling",
        lineage="Abyssal",
        size=Size.MEDIUM,
        base_walking_speed=30,
        granted_senses={"darkvision": 60},
        traits=["Darkvision", "Fiendish Legacy", "Otherworldly Presence"],
    ),
    "Dragonborn": Species(
        name="Dragonborn",
        lineage="Red",
        size=Size.MEDIUM,
        base_walking_speed=30,
        traits=["Breath Weapon", "Damage Resistance", "Draconic Ancestry", "Darkvision"],
        granted_senses={"darkvision": 60},
    ),
}


def apply_species(sheet: CharacterSheet, species_name: str) -> CharacterSheet:
    """
    按预设应用物种。
    未知物种名会被当作手动自定义，打 non_standard 并只写一个空壳。
    """
    preset = SPECIES_PRESETS.get(species_name)
    if preset is None:
        # 自定义物种: 打标记，只填名字
        sheet.species = Species(name=species_name)
        sheet.non_standard = True
    else:
        # Pydantic 深拷贝避免共享引用
        sheet.species = preset.model_copy(deep=True)

    # 同步速度与感知到 sheet 顶层缓存字段
    sheet.speed.walk = sheet.species.base_walking_speed
    for kind, distance in sheet.species.granted_senses.items():
        if hasattr(sheet.senses, kind):
            current = getattr(sheet.senses, kind)
            if distance > current:
                setattr(sheet.senses, kind, distance)

    return sheet


# ============================================================
#  背景预设 (2024 版)
# ============================================================

BACKGROUND_PRESETS: dict[str, Background] = {
    "Soldier": Background(
        name="Soldier",
        origin_feat="Savage Attacker",
        ability_score_bonuses={
            AbilityName.STR: 2,
            AbilityName.CON: 1,
        },
        skill_proficiencies=[Skill.ATHLETICS, Skill.INTIMIDATION],
        tool_proficiencies=["Gaming Set"],
        starting_equipment=["Spear", "Shortbow", "20 arrows", "Gaming set", "Healer's kit"],
    ),
    "Acolyte": Background(
        name="Acolyte",
        origin_feat="Magic Initiate (Cleric)",
        ability_score_bonuses={
            AbilityName.INT: 2,
            AbilityName.WIS: 1,
        },
        skill_proficiencies=[Skill.INSIGHT, Skill.RELIGION],
        languages=["Two of your choice"],
    ),
    "Criminal": Background(
        name="Criminal",
        origin_feat="Alert",
        ability_score_bonuses={
            AbilityName.DEX: 2,
            AbilityName.INT: 1,
        },
        skill_proficiencies=[Skill.SLEIGHT_OF_HAND, Skill.STEALTH],
        tool_proficiencies=["Thieves' Tools"],
    ),
    "Sage": Background(
        name="Sage",
        origin_feat="Magic Initiate (Wizard)",
        ability_score_bonuses={
            AbilityName.CON: 1,
            AbilityName.INT: 2,
        },
        skill_proficiencies=[Skill.ARCANA, Skill.HISTORY],
        languages=["Two of your choice"],
    ),
    "Folk Hero": Background(
        name="Folk Hero",
        origin_feat="Lucky",
        ability_score_bonuses={
            AbilityName.CON: 2,
            AbilityName.WIS: 1,
        },
        skill_proficiencies=[Skill.ANIMAL_HANDLING, Skill.SURVIVAL],
        tool_proficiencies=["Artisan's Tools"],
    ),
}


def apply_background(
    sheet: CharacterSheet,
    background_name: str,
    apply_ability_bonuses: bool = True,
) -> CharacterSheet:
    """
    应用背景。默认会把背景的属性加值应用到 sheet.ability_scores 上。
    技能熟练自动加到 sheet.skills。
    """
    preset = BACKGROUND_PRESETS.get(background_name)
    if preset is None:
        sheet.background = Background(name=background_name)
        sheet.non_standard = True
    else:
        sheet.background = preset.model_copy(deep=True)

    if apply_ability_bonuses:
        for ability, bonus in sheet.background.ability_score_bonuses.items():
            current = sheet.ability_scores.get(ability)
            setattr(sheet.ability_scores, ability.value, current + bonus)

    for skill in sheet.background.skill_proficiencies:
        if sheet.skills.get(skill) == ProficiencyLevel.NONE:
            sheet.skills.set(skill, ProficiencyLevel.PROFICIENT)

    for tool in sheet.background.tool_proficiencies:
        if tool not in sheet.tool_proficiencies:
            sheet.tool_proficiencies.append(tool)

    if sheet.background.origin_feat and not sheet.origin_feat:
        sheet.origin_feat = sheet.background.origin_feat

    return sheet


# ============================================================
#  职业预设
# ============================================================

class ClassPreset:
    """职业的规则硬数据。特性描述不在这里存。"""
    def __init__(
        self,
        name: str,
        hit_die: int,
        primary_abilities: list[AbilityName],
        saving_throws: list[AbilityName],
        armor_profs: list[ArmorCategory],
        weapon_profs: list[str],
        skill_choices: list[Skill],
        skill_choice_count: int = 2,
    ) -> None:
        self.name = name
        self.hit_die = hit_die
        self.primary_abilities = primary_abilities
        self.saving_throws = saving_throws
        self.armor_profs = armor_profs
        self.weapon_profs = weapon_profs
        self.skill_choices = skill_choices
        self.skill_choice_count = skill_choice_count


CLASS_PRESETS: dict[str, ClassPreset] = {
    "Fighter": ClassPreset(
        name="Fighter",
        hit_die=10,
        primary_abilities=[AbilityName.STR, AbilityName.DEX],
        saving_throws=[AbilityName.STR, AbilityName.CON],
        armor_profs=[ArmorCategory.LIGHT, ArmorCategory.MEDIUM, ArmorCategory.HEAVY, ArmorCategory.SHIELD],
        weapon_profs=["simple_melee", "simple_ranged", "martial_melee", "martial_ranged"],
        skill_choices=[
            Skill.ACROBATICS, Skill.ANIMAL_HANDLING, Skill.ATHLETICS,
            Skill.HISTORY, Skill.INSIGHT, Skill.INTIMIDATION,
            Skill.PERCEPTION, Skill.SURVIVAL,
        ],
    ),
    "Rogue": ClassPreset(
        name="Rogue",
        hit_die=8,
        primary_abilities=[AbilityName.DEX],
        saving_throws=[AbilityName.DEX, AbilityName.INT],
        armor_profs=[ArmorCategory.LIGHT],
        weapon_profs=["simple_melee", "simple_ranged", "martial_melee", "martial_ranged"],
        skill_choices=[
            Skill.ACROBATICS, Skill.ATHLETICS, Skill.DECEPTION,
            Skill.INSIGHT, Skill.INTIMIDATION, Skill.INVESTIGATION,
            Skill.PERCEPTION, Skill.PERFORMANCE, Skill.PERSUASION,
            Skill.SLEIGHT_OF_HAND, Skill.STEALTH,
        ],
        skill_choice_count=4,
    ),
    "Wizard": ClassPreset(
        name="Wizard",
        hit_die=6,
        primary_abilities=[AbilityName.INT],
        saving_throws=[AbilityName.INT, AbilityName.WIS],
        armor_profs=[],
        weapon_profs=["simple_melee", "simple_ranged"],
        skill_choices=[
            Skill.ARCANA, Skill.HISTORY, Skill.INSIGHT,
            Skill.INVESTIGATION, Skill.MEDICINE, Skill.RELIGION,
        ],
    ),
    "Cleric": ClassPreset(
        name="Cleric",
        hit_die=8,
        primary_abilities=[AbilityName.WIS],
        saving_throws=[AbilityName.WIS, AbilityName.CHA],
        armor_profs=[ArmorCategory.LIGHT, ArmorCategory.MEDIUM, ArmorCategory.SHIELD],
        weapon_profs=["simple_melee", "simple_ranged"],
        skill_choices=[
            Skill.HISTORY, Skill.INSIGHT, Skill.MEDICINE,
            Skill.PERSUASION, Skill.RELIGION,
        ],
    ),
    "Barbarian": ClassPreset(
        name="Barbarian",
        hit_die=12,
        primary_abilities=[AbilityName.STR],
        saving_throws=[AbilityName.STR, AbilityName.CON],
        armor_profs=[ArmorCategory.LIGHT, ArmorCategory.MEDIUM, ArmorCategory.SHIELD],
        weapon_profs=["simple_melee", "simple_ranged", "martial_melee", "martial_ranged"],
        skill_choices=[
            Skill.ANIMAL_HANDLING, Skill.ATHLETICS, Skill.INTIMIDATION,
            Skill.NATURE, Skill.PERCEPTION, Skill.SURVIVAL,
        ],
    ),
}


def apply_class(
    sheet: CharacterSheet,
    class_name: str,
    level: int = 1,
    subclass: str = "",
    is_primary: bool | None = None,
    chosen_skills: list[Skill] | None = None,
) -> CharacterSheet:
    """
    为 sheet 添加或升级一个职业等级。

    - 如果 class_name 已存在，则累加 level（不重复写熟练）
    - 如果是主职业且当前没有主职业，会自动接管主职业位
    - chosen_skills 只在首次加入此职业时应用
    """
    preset = CLASS_PRESETS.get(class_name)

    existing: ClassLevel | None = None
    for cls in sheet.class_levels:
        if cls.class_name.lower() == class_name.lower():
            existing = cls
            break

    if existing is not None:
        existing.level += level
        if subclass and not existing.subclass:
            existing.subclass = subclass
        return sheet

    # 首次加入此职业
    make_primary = is_primary if is_primary is not None else (len(sheet.class_levels) == 0)
    hit_die = preset.hit_die if preset else 8

    sheet.class_levels.append(
        ClassLevel(
            class_name=class_name,
            level=level,
            subclass=subclass,
            hit_die_size=hit_die,
            is_primary=make_primary,
        )
    )

    if preset is None:
        sheet.non_standard = True
        return sheet

    # 只有 1 级首加的职业才带豁免/护甲/武器熟练 (多职业规则只给部分)
    is_first_class = len(sheet.class_levels) == 1

    if is_first_class:
        sheet.saving_throws.proficient.update(preset.saving_throws)

        for armor in preset.armor_profs:
            if armor not in sheet.armor_proficiencies:
                sheet.armor_proficiencies.append(armor)
        for weap in preset.weapon_profs:
            if weap not in sheet.weapon_proficiencies:
                sheet.weapon_proficiencies.append(weap)

        if chosen_skills:
            if len(chosen_skills) > preset.skill_choice_count:
                sheet.non_standard = True
            for skill in chosen_skills:
                if skill not in preset.skill_choices:
                    sheet.non_standard = True
                if sheet.skills.get(skill) == ProficiencyLevel.NONE:
                    sheet.skills.set(skill, ProficiencyLevel.PROFICIENT)

    # 更新主职业生命骰（在 hit_points 上也记一份）
    if make_primary:
        sheet.hit_points.hit_die_size = hit_die
    sheet.hit_points.hit_dice_total = sum(c.level for c in sheet.class_levels)

    return sheet


# ============================================================
#  finalize
# ============================================================

def finalize(sheet: CharacterSheet, recompute_hp: bool = True) -> CharacterSheet:
    """
    结算派生值：
    - 最大 HP（若 recompute_hp=True）
    - armor_class_cache
    - initiative_bonus = DEX 修正
    """
    if recompute_hp:
        hp = max_hp_by_formula(sheet)
        sheet.hit_points.maximum = hp
        if sheet.hit_points.current == 0 or sheet.hit_points.current > hp:
            sheet.hit_points.current = hp

    sheet.armor_class_cache = compute_ac(sheet)
    sheet.initiative_bonus = ability_modifier(sheet.ability_scores.dexterity)
    return sheet


# ============================================================
#  一站式 build
# ============================================================

def build_character(
    name: str,
    owner_id: str,
    owner_display: str = "",
    *,
    ability_scores: dict[AbilityName, int],
    build_method: BuildMethod = BuildMethod.STANDARD_ARRAY,
    species: str = "",
    background: str = "",
    class_name: str = "",
    level: int = 1,
    subclass: str = "",
    chosen_skills: list[Skill] | None = None,
    campaign_id: str | None = None,
    edition: Literal["2024", "2014"] = "2024",
) -> CharacterSheet:
    """
    一次性构建完整人物卡的便捷函数。
    适用于快速创建测试角色或 DM 出 NPC。
    """
    sheet = CharacterSheet(
        name=name,
        owner_id=owner_id,
        owner_display=owner_display or owner_id,
        campaign_id=campaign_id,
        edition=edition,
    )

    apply_ability_scores(sheet, ability_scores, build_method)

    if species:
        apply_species(sheet, species)
    if background:
        apply_background(sheet, background)
    if class_name:
        apply_class(sheet, class_name, level=level, subclass=subclass, chosen_skills=chosen_skills)

    finalize(sheet)
    return sheet


# ============================================================
#  辅助：属性值分配
# ============================================================

def assign_ability_pool(
    pool: list[int],
    ordering: list[AbilityName],
) -> dict[AbilityName, int]:
    """
    把一个数值池按顺序分配给 6 个属性。
    用于: apply_ability_scores(sheet, assign_ability_pool(STANDARD_ARRAY, [STR, DEX, ...]), BuildMethod.STANDARD_ARRAY)
    """
    if len(pool) != len(ordering):
        raise ValueError(f"pool 长度 {len(pool)} != ordering 长度 {len(ordering)}")
    if len(ordering) != 6 or len(set(ordering)) != 6:
        raise ValueError("ordering 必须恰好是六项属性各一次")
    return dict(zip(ordering, pool))
