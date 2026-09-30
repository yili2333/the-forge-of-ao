"""
人物卡数据模型 (D&D 5e 2024 版)

设计原则:
1. 纯数据，不含计算逻辑（计算放在 calculator.py）
2. Pydantic v2，所有字段有合理默认值（方便部分构建）
3. 与现有 src/models.py (规则相关) 完全独立
4. 序列化友好（dict 而非 tuple，避免 Pydantic tuple 反序列化坑）
5. 支持 2024 版特有机制：weapon mastery、heroic inspiration、10 级耗竭、background origin feat
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
#  通用枚举
# ============================================================

class AbilityName(str, Enum):
    STR = "strength"
    DEX = "dexterity"
    CON = "constitution"
    INT = "intelligence"
    WIS = "wisdom"
    CHA = "charisma"


class Size(str, Enum):
    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"
    GARGANTUAN = "gargantuan"


class Skill(str, Enum):
    """D&D 5e 18 项技能"""
    ACROBATICS = "acrobatics"
    ANIMAL_HANDLING = "animal_handling"
    ARCANA = "arcana"
    ATHLETICS = "athletics"
    DECEPTION = "deception"
    HISTORY = "history"
    INSIGHT = "insight"
    INTIMIDATION = "intimidation"
    INVESTIGATION = "investigation"
    MEDICINE = "medicine"
    NATURE = "nature"
    PERCEPTION = "perception"
    PERFORMANCE = "performance"
    PERSUASION = "persuasion"
    RELIGION = "religion"
    SLEIGHT_OF_HAND = "sleight_of_hand"
    STEALTH = "stealth"
    SURVIVAL = "survival"


# 技能 → 关联属性
SKILL_ABILITY: dict[Skill, AbilityName] = {
    Skill.ACROBATICS: AbilityName.DEX,
    Skill.ANIMAL_HANDLING: AbilityName.WIS,
    Skill.ARCANA: AbilityName.INT,
    Skill.ATHLETICS: AbilityName.STR,
    Skill.DECEPTION: AbilityName.CHA,
    Skill.HISTORY: AbilityName.INT,
    Skill.INSIGHT: AbilityName.WIS,
    Skill.INTIMIDATION: AbilityName.CHA,
    Skill.INVESTIGATION: AbilityName.INT,
    Skill.MEDICINE: AbilityName.WIS,
    Skill.NATURE: AbilityName.INT,
    Skill.PERCEPTION: AbilityName.WIS,
    Skill.PERFORMANCE: AbilityName.CHA,
    Skill.PERSUASION: AbilityName.CHA,
    Skill.RELIGION: AbilityName.INT,
    Skill.SLEIGHT_OF_HAND: AbilityName.DEX,
    Skill.STEALTH: AbilityName.DEX,
    Skill.SURVIVAL: AbilityName.WIS,
}


class ProficiencyLevel(str, Enum):
    NONE = "none"               # 无熟练
    HALF = "half"               # 半熟练 (Jack of All Trades 等)
    PROFICIENT = "proficient"   # 熟练
    EXPERTISE = "expertise"     # 专精 (双倍熟练加值)


class DamageType(str, Enum):
    ACID = "acid"
    BLUDGEONING = "bludgeoning"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    PIERCING = "piercing"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    SLASHING = "slashing"
    THUNDER = "thunder"


class Condition(str, Enum):
    """D&D 5e 标准状态（2024 版相同）"""
    BLINDED = "blinded"
    CHARMED = "charmed"
    DEAFENED = "deafened"
    FRIGHTENED = "frightened"
    GRAPPLED = "grappled"
    INCAPACITATED = "incapacitated"
    INVISIBLE = "invisible"
    PARALYZED = "paralyzed"
    PETRIFIED = "petrified"
    POISONED = "poisoned"
    PRONE = "prone"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    UNCONSCIOUS = "unconscious"


# ============================================================
#  装备相关
# ============================================================

class ItemType(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    SHIELD = "shield"
    TOOL = "tool"
    GEAR = "gear"
    CONSUMABLE = "consumable"
    TREASURE = "treasure"
    MAGIC_ITEM = "magic_item"
    AMMUNITION = "ammunition"
    OTHER = "other"


class ArmorCategory(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"


class WeaponCategory(str, Enum):
    SIMPLE_MELEE = "simple_melee"
    SIMPLE_RANGED = "simple_ranged"
    MARTIAL_MELEE = "martial_melee"
    MARTIAL_RANGED = "martial_ranged"


class WeaponProperty(str, Enum):
    """武器属性 (2024 版与 2014 大体相同)"""
    AMMUNITION = "ammunition"
    FINESSE = "finesse"
    HEAVY = "heavy"
    LIGHT = "light"
    LOADING = "loading"
    RANGE = "range"
    REACH = "reach"
    SPECIAL = "special"
    THROWN = "thrown"
    TWO_HANDED = "two_handed"
    VERSATILE = "versatile"


class WeaponMastery(str, Enum):
    """2024 版新增: 武器精通 (Mastery)"""
    CLEAVE = "cleave"
    GRAZE = "graze"
    NICK = "nick"
    PUSH = "push"
    SAP = "sap"
    SLOW = "slow"
    TOPPLE = "topple"
    VEX = "vex"


class Item(BaseModel):
    """
    通用物品。武器/护甲/普通物品共享一个模型，
    通过 item_type + 可选字段区分。这样比 discriminated union 简单。
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    item_type: ItemType = ItemType.OTHER
    description: str = ""

    quantity: int = 1
    weight: float = 0.0
    cost_gp: float = 0.0

    equipped: bool = False
    attuned: bool = False           # 魔法物品协调
    requires_attunement: bool = False

    # ----- 武器字段 (item_type=weapon 时使用) -----
    weapon_category: WeaponCategory | None = None
    damage_dice: str = ""           # "1d8"
    damage_type: DamageType | None = None
    versatile_dice: str = ""        # "1d10" (versatile 单手→双手)
    weapon_properties: list[WeaponProperty] = Field(default_factory=list)
    mastery: WeaponMastery | None = None        # 2024 新增
    range_normal: int = 0           # 英尺
    range_long: int = 0
    thrown_range_normal: int = 0
    thrown_range_long: int = 0

    # ----- 护甲字段 (item_type=armor/shield 时使用) -----
    armor_category: ArmorCategory | None = None
    armor_class_base: int = 0       # 护甲基础 AC
    armor_max_dex_bonus: int | None = None  # 中甲 = 2，重甲 = 0，轻甲 = None(无限)
    armor_strength_required: int = 0
    armor_stealth_disadvantage: bool = False

    # ----- 魔法物品 -----
    is_magical: bool = False
    magical_bonus: int = 0          # +1/+2/+3
    rarity: Literal["common", "uncommon", "rare", "very_rare", "legendary", "artifact", ""] = ""

    # ----- 自由字段 -----
    notes: str = ""


# ============================================================
#  属性、技能、豁免
# ============================================================

class AbilityScores(BaseModel):
    """六维属性。修正值通过 .modifier() 计算，不存储。"""
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    def get(self, ability: AbilityName | str) -> int:
        key = ability.value if isinstance(ability, AbilityName) else ability
        return getattr(self, key, 10)

    def modifier(self, ability: AbilityName | str) -> int:
        return (self.get(ability) - 10) // 2


class SkillProficiencies(BaseModel):
    """每个技能的熟练等级。默认全部 NONE。"""
    levels: dict[Skill, ProficiencyLevel] = Field(default_factory=dict)

    def get(self, skill: Skill) -> ProficiencyLevel:
        return self.levels.get(skill, ProficiencyLevel.NONE)

    def set(self, skill: Skill, level: ProficiencyLevel) -> None:
        if level == ProficiencyLevel.NONE:
            self.levels.pop(skill, None)
        else:
            self.levels[skill] = level


class SavingThrowProficiencies(BaseModel):
    """六个豁免的熟练情况"""
    proficient: set[AbilityName] = Field(default_factory=set)


# ============================================================
#  HP / 死亡豁免 / 速度 / 感知
# ============================================================

class DeathSaves(BaseModel):
    successes: int = Field(default=0, ge=0, le=3)
    failures: int = Field(default=0, ge=0, le=3)
    stable: bool = False            # 已稳定 (不再需要继续掷)

    def reset(self) -> None:
        self.successes = 0
        self.failures = 0
        self.stable = False


class HitPoints(BaseModel):
    current: int = 0
    maximum: int = 0
    temporary: int = 0

    # 生命骰
    hit_die_size: int = 8           # d6/d8/d10/d12 中的数字部分
    hit_dice_total: int = 1
    hit_dice_used: int = 0

    death_saves: DeathSaves = Field(default_factory=DeathSaves)

    @property
    def is_dying(self) -> bool:
        return self.current <= 0 and not self.death_saves.stable

    @property
    def is_dead(self) -> bool:
        return self.death_saves.failures >= 3

    @property
    def hit_dice_remaining(self) -> int:
        return max(0, self.hit_dice_total - self.hit_dice_used)


class Speed(BaseModel):
    """
    多模式速度。所有单位为英尺。
    walk 是基础，其余按需添加。
    """
    walk: int = 30
    fly: int = 0
    swim: int = 0
    climb: int = 0
    burrow: int = 0
    hover: bool = False             # 飞行带 hover

    # 临时修正（饥寒/法术等导致的减速或加速）
    temp_modifier: int = 0          # 应用到 walk 上


class Senses(BaseModel):
    """
    特殊感知。
    被动检定值由 calculator 计算，这里只存基础数据。
    """
    darkvision: int = 0             # 英尺
    blindsight: int = 0
    tremorsense: int = 0
    truesight: int = 0


# ============================================================
#  效果与资源
# ============================================================

class DurationType(str, Enum):
    INSTANTANEOUS = "instantaneous"
    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    UNTIL_END_OF_TURN = "until_end_of_turn"
    UNTIL_START_OF_NEXT_TURN = "until_start_of_next_turn"
    UNTIL_LONG_REST = "until_long_rest"
    UNTIL_SHORT_REST = "until_short_rest"
    UNTIL_DISPELLED = "until_dispelled"
    CONCENTRATION = "concentration"
    PERMANENT = "permanent"


class ActiveEffect(BaseModel):
    """
    当前生效的效果。
    可以来自法术、物品、状态、特性等。
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    source: str = ""                # "spell:Shield of Faith" / "feat:Tough" 等
    description: str = ""

    # ----- 数值修正 -----
    ac_bonus: int = 0
    attack_bonus: int = 0
    damage_bonus: str = ""          # "1d6 fire"
    save_bonus: int = 0
    speed_modifier: int = 0
    hp_max_modifier: int = 0

    # ----- 优势/劣势 -----
    advantage_on: list[str] = Field(default_factory=list)
    disadvantage_on: list[str] = Field(default_factory=list)

    # ----- 关联状态 -----
    grants_conditions: list[Condition] = Field(default_factory=list)

    # ----- 持续时间 -----
    duration_type: DurationType = DurationType.PERMANENT
    duration_value: int = 0         # rounds/minutes/hours 时使用
    started_at_round: int = 0       # 战斗开始后第几轮施加

    # ----- 集中 -----
    concentration: bool = False
    caster_id: str = ""             # 集中法术的施法者 character_id


class ClassResource(BaseModel):
    """
    职业资源 (Ki / Rage / Channel Divinity / Bardic Inspiration / 等)
    """
    name: str                       # "Ki Points"
    current: int = 0
    maximum: int = 0
    recharge: Literal["short_rest", "long_rest", "dawn", "manual"] = "long_rest"


# ============================================================
#  法术
# ============================================================

class SpellSlot(BaseModel):
    maximum: int = 0
    current: int = 0


class SpellSlots(BaseModel):
    """
    用 dict 存法术位等级 → SpellSlot，比 9 个独立字段干净。
    Pact Magic 的法术位单独建模 (warlock 用 pact_slots)。
    """
    slots: dict[int, SpellSlot] = Field(default_factory=dict)
    # 例: {1: SpellSlot(max=4, current=2), 2: SpellSlot(max=3, current=3)}

    pact_level: int = 0             # warlock pact magic 法术位等级
    pact_slots: SpellSlot = Field(default_factory=SpellSlot)

    def available(self, level: int) -> int:
        slot = self.slots.get(level)
        return slot.current if slot else 0

    def maximum(self, level: int) -> int:
        slot = self.slots.get(level)
        return slot.maximum if slot else 0


class KnownSpell(BaseModel):
    """已知/已准备的法术（仅记录引用，规则细节走规则库查询）"""
    name: str                       # "Fire Bolt"
    level: int                      # 0 = cantrip
    prepared: bool = False
    always_prepared: bool = False   # 域法术、誓约法术等
    source_class: str = ""          # 多职业时区分来源
    notes: str = ""


# ============================================================
#  物种 / 背景 / 职业
# ============================================================

class Species(BaseModel):
    """
    2024 版物种 (取代 race)
    具体特性细节由规则库提供，这里只存名字和关键字段。
    """
    name: str = ""                  # "Elf"
    lineage: str = ""               # "High Elf" / "Wood Elf"
    size: Size = Size.MEDIUM
    base_walking_speed: int = 30

    # 内置感知（如精灵 darkvision 60）
    granted_senses: dict[str, int] = Field(default_factory=dict)

    # 物种特性名（详细规则查规则库）
    traits: list[str] = Field(default_factory=list)

    # 物种法术 (如高等精灵的戏法)
    innate_spells: list[str] = Field(default_factory=list)

    # 速度 (除步行外的)
    extra_speeds: dict[str, int] = Field(default_factory=dict)


class Background(BaseModel):
    """
    2024 版背景。给的东西比 2014 多得多:
    - 1 个起源专长 (origin feat)
    - +2/+1 或 三个 +1 的属性加值
    - 2 项技能熟练
    - 1 项工具熟练
    - 装备包
    """
    name: str = ""                  # "Soldier"
    origin_feat: str = ""           # 来自背景的初始专长
    ability_score_bonuses: dict[AbilityName, int] = Field(default_factory=dict)
    skill_proficiencies: list[Skill] = Field(default_factory=list)
    tool_proficiencies: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    starting_equipment: list[str] = Field(default_factory=list)


class ClassLevel(BaseModel):
    """
    职业等级条目。多职业时一个角色有多个 ClassLevel。
    """
    class_name: str                 # "Rogue"
    level: int = 1
    subclass: str = ""              # "Assassin" / "Battle Master" 等
    hit_die_size: int = 8           # d6/d8/d10/d12
    is_primary: bool = True         # 多职业时的主要职业（决定 background HP 等）

    # 此职业等级里手动选择的特性（如战斗风格、邪术等）
    chosen_features: list[str] = Field(default_factory=list)


# ============================================================
#  建卡元数据
# ============================================================

class BuildMethod(str, Enum):
    """属性获取方式"""
    STANDARD_ARRAY = "standard_array"   # 15,14,13,12,10,8
    POINT_BUY = "point_buy"             # 27 点购买
    ROLLED = "rolled"                   # 4d6 弃 1
    MANUAL = "manual"                   # 手填，由 DM 仲裁


# ============================================================
#  CharacterSheet 主模型
# ============================================================

class CharacterSheet(BaseModel):
    """
    完整人物卡 (D&D 5e 2024)

    字段量大但结构清晰。计算属性 (AC/被动值/法术豁免DC) 不存储，
    由 calculator.py 提供 stateless 函数计算。
    """

    # ===== 身份 =====
    id: str = Field(default_factory=lambda: f"char-{uuid.uuid4().hex[:10]}")
    owner_id: str = ""              # IdentityManager.stable_key
    owner_display: str = ""         # "Tanrui#7281" 显示用
    campaign_id: str | None = None  # null = 自由卡，未绑定到战役

    name: str = "Unnamed Adventurer"
    edition: Literal["2024", "2014"] = "2024"

    # ===== 建卡元数据 =====
    build_method: BuildMethod = BuildMethod.STANDARD_ARRAY
    non_standard: bool = False      # 是否使用了手动 override (DM 需审批)
    dm_approved: bool = False       # DM 审批通过
    dm_approval_note: str = ""

    # ===== 物种 / 背景 / 职业 =====
    species: Species = Field(default_factory=Species)
    background: Background = Field(default_factory=Background)
    class_levels: list[ClassLevel] = Field(default_factory=list)

    @property
    def total_level(self) -> int:
        return sum(c.level for c in self.class_levels)

    @property
    def proficiency_bonus(self) -> int:
        """根据角色总等级返回熟练加值"""
        lvl = self.total_level
        if lvl <= 0:
            return 2
        return 2 + (max(1, lvl) - 1) // 4

    # ===== 属性 =====
    ability_scores: AbilityScores = Field(default_factory=AbilityScores)

    # ===== 熟练 =====
    skills: SkillProficiencies = Field(default_factory=SkillProficiencies)
    saving_throws: SavingThrowProficiencies = Field(default_factory=SavingThrowProficiencies)
    weapon_proficiencies: list[str] = Field(default_factory=list)
    armor_proficiencies: list[ArmorCategory] = Field(default_factory=list)
    tool_proficiencies: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    # ===== HP / 死亡豁免 =====
    hit_points: HitPoints = Field(default_factory=HitPoints)

    # ===== 速度 / 感知 =====
    speed: Speed = Field(default_factory=Speed)
    senses: Senses = Field(default_factory=Senses)

    # ===== 防御 (运行时缓存，可由 calculator 重算) =====
    armor_class_cache: int = 10
    initiative_bonus: int = 0       # 通常 = DEX 修正 + 其他

    # ===== 抗性 / 免疫 / 易伤 =====
    damage_resistances: list[DamageType] = Field(default_factory=list)
    damage_immunities: list[DamageType] = Field(default_factory=list)
    damage_vulnerabilities: list[DamageType] = Field(default_factory=list)
    condition_immunities: list[Condition] = Field(default_factory=list)

    # ===== 当前状态 =====
    conditions: list[Condition] = Field(default_factory=list)
    exhaustion_level: int = Field(default=0, ge=0, le=10)   # 2024: 0-10
    heroic_inspiration: bool = False                         # 2024: 替代旧 Inspiration
    active_effects: list[ActiveEffect] = Field(default_factory=list)

    # ===== 动作经济（战斗中追踪） =====
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False
    movement_used: int = 0                                   # 已消耗的移动力（英尺）

    # ===== 装备 =====
    inventory: list[Item] = Field(default_factory=list)
    gold: float = 0.0
    silver: float = 0.0
    copper: float = 0.0
    platinum: float = 0.0
    electrum: float = 0.0

    # ===== 施法 =====
    # 单职业施法者：只填 spellcasting_ability（向后兼容）
    # 多职业施法者：填 spellcasting_abilities dict，key = 职业名，value = 施法属性
    #   示例：{"Wizard": "intelligence", "Cleric": "wisdom"}
    # 两个字段可共存；calculator 优先读 spellcasting_abilities，为空时回退 spellcasting_ability
    spellcasting_ability: AbilityName | None = None
    spellcasting_abilities: dict[str, AbilityName] = Field(default_factory=dict)
    spells_known: list[KnownSpell] = Field(default_factory=list)
    cantrips_known: list[KnownSpell] = Field(default_factory=list)
    spell_slots: SpellSlots = Field(default_factory=SpellSlots)
    concentration_effect_id: str = ""    # 当前集中的 ActiveEffect.id (对应 active_effects 里的项)

    # ===== 职业资源 =====
    class_resources: list[ClassResource] = Field(default_factory=list)

    # ===== 专长（2024 版分四种） =====
    origin_feat: str = ""           # 来自 background
    general_feats: list[str] = Field(default_factory=list)        # Lv4/8/12/16/19
    fighting_style_feats: list[str] = Field(default_factory=list) # 战士/圣武士等
    epic_boon: str = ""             # Lv19 专属

    # ===== 武器精通 (2024 新增) =====
    weapon_masteries_learned: list[WeaponMastery] = Field(default_factory=list)

    # ===== 角色描述 =====
    alignment: str = ""             # "Chaotic Good" 等
    age: str = ""
    height: str = ""
    weight: str = ""
    eyes: str = ""
    skin: str = ""
    hair: str = ""
    appearance: str = ""
    backstory: str = ""
    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    # ===== 变形状态 (Polymorph) =====
    is_polymorphed: bool = False
    polymorph_snapshot: dict | None = None   # 原始角色数据快照（model_dump），解除变形时恢复
    polymorph_monster_id: str = ""           # 当前变形的怪物 ID

    # ===== 经验值 (XP) =====
    xp_total: int = 0                        # 角色累计获得的总经验值（PHB milestone 系统可选不用）
    xp_to_next_level: int = 0               # 缓存：距下一级还需多少 XP（由 xp 系统计算填入）

    # ===== 时间戳 =====
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    version: int = 1                # 每次更新自增

    # ============================================================
    #  便捷方法 (无副作用的查询)
    # ============================================================

    def has_condition(self, condition: Condition | str) -> bool:
        target = condition if isinstance(condition, Condition) else Condition(condition)
        return target in self.conditions

    def get_class_level(self, class_name: str) -> int:
        for c in self.class_levels:
            if c.class_name.lower() == class_name.lower():
                return c.level
        return 0

    def equipped_weapons(self) -> list[Item]:
        return [
            i for i in self.inventory
            if i.equipped and i.item_type == ItemType.WEAPON
        ]

    def equipped_armor(self) -> Item | None:
        for i in self.inventory:
            if i.equipped and i.item_type == ItemType.ARMOR:
                return i
        return None

    def equipped_shield(self) -> Item | None:
        for i in self.inventory:
            if i.equipped and i.item_type == ItemType.SHIELD:
                return i
        return None

    def attuned_items(self) -> list[Item]:
        return [i for i in self.inventory if i.attuned]

    def is_spellcaster(self) -> bool:
        return self.spellcasting_ability is not None or bool(self.spellcasting_abilities)

    def primary_spellcasting_ability(self) -> AbilityName | None:
        """
        返回主要施法属性：
        - 多职业时返回主职业（is_primary=True）的施法属性
        - 单职业时返回 spellcasting_ability
        - 都没有时返回 None
        """
        if self.spellcasting_abilities:
            for cls in self.class_levels:
                if cls.is_primary and cls.class_name in self.spellcasting_abilities:
                    return self.spellcasting_abilities[cls.class_name]
            # 主职业未在 dict 里时，返回 dict 第一项
            return next(iter(self.spellcasting_abilities.values()))
        return self.spellcasting_ability

    # ============================================================
    #  上下文摘要 (给 LLM 用)
    # ============================================================

    def to_context_summary(self) -> str:
        """
        生成给规则 AI 的简明摘要。
        不包含完整背包/法术列表，只有当前关键状态。
        """
        from .calculator import compute_ac, passive_perception  # 懒导入避免循环

        weapons = self.equipped_weapons()
        weapon_str = (
            ", ".join(
                f"{w.name}({w.damage_dice}{' '+w.damage_type.value if w.damage_type else ''})"
                for w in weapons
            )
            if weapons else "无武器"
        )

        cls_str = (
            " / ".join(
                f"{c.class_name} Lv{c.level}"
                + (f" ({c.subclass})" if c.subclass else "")
                for c in self.class_levels
            )
            if self.class_levels else "无职业"
        )

        species_str = self.species.name or "未指定"
        if self.species.lineage:
            species_str += f" / {self.species.lineage}"

        ability = self.ability_scores
        ability_str = (
            f"STR {ability.strength}({ability.modifier('strength'):+d}) "
            f"DEX {ability.dexterity}({ability.modifier('dexterity'):+d}) "
            f"CON {ability.constitution}({ability.modifier('constitution'):+d}) "
            f"INT {ability.intelligence}({ability.modifier('intelligence'):+d}) "
            f"WIS {ability.wisdom}({ability.modifier('wisdom'):+d}) "
            f"CHA {ability.charisma}({ability.modifier('charisma'):+d})"
        )

        hp = self.hit_points
        hp_str = f"{hp.current}/{hp.maximum}"
        if hp.temporary:
            hp_str += f" (临时 {hp.temporary})"

        conditions_str = (
            ", ".join(c.value for c in self.conditions)
            if self.conditions else "无"
        )
        effects_str = (
            ", ".join(e.name for e in self.active_effects)
            if self.active_effects else "无"
        )

        # 法术位摘要
        slot_parts = []
        for lvl in sorted(self.spell_slots.slots.keys()):
            slot = self.spell_slots.slots[lvl]
            if slot.maximum > 0:
                slot_parts.append(f"L{lvl}:{slot.current}/{slot.maximum}")
        slot_str = ", ".join(slot_parts) if slot_parts else "无法术位"

        # 集中法术名
        conc_name = "无"
        if self.concentration_effect_id:
            for e in self.active_effects:
                if e.id == self.concentration_effect_id:
                    conc_name = e.name
                    break

        lines = [
            f"【角色】{self.name}",
            f"  物种: {species_str}",
            f"  职业: {cls_str}  熟练加值: +{self.proficiency_bonus}",
            f"  属性: {ability_str}",
            f"  HP: {hp_str}    AC: {self.armor_class_cache}    速度: {self.speed.walk}ft",
            f"  被动察觉: {passive_perception(self)}",
            f"  装备武器: {weapon_str}",
            f"  法术位: {slot_str}    集中: {conc_name}",
            f"  状态: {conditions_str}",
            f"  生效效果: {effects_str}",
        ]

        if self.heroic_inspiration:
            lines.append("  英雄激励: 持有")
        if self.exhaustion_level > 0:
            lines.append(f"  耗竭等级: {self.exhaustion_level}/10")

        if self.senses.darkvision:
            lines.append(f"  黑暗视觉: {self.senses.darkvision}ft")

        if self.damage_resistances:
            lines.append(
                f"  伤害抗性: {', '.join(d.value for d in self.damage_resistances)}"
            )

        return "\n".join(lines)
