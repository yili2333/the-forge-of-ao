"""
专注检定系统

D&D 5e 规则：
- 施法者受到伤害时进行 CON 豁免
- DC = max(10, 伤害 ÷ 2)
- 失败则打断集中法术，移除对应 ActiveEffect
"""
from __future__ import annotations

import random

from .models import CharacterSheet, Condition


def _con_save_bonus(sheet: CharacterSheet) -> int:
    from .calculator import saving_throw_modifier
    from .models import AbilityName
    return saving_throw_modifier(sheet, AbilityName.CON)


def check_concentration(sheet: CharacterSheet, damage_taken: int) -> tuple[bool, int, int]:
    """
    Roll a concentration saving throw.

    Returns (success, dc, roll_total).
    """
    dc = max(10, damage_taken // 2)
    roll = random.randint(1, 20)
    bonus = _con_save_bonus(sheet)
    total = roll + bonus
    return total >= dc, dc, total


def on_damage_received(
    sheet: CharacterSheet,
    damage: int,
) -> tuple[CharacterSheet, dict | None]:
    """
    Called after a character takes damage. Handles concentration check.

    Returns (updated_sheet, event_dict | None).
    event_dict contains roll details if a check was made.
    If concentration breaks, the effect is removed from sheet.active_effects.
    """
    if not sheet.concentration_effect_id:
        return sheet, None

    # Incapacitated / unconscious → auto-fail
    auto_fail = any(c in sheet.conditions for c in
                    (Condition.INCAPACITATED, Condition.UNCONSCIOUS))

    if auto_fail:
        sheet = _break_concentration(sheet)
        return sheet, {"dc": 10, "roll": 1, "total": 1, "success": False, "auto_fail": True}

    success, dc, total = check_concentration(sheet, damage)
    raw_roll = total - bonus if (bonus := _con_save_bonus(sheet)) else total
    event = {"dc": dc, "roll": raw_roll, "total": total, "success": success}

    if not success:
        sheet = _break_concentration(sheet)

    return sheet, event


def _break_concentration(sheet: CharacterSheet) -> CharacterSheet:
    eid = sheet.concentration_effect_id
    sheet.active_effects = [e for e in sheet.active_effects if e.id != eid]
    sheet.concentration_effect_id = ""
    return sheet
