"""
休息机制 (Rest Engine)

实现 D&D 5e 2024 版的短休和长休规则:

短休 (Short Rest, ~1小时):
  - 花费生命骰 (roll + CON mod) 回复 HP
  - 刷新短休充能的职业资源（Ki、Action Surge 等）
  - Warlock 恢复 Pact Magic 法术位
  - 清除 UNTIL_SHORT_REST 的效果

长休 (Long Rest, ~8小时):
  - 全回 HP
  - 全回法术位
  - 刷新所有职业资源
  - 恢复 hit dice（最多回一半）
  - 死亡豁免清零
  - 耗竭等级 -1
  - 清除 UNTIL_SHORT_REST + UNTIL_LONG_REST 的效果
  - 重置战斗动作状态
"""
from __future__ import annotations

import random

from pydantic import BaseModel

from .effects_engine import tick_effects
from .models import CharacterSheet


class RestResult(BaseModel):
    """休息结果摘要（用于 API 响应）"""
    hp_gained: int = 0
    hit_dice_spent: list[str] = []          # 花费的生命骰，如 ["d8", "d8"]
    slots_recovered: dict[int, int] = {}    # {法术位等级: 回复数量}
    resources_recovered: list[str] = []     # 回复的职业资源名
    effects_expired: list[str] = []         # 过期的效果名
    exhaustion_reduced: bool = False        # 长休是否减少了耗竭


async def short_rest(
    sheet: CharacterSheet,
    hit_dice_to_spend: list[str],
    *,
    rng: random.Random | None = None,
) -> tuple[CharacterSheet, RestResult]:
    """
    短休。

    Parameters
    ----------
    sheet:
        当前角色表。
    hit_dice_to_spend:
        想花费的生命骰列表，如 ``["d8", "d8"]``。
        骰型必须与角色实际 hit_die_size 一致（前端负责过滤）。
        若剩余生命骰不足或 HP 已满则忽略多余的请求。
    rng:
        可选的随机数源，便于测试时注入固定随机数。
    """
    sheet = sheet.model_copy(deep=True)
    result = RestResult()
    rng = rng or random.Random()

    con_mod = sheet.ability_scores.modifier("constitution")
    hp = sheet.hit_points

    for die_str in hit_dice_to_spend:
        # 解析 "d8" → 8
        try:
            die_sides = int(die_str.lstrip("dD"))
        except (ValueError, AttributeError):
            continue

        if hp.hit_dice_remaining <= 0:
            break
        if hp.current >= hp.maximum:
            break

        roll = rng.randint(1, die_sides) + con_mod
        gain = max(1, roll)
        hp.current = min(hp.maximum, hp.current + gain)
        hp.hit_dice_used += 1
        result.hp_gained += gain
        result.hit_dice_spent.append(die_str)

    sheet.hit_points = hp

    # 刷新短休充能的职业资源
    for resource in sheet.class_resources:
        if resource.recharge == "short_rest" and resource.current < resource.maximum:
            result.resources_recovered.append(resource.name)
            resource.current = resource.maximum

    # Warlock: 恢复 Pact Magic 法术位（短休充能）
    warlock_level = sheet.get_class_level("Warlock")
    pact = sheet.spell_slots.pact_slots
    if warlock_level > 0 and pact.current < pact.maximum:
        result.slots_recovered[sheet.spell_slots.pact_level] = pact.maximum - pact.current
        sheet.spell_slots.pact_slots.current = pact.maximum
        if "Pact Magic" not in result.resources_recovered:
            result.resources_recovered.append("Pact Magic")

    # 过期短休效果
    sheet, expired = tick_effects(sheet, trigger="short_rest")
    result.effects_expired = [e.name for e in expired]

    return sheet, result


async def long_rest(
    sheet: CharacterSheet,
) -> tuple[CharacterSheet, RestResult]:
    """
    长休。

    规则摘要 (PHB 2024):
    - 全回 HP（至多）
    - 全回法术位
    - 刷新所有 short_rest / long_rest 充能的职业资源
    - 生命骰最多回一半总数（最少 1 个）
    - 死亡豁免清零
    - 耗竭等级 -1（若有）
    - 清除战斗动作标志
    """
    sheet = sheet.model_copy(deep=True)
    result = RestResult()

    hp = sheet.hit_points

    # 1. 全回 HP
    gained = max(0, hp.maximum - hp.current)
    result.hp_gained = gained
    hp.current = hp.maximum

    # 2. 清除死亡豁免
    hp.death_saves.reset()

    # 3. 恢复生命骰（最多回一半最大骰数，最少 1 个）
    max_recover = max(1, hp.hit_dice_total // 2)
    actual_recover = min(hp.hit_dice_used, max_recover)
    hp.hit_dice_used = max(0, hp.hit_dice_used - actual_recover)

    sheet.hit_points = hp

    # 4. 全回普通法术位
    for lvl, slot in sheet.spell_slots.slots.items():
        if slot.current < slot.maximum:
            result.slots_recovered[lvl] = slot.maximum - slot.current
            slot.current = slot.maximum

    # 5. 刷新所有长休/短休充能的职业资源
    for resource in sheet.class_resources:
        if resource.recharge in ("short_rest", "long_rest") and resource.current < resource.maximum:
            result.resources_recovered.append(resource.name)
            resource.current = resource.maximum

    # 6. 减少耗竭等级（2024: 长休减1级）
    if sheet.exhaustion_level > 0:
        sheet.exhaustion_level -= 1
        result.exhaustion_reduced = True

    # 7. 清除战斗动作状态
    sheet.action_used = False
    sheet.bonus_action_used = False
    sheet.reaction_used = False
    sheet.movement_used = 0

    # 8. 过期长休效果
    sheet, expired = tick_effects(sheet, trigger="long_rest")
    result.effects_expired = [e.name for e in expired]

    return sheet, result
