"""
怪物数据模型

覆盖 D&D 5e 2024 版怪物手册所有 stat block 字段。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ================================================================
#  子模型
# ================================================================

class MonsterAbilities(BaseModel):
    """六维属性"""
    str: int = 10
    dex: int = 10
    con: int = 10
    int_: int = 10   # int 是 Python 保留字，用 int_
    wis: int = 10
    cha: int = 10

    def modifier(self, ability: str) -> int:
        score = getattr(self, ability if ability != "int" else "int_", 10)
        return (score - 10) // 2

    class Config:
        populate_by_name = True


class MonsterAction(BaseModel):
    """一个特质、动作、反应或传奇动作条目"""
    name: str
    name_en: str = ""
    description: str
    # action / bonus_action / reaction / legendary / lair / trait
    action_type: str = "action"
    # 充能信息，如 "(充能 6)" "(3/日)"
    recharge: str = ""


# ================================================================
#  主模型
# ================================================================

_NAMESPACE_MONSTER = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _monster_id(name_cn: str) -> str:
    """根据中文名生成确定性 UUID，保证同名怪物跨解析运行 ID 相同。"""
    return str(uuid.uuid5(_NAMESPACE_MONSTER, name_cn.strip()))


class Monster(BaseModel):
    id: str = ""  # 由 model_validator 填充，或由调用方设置

    # ---- 基础信息 ----
    name_cn: str
    name_en: str = ""
    size: str = ""           # 微型/小型/中型/大型/超大型/巨型
    creature_type: str = ""  # 亡灵/天族/构装/龙类/…
    subtype: str = ""        # 如"（精灵）"
    alignment: str = ""

    # ---- 战斗数值 ----
    ac: int = 10
    ac_note: str = ""        # 如"（天然护甲）""（镶钉皮甲）"
    hp: int = 0
    hp_formula: str = ""     # 如"11d8+33"
    speed: str = ""          # 如"30尺，飞行60尺（悬浮）"
    initiative_bonus: int = 0

    # ---- 属性 ----
    abilities: MonsterAbilities = Field(default_factory=MonsterAbilities)

    # ---- 豁免加值（仅熟练的项）----
    saving_throws: dict[str, int] = Field(default_factory=dict)

    # ---- 技能加值（仅熟练的项）----
    skills: dict[str, int] = Field(default_factory=dict)

    # ---- 伤害 ----
    damage_vulnerabilities: list[str] = Field(default_factory=list)
    damage_resistances: list[str] = Field(default_factory=list)
    damage_immunities: list[str] = Field(default_factory=list)
    condition_immunities: list[str] = Field(default_factory=list)

    # ---- 感官 ----
    senses: str = ""
    passive_perception: int = 10

    # ---- 语言 ----
    languages: str = ""

    # ---- 挑战等级 ----
    cr: str = ""      # "1/4" / "1" / "21" 等
    xp: int = 0
    proficiency_bonus: int = 0  # PB

    # ---- 装备（部分怪物有）----
    equipment: str = ""

    # ---- 行动条目 ----
    traits: list[MonsterAction] = Field(default_factory=list)
    actions: list[MonsterAction] = Field(default_factory=list)
    bonus_actions: list[MonsterAction] = Field(default_factory=list)
    reactions: list[MonsterAction] = Field(default_factory=list)
    legendary_actions: list[MonsterAction] = Field(default_factory=list)
    legendary_action_desc: str = ""  # 传奇动作前的说明文字
    lair_actions: list[MonsterAction] = Field(default_factory=list)
    mythic_actions: list[MonsterAction] = Field(default_factory=list)

    # ---- 来源 ----
    source: str = "MM 2024"
    source_file: str = ""    # HTM 文件相对路径
    tags: list[str] = Field(default_factory=list)

    # ---- 时间戳 ----
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )

    # ---- 运行时（不持久化）----
    is_seed: bool = False   # True = 内置种子数据

    def model_post_init(self, __context: object) -> None:
        """如果 id 未设置，从 name_cn 生成确定性 UUID。"""
        if not self.id and self.name_cn:
            object.__setattr__(self, "id", _monster_id(self.name_cn))

    @property
    def display_name(self) -> str:
        if self.name_en:
            return f"{self.name_cn} {self.name_en}"
        return self.name_cn

    @property
    def cr_display(self) -> str:
        cr_map = {
            "0": "0", "1/8": "1/8", "1/4": "1/4", "1/2": "1/2",
        }
        return cr_map.get(self.cr, self.cr)


# ================================================================
#  API 请求/响应模型
# ================================================================

class MonsterImportRequest(BaseModel):
    """从 HTM 路径批量解析并导入怪物"""
    path: str                        # HTM 文件或目录路径
    source: str = "MM 2024"
    overwrite: bool = False          # 是否覆盖同名怪物


class MonsterImportResponse(BaseModel):
    success: bool
    imported: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str = ""


class MonsterSummary(BaseModel):
    """列表页用的轻量摘要"""
    id: str
    name_cn: str
    name_en: str
    size: str
    creature_type: str
    alignment: str
    ac: int
    hp: int
    cr: str
    source: str


class MonsterListResponse(BaseModel):
    """怪物列表分页响应（供客户端统一解析）"""
    monsters: list[MonsterSummary]
    total: int
    limit: int
    offset: int
