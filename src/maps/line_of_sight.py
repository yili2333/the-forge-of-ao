"""
视线计算 (Line of Sight)

D&D 5e 简化规则：
- wall / cover_full 完全阻断视线
- cover_half 不阻断视线（提供 AC 加值，但不影响可见性）
- 使用 Bresenham 射线穿越中间格子
"""
from __future__ import annotations

import math


def has_line_of_sight(
    cells: list[list[dict]],
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> tuple[bool, str]:
    """
    Check LOS between two grid cells.

    Returns (has_los, blocking_reason).
    - (True,  "")           — clear sight
    - (False, "wall")       — blocked by wall
    - (False, "cover_full") — blocked by full cover
    """
    if not cells:
        return True, ""

    rows = len(cells)
    cols = len(cells[0])

    dx = to_col - from_col
    dy = to_row - from_row
    distance = math.sqrt(dx * dx + dy * dy)

    if distance == 0:
        return True, ""

    steps = max(abs(dx), abs(dy))

    for i in range(1, steps):
        t = i / steps
        check_col = int(round(from_col + dx * t))
        check_row = int(round(from_row + dy * t))

        if not (0 <= check_row < rows and 0 <= check_col < cols):
            continue

        terrain = cells[check_row][check_col].get("terrain", "open")
        if terrain == "wall":
            return False, "wall"
        if terrain == "cover_full":
            return False, "cover_full"

    return True, ""


def distance_ft(from_row: int, from_col: int, to_row: int, to_col: int) -> float:
    """Euclidean distance in feet (5 ft per cell)."""
    return math.sqrt((to_col - from_col) ** 2 + (to_row - from_row) ** 2) * 5
