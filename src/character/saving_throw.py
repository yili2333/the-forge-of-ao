"""
豁免掷骰系统

roll_saving_throw()   — 掷一次豁免，返回结果 dict
apply_spell_save()    — 对整个目标列表执行豁免，返回成功 / 失败分组
"""
from __future__ import annotations

import random

from .calculator import saving_throw_modifier
from .models import AbilityName, CharacterSheet


_ABILITY_ALIASES: dict[str, AbilityName] = {
    "str": AbilityName.STR, "strength": AbilityName.STR,
    "dex": AbilityName.DEX, "dexterity": AbilityName.DEX,
    "con": AbilityName.CON, "constitution": AbilityName.CON,
    "int": AbilityName.INT, "intelligence": AbilityName.INT,
    "wis": AbilityName.WIS, "wisdom": AbilityName.WIS,
    "cha": AbilityName.CHA, "charisma": AbilityName.CHA,
}


def _resolve_ability(ability: str) -> AbilityName:
    key = ability.lower().strip()
    if key in _ABILITY_ALIASES:
        return _ABILITY_ALIASES[key]
    raise ValueError(f"未知属性：{ability}")


def roll_saving_throw(
    sheet: CharacterSheet,
    ability: str,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
) -> dict:
    """
    Roll a saving throw for *sheet* against *dc*.

    Returns:
    {
        "ability": "constitution",
        "dc": int,
        "roll": int,          # raw d20
        "bonus": int,
        "total": int,
        "success": bool,
        "advantage": bool,
        "disadvantage": bool,
    }
    """
    ability_name = _resolve_ability(ability)
    bonus = saving_throw_modifier(sheet, ability_name)

    if advantage and not disadvantage:
        roll = max(random.randint(1, 20), random.randint(1, 20))
    elif disadvantage and not advantage:
        roll = min(random.randint(1, 20), random.randint(1, 20))
    else:
        roll = random.randint(1, 20)

    total = roll + bonus
    return {
        "ability": ability_name.value,
        "dc": dc,
        "roll": roll,
        "bonus": bonus,
        "total": total,
        "success": total >= dc,
        "advantage": advantage,
        "disadvantage": disadvantage,
    }


def apply_spell_save(
    targets: list[CharacterSheet],
    ability: str,
    dc: int,
) -> dict:
    """
    Roll saving throws for all targets.

    Returns:
    {
        "successes": [{"id": ..., "name": ..., "result": {...}}, ...],
        "failures":  [{"id": ..., "name": ..., "result": {...}}, ...],
    }
    """
    successes = []
    failures = []
    for sheet in targets:
        result = roll_saving_throw(sheet, ability, dc)
        entry = {"id": sheet.id, "name": sheet.name, "result": result}
        (successes if result["success"] else failures).append(entry)
    return {"successes": successes, "failures": failures}
