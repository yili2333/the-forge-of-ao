"""
移动验证与移动范围计算

validate_move()        — 验证单次移动是否合法，返回移动力消耗
calculate_movement_range() — BFS 计算可达格子列表（供 movement-range 端点使用）
get_creature_speed()   — 读取生物当前有效速度
"""
from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING

from .collision import can_occupy_cell, can_occupy_cell_with_map
from .utils import get_cell, is_valid_position, movement_cost_for_cell

if TYPE_CHECKING:
    from .models import MapCreature


# ----------------------------------------------------------------
# 速度读取
# ----------------------------------------------------------------

async def get_creature_speed(creature: MapCreature) -> int:
    """
    Return effective walking speed (ft) for the creature.
    - Player character: read from CharacterSheet (includes effects).
    - Monster: use MapCreature.speed (set from monster data at simulate time).
    - Fallback: 30 ft.
    """
    if creature.character_id:
        try:
            from character.storage import get_character
            from character.calculator import compute_derived_stats
            sheet = await get_character(creature.character_id)
            if sheet:
                return compute_derived_stats(sheet).get("speed_effective", 30)
        except Exception:
            pass
    return creature.speed if creature.speed else 30


# ----------------------------------------------------------------
# 单次移动验证
# ----------------------------------------------------------------

def validate_move(
    creature: MapCreature,
    new_x: int,
    new_y: int,
    cells: list[list[dict]],
    map_creatures: list[MapCreature],
    max_movement: int,
    movement_already_used: int,
) -> tuple[bool, str, int]:
    """
    Validate moving *creature* to (new_x, new_y).

    Returns (valid, error_message, cost_ft).
    cost_ft is the movement consumed by this step (0 if invalid).
    """
    # Bounds + terrain + creature collision
    # If no floor plan has been generated yet, skip terrain/bounds and only check creature overlap
    if cells:
        ok, err = can_occupy_cell_with_map(creature, new_y, new_x, cells, map_creatures)
    else:
        ok, err = can_occupy_cell(creature, new_y, new_x, map_creatures)
    if not ok:
        return False, err, 0

    # Movement cost: Chebyshev distance (diagonal = 1 cell = 5 ft D&D rule)
    dx = abs(new_x - creature.x)
    dy = abs(new_y - creature.y)
    cells_moved = max(dx, dy)  # Chebyshev distance

    target_cell = get_cell(cells, new_y, new_x) if cells else None
    cost_per_cell = (10 if target_cell and target_cell.get("terrain") == "difficult" else 5)

    # Elevation gain: each 5ft of ascent costs an extra 5ft (climbing penalty)
    from_cell = get_cell(cells, creature.y, creature.x) if cells else None
    elev_from = from_cell.get("elevation", 0) if from_cell else 0
    elev_to   = target_cell.get("elevation", 0) if target_cell else 0
    elev_cost = max(0, elev_to - elev_from)

    cost = cells_moved * cost_per_cell + elev_cost

    if movement_already_used + cost > max_movement:
        remaining = max_movement - movement_already_used
        return False, f"移动力不足（需要 {cost} 尺，剩余 {remaining} 尺）", 0

    return True, "", cost


# ----------------------------------------------------------------
# BFS 可达范围
# ----------------------------------------------------------------

def calculate_movement_range(
    cells: list[list[dict]],
    creatures: list[MapCreature],
    start_row: int,
    start_col: int,
    max_movement: int,
    exclude_instance_id: str | None = None,
) -> list[dict]:
    """
    BFS from (start_row, start_col) up to max_movement feet.

    Returns list of {row, col, cost, terrain} dicts.
    Diagonal movement allowed (Chebyshev, each diagonal = 5 ft base cost).
    """
    if not cells:
        return []

    rows = len(cells)
    cols = len(cells[0]) if rows else 0

    reachable: list[dict] = []
    # visited maps (row, col) → min cost seen
    visited: dict[tuple[int, int], int] = {(start_row, start_col): 0}
    queue: deque[tuple[int, int, int]] = deque([(start_row, start_col, 0)])

    directions = [(-1, -1), (-1, 0), (-1, 1),
                  (0, -1),           (0, 1),
                  (1, -1),  (1, 0),  (1, 1)]

    other_creatures = [c for c in creatures
                       if not exclude_instance_id or c.instance_id != exclude_instance_id]

    while queue:
        row, col, cost_so_far = queue.popleft()

        for dr, dc in directions:
            nr, nc = row + dr, col + dc

            if not (0 <= nr < rows and 0 <= nc < cols):
                continue

            cell = cells[nr][nc]
            if cell.get("terrain", "open") == "wall":
                continue

            # creature collision
            if any(c.y == nr and c.x == nc for c in other_creatures):
                continue

            step_cost = movement_cost_for_cell(cell)
            # Elevation gain penalty
            from_c = cells[row][col]
            elev_gain = max(0, cell.get("elevation", 0) - from_c.get("elevation", 0))
            new_cost = cost_so_far + step_cost + elev_gain

            if new_cost > max_movement:
                continue

            if (nr, nc) in visited and visited[(nr, nc)] <= new_cost:
                continue

            visited[(nr, nc)] = new_cost
            queue.append((nr, nc, new_cost))
            reachable.append({
                "row": nr,
                "col": nc,
                "cost": new_cost,
                "terrain": cell.get("terrain", "open"),
            })

    # deduplicate — keep lowest cost entry per cell
    seen: dict[tuple[int, int], dict] = {}
    for entry in reachable:
        key = (entry["row"], entry["col"])
        if key not in seen or entry["cost"] < seen[key]["cost"]:
            seen[key] = entry
    return list(seen.values())
