"""
D&D 5e 伤害计算引擎

支持：
- 武器伤害骰（含重击双倍骰）
- 属性修正 / 魔法加值 / 效果加值
- 目标抗性 / 免疫 / 易伤
- 法术伤害（直接传入伤害骰字符串）
"""
from __future__ import annotations

import re
import random


def _roll_dice(notation: str) -> int:
    """
    Roll a dice notation string like "2d6", "1d8+3", "2d10".
    Returns the total. Handles simple NdM[+/-K] format only.
    """
    notation = notation.strip().lower()
    total = 0

    for part in re.split(r"(?=[+-])", notation):
        part = part.strip().lstrip("+")
        if not part:
            continue
        m = re.fullmatch(r"(-?)(\d+)d(\d+)", part)
        if m:
            sign = -1 if m.group(1) == "-" else 1
            count = int(m.group(2))
            sides = int(m.group(3))
            total += sign * sum(random.randint(1, sides) for _ in range(count))
        else:
            try:
                total += int(part)
            except ValueError:
                pass

    return total


def _double_dice(notation: str) -> str:
    """Double the number of dice for a critical hit (e.g. '1d8' → '2d8')."""
    def _double_match(m: re.Match) -> str:
        count = int(m.group(1)) * 2
        sides = m.group(2)
        return f"{count}d{sides}"

    return re.sub(r"(\d+)d(\d+)", _double_match, notation)


def _apply_resistance(damage: int, *, resistant: bool, immune: bool, vulnerable: bool) -> int:
    if immune:
        return 0
    if resistant:
        damage = max(1, damage // 2)
    if vulnerable:
        damage = damage * 2
    return damage


def calculate_weapon_damage(
    damage_dice: str,
    ability_modifier: int = 0,
    magical_bonus: int = 0,
    effect_damage_bonus: str = "",
    is_critical: bool = False,
    target_damage_type: str = "",
    target_resistances: list[str] | None = None,
    target_immunities: list[str] | None = None,
    target_vulnerabilities: list[str] | None = None,
) -> dict:
    """
    Calculate weapon damage and return a result dict.

    Parameters
    ----------
    damage_dice         : base damage notation, e.g. "1d8"
    ability_modifier    : STR or DEX modifier
    magical_bonus       : +1/+2/+3 magic weapon bonus
    effect_damage_bonus : extra damage from effects, e.g. "1d6 fire" — the
                          numeric part is rolled, type may differ
    is_critical         : if True, double the dice
    target_damage_type  : primary damage type string for resistance check
    target_resistances / immunities / vulnerabilities : lists of damage type
        strings from the target (monster.damage_resistances etc.)

    Returns
    -------
    {
        "dice_rolled": str,     # notation actually rolled
        "dice_total": int,      # raw dice result
        "modifier": int,        # ability + magic bonus
        "effect_bonus": int,    # extra damage from effects
        "total_raw": int,       # sum before resistance
        "final_damage": int,    # after resistance / immunity / vulnerability
        "is_critical": bool,
        "resistant": bool,
        "immune": bool,
        "vulnerable": bool,
    }
    """
    resistances = [r.lower() for r in (target_resistances or [])]
    immunities   = [r.lower() for r in (target_immunities or [])]
    vulnerabilities = [r.lower() for r in (target_vulnerabilities or [])]
    dtype = target_damage_type.lower()

    dice_notation = _double_dice(damage_dice) if is_critical else damage_dice
    dice_total = _roll_dice(dice_notation)

    modifier = ability_modifier + magical_bonus

    # Parse effect bonus (e.g. "1d6 fire" or "2")
    effect_total = 0
    if effect_damage_bonus:
        m = re.search(r"([\d]+d[\d]+|[\d]+)", effect_damage_bonus)
        if m:
            effect_total = _roll_dice(m.group(1))

    total_raw = max(0, dice_total + modifier + effect_total)

    resistant  = dtype in resistances
    immune     = dtype in immunities
    vulnerable = dtype in vulnerabilities

    # Non-magical weapon damage against creatures with non-magical resistance
    # That logic lives at the call site (caller can set resistant=True).

    final = _apply_resistance(total_raw, resistant=resistant, immune=immune, vulnerable=vulnerable)

    return {
        "dice_rolled": dice_notation,
        "dice_total": dice_total,
        "modifier": modifier,
        "effect_bonus": effect_total,
        "total_raw": total_raw,
        "final_damage": final,
        "is_critical": is_critical,
        "resistant": resistant,
        "immune": immune,
        "vulnerable": vulnerable,
    }


def calculate_spell_damage(
    damage_dice: str,
    ability_modifier: int = 0,
    is_critical: bool = False,
    target_damage_type: str = "",
    target_resistances: list[str] | None = None,
    target_immunities: list[str] | None = None,
    target_vulnerabilities: list[str] | None = None,
) -> dict:
    """Convenience wrapper for spell damage (no magical_bonus, no effect_bonus)."""
    return calculate_weapon_damage(
        damage_dice=damage_dice,
        ability_modifier=ability_modifier,
        magical_bonus=0,
        is_critical=is_critical,
        target_damage_type=target_damage_type,
        target_resistances=target_resistances,
        target_immunities=target_immunities,
        target_vulnerabilities=target_vulnerabilities,
    )
