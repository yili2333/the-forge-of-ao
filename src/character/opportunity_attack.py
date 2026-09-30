"""
机会攻击（Opportunity Attack）检测

D&D 5e 规则：
- 当敌对生物自愿移出你的威胁范围（默认 5尺 / 1格）时，你可以用**反应**进行一次近战攻击。
- 使用飞离（Disengage）动作移动、被强制移动（DM skip_validation）不触发机会攻击。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maps.models import MapCreature


def _chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(abs(x2 - x1), abs(y2 - y1))


def enemies_threatening(
    creature: MapCreature,
    all_creatures: list[MapCreature],
    reach_cells: int = 1,
) -> list[MapCreature]:
    """
    返回当前威胁 *creature* 的所有敌方生物（在 reach_cells 格范围内）。
    敌我判断：is_player 不同即视为敌对。
    """
    return [
        c for c in all_creatures
        if c.instance_id != creature.instance_id
        and c.is_player != creature.is_player
        and _chebyshev(c.x, c.y, creature.x, creature.y) <= reach_cells
    ]


def provokes_opportunity_attack(
    mover: MapCreature,
    old_x: int,
    old_y: int,
    new_x: int,
    new_y: int,
    all_creatures: list[MapCreature],
    reach_cells: int = 1,
) -> list[MapCreature]:
    """
    检测本次移动是否触发机会攻击。

    规则：移动者从威胁范围内（旧位置）离开（新位置不在范围内）→ 触发。

    返回可以进行机会攻击的敌方生物列表。
    skip_validation 移动（DM 强制传送）不经过此函数，由调用方负责过滤。
    """
    provoked: list[MapCreature] = []
    for c in all_creatures:
        if c.instance_id == mover.instance_id:
            continue
        if c.is_player == mover.is_player:
            continue  # 友方不触发
        if c.reaction_used if hasattr(c, "reaction_used") else False:
            continue  # 已用反应（怪物暂无此字段，跳过）

        was_in_reach = _chebyshev(c.x, c.y, old_x, old_y) <= reach_cells
        still_in_reach = _chebyshev(c.x, c.y, new_x, new_y) <= reach_cells

        if was_in_reach and not still_in_reach:
            provoked.append(c)

    return provoked
