"""碰撞检测 — 生物能否占据某格，友军穿越规则"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .utils import get_cell, get_creatures_at, is_traversable, is_valid_position

if TYPE_CHECKING:
    from .models import MapCreature


def can_occupy_cell(
    creature: MapCreature,
    row: int,
    col: int,
    map_creatures: list[MapCreature],
) -> tuple[bool, str]:
    """
    Check if *creature* can stand on (row, col).

    Rules (D&D 5e simplified):
    - Must be within map bounds
    - Terrain must be traversable (not wall)
    - No other creature may occupy the same cell
      (ally pass-through is not enforced at the grid level; that would
       require path validation which is handled in movement.py)

    Returns (ok, error_message).
    """
    cells = getattr(creature, "_cells_ref", None)  # injected externally when needed
    # Bounds are validated by the caller who has cells; skip here if not injected.

    occupants = [c for c in map_creatures if c.y == row and c.x == col
                 and c.instance_id != creature.instance_id]
    if occupants:
        names = ", ".join(c.name for c in occupants)
        return False, f"该位置已被 {names} 占据"

    return True, ""


def can_occupy_cell_with_map(
    creature: MapCreature,
    row: int,
    col: int,
    cells: list[list[dict]],
    map_creatures: list[MapCreature],
) -> tuple[bool, str]:
    """Full version that also checks bounds and terrain."""
    if not is_valid_position(cells, row, col):
        return False, "目标位置超出地图范围"

    cell = get_cell(cells, row, col)
    if cell and not is_traversable(cell):
        terrain = cell.get("terrain", "open")
        return False, f"无法进入 {terrain} 地形"

    return can_occupy_cell(creature, row, col, map_creatures)
