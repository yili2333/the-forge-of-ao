"""
D&D 5e 2024 多职业前置条件 (PHB 2024, p.58)

规则：
  要多职业，当前已有职业和新入职业都需满足最低属性要求。
  已有职业同样需维持原入职条件（以简化实现，只在加入新职业时校验新职业要求）。

每种职业的最低属性要求（至少一个满足即可）：
  Barbarian:    STR 13
  Bard:         CHA 13
  Cleric:       WIS 13
  Druid:        WIS 13
  Fighter:      STR 13 或 DEX 13
  Monk:         DEX 13 且 WIS 13
  Paladin:      STR 13 且 CHA 13
  Ranger:       DEX 13 且 WIS 13
  Rogue:        DEX 13
  Sorcerer:     CHA 13
  Warlock:      CHA 13
  Wizard:       INT 13
  Artificer:    INT 13
"""
from __future__ import annotations

from .models import AbilityScores

# 每个职业的前置条件
# 格式: [condition, ...]
# condition = {ability: min_score, ...}  → 所有字段都要满足（AND）
# 多个 condition 之间是 OR 关系
_MULTICLASS_PREREQS: dict[str, list[dict[str, int]]] = {
    "barbarian": [{"strength": 13}],
    "bard":      [{"charisma": 13}],
    "cleric":    [{"wisdom": 13}],
    "druid":     [{"wisdom": 13}],
    "fighter":   [{"strength": 13}, {"dexterity": 13}],   # OR
    "monk":      [{"dexterity": 13, "wisdom": 13}],        # AND
    "paladin":   [{"strength": 13, "charisma": 13}],       # AND
    "ranger":    [{"dexterity": 13, "wisdom": 13}],        # AND
    "rogue":     [{"dexterity": 13}],
    "sorcerer":  [{"charisma": 13}],
    "warlock":   [{"charisma": 13}],
    "wizard":    [{"intelligence": 13}],
    "artificer": [{"intelligence": 13}],
}


def check_multiclass_prereq(
    ability_scores: AbilityScores,
    new_class: str,
) -> tuple[bool, str]:
    """
    检查能力值是否满足新职业的多职业前置条件。

    返回 (ok, reason)：
      ok=True  → 满足条件
      ok=False → reason 描述原因
    """
    key = new_class.lower()
    conditions = _MULTICLASS_PREREQS.get(key)
    if conditions is None:
        # 未知职业：不强制校验，视为通过（可能是 homebrew）
        return True, ""

    for cond in conditions:
        # cond 内的所有条件都需满足（AND）
        if all(
            getattr(ability_scores, ability, 0) >= min_score
            for ability, min_score in cond.items()
        ):
            return True, ""   # 任意一个 OR 条件通过即满足

    # 构建失败原因描述
    or_parts = []
    for cond in conditions:
        and_parts = [f"{ab.upper()} ≥ {ms}" for ab, ms in cond.items()]
        or_parts.append(" 且 ".join(and_parts))
    reason = "多职业前置条件不满足：需要 " + "，或 ".join(or_parts)
    return False, reason


def validate_multiclass(
    ability_scores: AbilityScores,
    existing_classes: list[str],
    new_class: str,
) -> tuple[bool, str]:
    """
    完整的多职业合法性检查：
    1. 如果已有职业（非纯职业），检查 new_class 的前置条件
    2. 如果 new_class 已经存在则不算多职业（直接升级），不需校验
    """
    existing_lower = [c.lower() for c in existing_classes]

    # 同一职业再次入职不算多职业
    if new_class.lower() in existing_lower:
        return True, ""

    # 纯职业（第一个职业）不需要前置条件
    if not existing_classes:
        return True, ""

    # 多职业：检查 new_class 的前置条件
    return check_multiclass_prereq(ability_scores, new_class)
