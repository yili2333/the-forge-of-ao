"""
A* 寻路

find_path() — 在遭遇战地图上找从起点到终点的最优路径（考虑地形消耗和生物碰撞）。
返回格子列表（不含起点，含终点），或 None（无法到达）。
"""
from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from .utils import get_cell, is_valid_position, movement_cost_for_cell

if TYPE_CHECKING:
    from .models import MapCreature


def find_path(
    cells: list[list[dict]],
    creatures: list[MapCreature],
    start_row: int,
    start_col: int,
    goal_row: int,
    goal_col: int,
    exclude_instance_id: str | None = None,
) -> list[dict] | None:
    """
    A* pathfinding on the encounter map.

    Parameters
    ----------
    cells               : terrain grid (cells[row][col])
    creatures           : all MapCreature instances on the map
    start_row/col       : origin cell (usually the mover's current position)
    goal_row/col        : destination cell
    exclude_instance_id : instance_id of the mover (ignored in creature collision)

    Returns
    -------
    List of {"row": int, "col": int, "cost": int} from start (exclusive) to goal
    (inclusive), ordered by travel order.  Returns None if unreachable.
    """
    if not cells:
        return None

    rows = len(cells)
    cols = len(cells[0]) if rows else 0

    if not (is_valid_position(cells, start_row, start_col) and
            is_valid_position(cells, goal_row, goal_col)):
        return None

    # Goal must be traversable (wall cannot be the destination)
    goal_cell = get_cell(cells, goal_row, goal_col)
    if goal_cell and goal_cell.get("terrain", "open") == "wall":
        return None

    other_creatures = [
        c for c in creatures
        if not exclude_instance_id or c.instance_id != exclude_instance_id
    ]

    def _heuristic(r: int, c: int) -> int:
        # Chebyshev distance * 5ft — admissible heuristic for this movement model
        return max(abs(goal_row - r), abs(goal_col - c)) * 5

    # (f, g, row, col)
    open_heap: list[tuple[int, int, int, int]] = [
        (_heuristic(start_row, start_col), 0, start_row, start_col)
    ]
    g_score: dict[tuple[int, int], int] = {(start_row, start_col): 0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    directions = [
        (-1, -1), (-1, 0), (-1, 1),
        (0,  -1),          (0,  1),
        (1,  -1), (1,  0), (1,  1),
    ]

    while open_heap:
        _f, g, r, c = heapq.heappop(open_heap)

        if r == goal_row and c == goal_col:
            # Reconstruct path
            path: list[dict] = []
            cur: tuple[int, int] = (r, c)
            while cur in came_from:
                path.append({"row": cur[0], "col": cur[1], "cost": g_score[cur]})
                cur = came_from[cur]
            path.reverse()
            return path

        if g > g_score.get((r, c), 10**9):
            continue  # stale entry

        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            cell = cells[nr][nc]
            if cell.get("terrain", "open") == "wall":
                continue
            # Creature collision (goal cell may be occupied — allow anyway so caller
            # can decide; movement validation handles the final legality check)
            if (nr, nc) != (goal_row, goal_col):
                if any(cx.y == nr and cx.x == nc for cx in other_creatures):
                    continue

            base_cost = movement_cost_for_cell(cell)
            # Elevation gain costs extra movement (5ft per 5ft of ascent)
            from_cell = cells[r][c]
            elev_from = from_cell.get("elevation", 0) if isinstance(from_cell, dict) else 0
            elev_to   = cell.get("elevation", 0) if isinstance(cell, dict) else 0
            elev_cost = max(0, elev_to - elev_from)
            step_cost = base_cost + elev_cost

            tentative_g = g + step_cost
            if tentative_g < g_score.get((nr, nc), 10**9):
                g_score[(nr, nc)] = tentative_g
                came_from[(nr, nc)] = (r, c)
                heapq.heappush(open_heap, (tentative_g + _heuristic(nr, nc), tentative_g, nr, nc))

    return None  # no path found
