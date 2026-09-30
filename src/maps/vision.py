"""
视野共享系统

规则：
- 玩家角色之间共享视野
- 任意玩家角色能看到的怪物 → 所有玩家都能看到
- is_hidden=True 的生物只有 DM 可见（伏击 / DM 手动隐藏）
- DM 始终看到所有生物
- 最大视力距离默认 120 尺（超出不可见）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .line_of_sight import has_line_of_sight, distance_ft

if TYPE_CHECKING:
    from .models import MapCreature

_MAX_SIGHT_FT = 120


def _player_can_see(
    observer: MapCreature,
    target: MapCreature,
    cells: list[list[dict]],
) -> bool:
    """True if observer has LOS to target and target is within sight range."""
    if distance_ft(observer.y, observer.x, target.y, target.x) > _MAX_SIGHT_FT:
        return False
    los, _ = has_line_of_sight(cells, observer.y, observer.x, target.y, target.x)
    return los


def get_visible_creatures_for_player(
    cells: list[list[dict]],
    all_creatures: list[MapCreature],
    player_character_ids: list[str],
) -> list[MapCreature]:
    """
    Return the subset of all_creatures visible to a player who controls
    the given character IDs.

    Visibility rules:
    1. Player always sees their own characters.
    2. If any player character has LOS to a non-hidden creature, it's visible.
    3. is_hidden=True creatures are never returned (DM-only).
    """
    player_creatures = [c for c in all_creatures if c.character_id in player_character_ids]

    visible: list[MapCreature] = []
    for creature in all_creatures:
        # Own character — always visible
        if creature.character_id in player_character_ids:
            visible.append(creature)
            continue

        # DM-hidden creatures are never visible to players
        if creature.is_hidden:
            continue

        # If cells are empty, no LOS possible — show everything non-hidden
        if not cells:
            visible.append(creature)
            continue

        # Shared vision: any observer gives sight to all players
        for observer in player_creatures:
            if _player_can_see(observer, creature, cells):
                visible.append(creature)
                break

    return visible


def filter_positions_for_player(
    creature_positions: dict[str, dict],
    all_creatures: list[MapCreature],
    cells: list[list[dict]],
    player_character_ids: list[str],
) -> dict[str, dict]:
    """
    Filter the creature_positions dict (from RoomState) to only include
    creatures visible to the given player.
    """
    visible = get_visible_creatures_for_player(cells, all_creatures, player_character_ids)
    visible_ids = {c.instance_id for c in visible}
    return {iid: pos for iid, pos in creature_positions.items() if iid in visible_ids}
