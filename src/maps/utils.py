"""地图工具函数 — 格子查询、地形判断、生物位置"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MapCreature


TRAVERSABLE_TERRAIN = {"open", "difficult", "water", "door", "cover_half", "cover_full"}
BLOCKING_TERRAIN = {"wall"}


def is_valid_position(cells: list[list[dict]], row: int, col: int) -> bool:
    if not cells:
        return False
    return 0 <= row < len(cells) and 0 <= col < len(cells[0])


def get_cell(cells: list[list[dict]], row: int, col: int) -> dict | None:
    if not is_valid_position(cells, row, col):
        return None
    return cells[row][col]


def is_traversable(cell: dict) -> bool:
    return cell.get("terrain", "open") not in BLOCKING_TERRAIN


def is_wall(cell: dict) -> bool:
    return cell.get("terrain", "open") == "wall"


def get_creatures_at(creatures: list[MapCreature], row: int, col: int) -> list[MapCreature]:
    return [c for c in creatures if c.y == row and c.x == col]


def movement_cost_for_cell(cell: dict) -> int:
    """Movement cost in feet to enter this cell (5 ft per cell, difficult = 10)."""
    terrain = cell.get("terrain", "open")
    return 10 if terrain == "difficult" else 5
