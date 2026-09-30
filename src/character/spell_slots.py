"""
PHB 2024 法术位表

提供:
  get_spell_slots(class_name, level)          → SpellSlots
  merge_multiclass_spell_slots(class_levels)  → SpellSlots（多职业合并）

施法者类型:
  全职施法者 (Full):   Wizard / Sorcerer / Cleric / Druid / Bard
  半职施法者 (Half):   Paladin / Ranger
  1/3 施法者 (Third):  Eldritch Knight (Fighter 子职) / Arcane Trickster (Rogue 子职)
  Warlock:             独立 Pact Magic（短休充能）
"""
from __future__ import annotations

from .models import SpellSlot, SpellSlots

# ============================================================
#  法术位表（等级 → {slot_level: count}）
# ============================================================

# Full caster: Wizard / Sorcerer / Cleric / Druid / Bard
_FULL: dict[int, dict[int, int]] = {
    1:  {1: 2},
    2:  {1: 3},
    3:  {1: 4, 2: 2},
    4:  {1: 4, 2: 3},
    5:  {1: 4, 2: 3, 3: 2},
    6:  {1: 4, 2: 3, 3: 3},
    7:  {1: 4, 2: 3, 3: 3, 4: 1},
    8:  {1: 4, 2: 3, 3: 3, 4: 2},
    9:  {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 1, 7: 1, 8: 1, 9: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1},
}

# Half caster: Paladin / Ranger
_HALF: dict[int, dict[int, int]] = {
    1:  {},
    2:  {1: 2},
    3:  {1: 3},
    4:  {1: 3},
    5:  {1: 4, 2: 2},
    6:  {1: 4, 2: 2},
    7:  {1: 4, 2: 3},
    8:  {1: 4, 2: 3},
    9:  {1: 4, 2: 3, 3: 2},
    10: {1: 4, 2: 3, 3: 2},
    11: {1: 4, 2: 3, 3: 3},
    12: {1: 4, 2: 3, 3: 3},
    13: {1: 4, 2: 3, 3: 3, 4: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 2},
    16: {1: 4, 2: 3, 3: 3, 4: 2},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
}

# 1/3 caster: Eldritch Knight / Arcane Trickster
_THIRD: dict[int, dict[int, int]] = {
    1:  {},
    2:  {},
    3:  {1: 2},
    4:  {1: 3},
    5:  {1: 3},
    6:  {1: 3},
    7:  {1: 4, 2: 2},
    8:  {1: 4, 2: 2},
    9:  {1: 4, 2: 2},
    10: {1: 4, 2: 3},
    11: {1: 4, 2: 3},
    12: {1: 4, 2: 3},
    13: {1: 4, 2: 3, 3: 2},
    14: {1: 4, 2: 3, 3: 2},
    15: {1: 4, 2: 3, 3: 2},
    16: {1: 4, 2: 3, 3: 3},
    17: {1: 4, 2: 3, 3: 3},
    18: {1: 4, 2: 3, 3: 3},
    19: {1: 4, 2: 3, 3: 3, 4: 1},
    20: {1: 4, 2: 3, 3: 3, 4: 1},
}

# Warlock Pact Magic: level → (slot_level, num_slots)
_WARLOCK_PACT: dict[int, tuple[int, int]] = {
    1:  (1, 1),
    2:  (1, 2),
    3:  (2, 2),
    4:  (2, 2),
    5:  (3, 2),
    6:  (3, 2),
    7:  (4, 2),
    8:  (4, 2),
    9:  (5, 2),
    10: (5, 2),
    11: (5, 3),
    12: (5, 3),
    13: (5, 3),
    14: (5, 3),
    15: (5, 3),
    16: (5, 3),
    17: (5, 4),
    18: (5, 4),
    19: (5, 4),
    20: (5, 4),
}

# 职业 → 施法者类型（小写）
_FULL_CASTER_CLASSES  = frozenset({"wizard", "sorcerer", "cleric", "druid", "bard"})
_HALF_CASTER_CLASSES  = frozenset({"paladin", "ranger"})
_THIRD_CASTER_CLASSES = frozenset({"eldritch knight", "arcane trickster"})


# ============================================================
#  公开 API
# ============================================================

def get_spell_slots(class_name: str, level: int) -> SpellSlots:
    """
    返回给定职业等级对应的法术位配置（完整施放，非多职业合并）。
    level 自动限制在 [1, 20]。
    """
    level = max(1, min(20, level))
    name = class_name.lower()

    if name == "warlock":
        pact_level, pact_count = _WARLOCK_PACT.get(level, (0, 0))
        return SpellSlots(
            pact_level=pact_level,
            pact_slots=SpellSlot(maximum=pact_count, current=pact_count),
        )

    if name in _FULL_CASTER_CLASSES:
        table = _FULL
    elif name in _HALF_CASTER_CLASSES:
        table = _HALF
    elif name in _THIRD_CASTER_CLASSES:
        table = _THIRD
    else:
        return SpellSlots()

    slot_dict = table.get(level, {})
    return SpellSlots(
        slots={
            lvl: SpellSlot(maximum=count, current=count)
            for lvl, count in slot_dict.items()
        }
    )


def merge_multiclass_spell_slots(
    class_levels: list[tuple[str, int]],
) -> SpellSlots:
    """
    多职业施法者法术位合并（PHB 2024）。

    Parameters
    ----------
    class_levels:
        ``[(class_name, level), ...]`` 格式的职业列表。

    规则:
    - 全职施法者贡献完整等级
    - 半职施法者贡献 level // 2
    - 1/3 施法者贡献 level // 3
    - Warlock 独立，不参与合并
    """
    caster_level = 0
    warlock_level = 0

    for class_name, level in class_levels:
        name = class_name.lower()
        if name == "warlock":
            warlock_level = level
        elif name in _FULL_CASTER_CLASSES:
            caster_level += level
        elif name in _HALF_CASTER_CLASSES:
            caster_level += level // 2
        elif name in _THIRD_CASTER_CLASSES:
            caster_level += level // 3

    caster_level = min(20, caster_level)

    if caster_level == 0 and warlock_level == 0:
        return SpellSlots()

    merged = SpellSlots()

    if caster_level > 0:
        slot_dict = _FULL.get(caster_level, {})
        merged.slots = {
            lvl: SpellSlot(maximum=count, current=count)
            for lvl, count in slot_dict.items()
        }

    if warlock_level > 0:
        pact_level, pact_count = _WARLOCK_PACT.get(warlock_level, (0, 0))
        merged.pact_level = pact_level
        merged.pact_slots = SpellSlot(maximum=pact_count, current=pact_count)

    return merged
