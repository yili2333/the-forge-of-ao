"""
人物卡子系统

D&D 5e 2024 版人物卡的构建、计算、存储与 API。

模块布局:
    models      - Pydantic 数据模型 (CharacterSheet 及子模型)
    calculator  - AC/HP/被动值/属性修正等规则驱动的计算
    storage     - SQLite 持久化 + 快照 + 导入导出
    api         - FastAPI 路由 (/api/character/*)
    builder     - 组合式建卡器 (属性/物种/背景/职业预设)
    rule_bridge - 与规则 AI 的联通 (上下文注入 / 主题提取 / 动作预检)
"""

from .models import (
    CharacterSheet,
    AbilityScores,
    AbilityName,
    Size,
    Skill,
    Item,
    SpellSlots,
    ActiveEffect,
    HitPoints,
    DeathSaves,
    Speed,
    Senses,
    Background,
    Species,
    ClassLevel,
    BuildMethod,
)

__all__ = [
    "CharacterSheet",
    "AbilityScores",
    "AbilityName",
    "Size",
    "Skill",
    "Item",
    "SpellSlots",
    "ActiveEffect",
    "HitPoints",
    "DeathSaves",
    "Speed",
    "Senses",
    "Background",
    "Species",
    "ClassLevel",
    "BuildMethod",
]
