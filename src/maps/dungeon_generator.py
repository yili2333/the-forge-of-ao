"""
程序化地牢生成器

generate_dungeon() — 统一入口，返回 cells[row][col] 二维列表

支持两种风格：
  "dungeon" — BSP 二叉空间分割（方形房间 + 走廊）
  "cave"    — Cellular Automata（有机洞穴）
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# ----------------------------------------------------------------
# 公共工具
# ----------------------------------------------------------------

def _empty_grid(rows: int, cols: int, terrain: str = "wall") -> list[list[dict]]:
    return [[{"terrain": terrain, "elevation": 0, "notes": "", "is_visible": True}
             for _ in range(cols)] for _ in range(rows)]


def _set(cells, r, c, terrain):
    if 0 <= r < len(cells) and 0 <= c < len(cells[0]):
        cells[r][c]["terrain"] = terrain


# ================================================================
# BSP 地牢
# ================================================================

@dataclass
class _Rect:
    r: int; c: int; h: int; w: int

    @property
    def center(self):
        return self.r + self.h // 2, self.c + self.w // 2


@dataclass
class _Node:
    rect: _Rect
    left: "_Node | None" = None
    right: "_Node | None" = None
    room: "_Rect | None" = None


def _split(node: _Node, rng: random.Random, min_size: int = 5) -> None:
    rect = node.rect
    # Decide split axis: prefer the longer dimension
    split_h = rect.h > rect.w
    if rect.h == rect.w:
        split_h = rng.choice([True, False])

    if split_h:
        if rect.h < min_size * 2:
            return
        split_at = rng.randint(min_size, rect.h - min_size)
        node.left  = _Node(_Rect(rect.r, rect.c, split_at, rect.w))
        node.right = _Node(_Rect(rect.r + split_at, rect.c, rect.h - split_at, rect.w))
    else:
        if rect.w < min_size * 2:
            return
        split_at = rng.randint(min_size, rect.w - min_size)
        node.left  = _Node(_Rect(rect.r, rect.c, rect.h, split_at))
        node.right = _Node(_Rect(rect.r, rect.c + split_at, rect.h, rect.w - split_at))

    _split(node.left, rng, min_size)
    _split(node.right, rng, min_size)


def _carve_rooms(node: _Node, rng: random.Random) -> None:
    if node.left is None and node.right is None:
        # Leaf — carve a room inside the partition
        r_pad, c_pad = 1, 1
        max_h = node.rect.h - 2 * r_pad
        max_w = node.rect.w - 2 * c_pad
        if max_h < 3 or max_w < 3:
            return
        room_h = rng.randint(3, max(3, max_h))
        room_w = rng.randint(3, max(3, max_w))
        room_r = node.rect.r + r_pad + rng.randint(0, max_h - room_h)
        room_c = node.rect.c + c_pad + rng.randint(0, max_w - room_w)
        node.room = _Rect(room_r, room_c, room_h, room_w)
        return
    if node.left:
        _carve_rooms(node.left, rng)
    if node.right:
        _carve_rooms(node.right, rng)


def _get_rooms(node: _Node) -> list[_Rect]:
    if node.left is None and node.right is None:
        return [node.room] if node.room else []
    rooms = []
    if node.left:
        rooms += _get_rooms(node.left)
    if node.right:
        rooms += _get_rooms(node.right)
    return rooms


def _carve_corridor(cells, r1, c1, r2, c2) -> None:
    """L-shaped corridor connecting two centers."""
    r, c = r1, c1
    # Horizontal first
    step = 1 if c2 >= c else -1
    while c != c2:
        _set(cells, r, c, "open")
        c += step
    # Then vertical
    step = 1 if r2 >= r else -1
    while r != r2:
        _set(cells, r, c, "open")
        r += step
    _set(cells, r, c, "open")


def _connect_tree(node: _Node, cells) -> tuple[int, int] | None:
    """Recursively connect siblings; return a center point from this subtree."""
    if node.left is None and node.right is None:
        if node.room:
            cr, cc = node.room.center
            return cr, cc
        return None

    lc = _connect_tree(node.left, cells) if node.left else None
    rc = _connect_tree(node.right, cells) if node.right else None

    if lc and rc:
        _carve_corridor(cells, lc[0], lc[1], rc[0], rc[1])
        return lc
    return lc or rc


def _bsp_dungeon(rows: int, cols: int, room_count: int, rng: random.Random) -> list[list[dict]]:
    cells = _empty_grid(rows, cols, "wall")
    root = _Node(_Rect(0, 0, rows, cols))

    # Run splits until we have enough leaves (roughly)
    for _ in range(room_count * 2):
        _split(root, rng)

    _carve_rooms(root, rng)

    # Paint rooms onto grid
    for room in _get_rooms(root):
        for r in range(room.r, room.r + room.h):
            for c in range(room.c, room.c + room.w):
                _set(cells, r, c, "open")

    # Connect rooms via BSP tree
    _connect_tree(root, cells)

    return cells


# ================================================================
# CA 洞穴
# ================================================================

def _count_walls(cells, r, c) -> int:
    count = 0
    rows, cols = len(cells), len(cells[0])
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                count += 1  # out-of-bounds counts as wall
            elif cells[nr][nc]["terrain"] == "wall":
                count += 1
    return count


def _ca_step(cells) -> list[list[dict]]:
    rows, cols = len(cells), len(cells[0])
    new = _empty_grid(rows, cols, "wall")
    for r in range(rows):
        for c in range(cols):
            walls = _count_walls(cells, r, c)
            new[r][c]["terrain"] = "wall" if walls >= 5 else "open"
    return new


def _flood(cells, start_r, start_c) -> set[tuple[int, int]]:
    rows, cols = len(cells), len(cells[0])
    visited: set[tuple[int, int]] = set()
    stack = [(start_r, start_c)]
    while stack:
        r, c = stack.pop()
        if (r, c) in visited:
            continue
        if not (0 <= r < rows and 0 <= c < cols):
            continue
        if cells[r][c]["terrain"] == "wall":
            continue
        visited.add((r, c))
        stack += [(r-1, c), (r+1, c), (r, c-1), (r, c+1)]
    return visited


def _ca_cave(rows: int, cols: int, rng: random.Random) -> list[list[dict]]:
    # Initial random fill: ~45% walls
    cells = _empty_grid(rows, cols)
    for r in range(rows):
        for c in range(cols):
            cells[r][c]["terrain"] = "wall" if rng.random() < 0.45 else "open"

    # Border is always wall
    for r in range(rows):
        cells[r][0]["terrain"] = cells[r][cols-1]["terrain"] = "wall"
    for c in range(cols):
        cells[0][c]["terrain"] = cells[rows-1][c]["terrain"] = "wall"

    # Run 5 CA generations
    for _ in range(5):
        cells = _ca_step(cells)

    # Keep only the largest connected open region
    open_cells = [(r, c) for r in range(rows) for c in range(cols)
                  if cells[r][c]["terrain"] == "open"]
    if not open_cells:
        return cells

    regions: list[set] = []
    visited_all: set[tuple] = set()
    for pos in open_cells:
        if pos not in visited_all:
            region = _flood(cells, pos[0], pos[1])
            regions.append(region)
            visited_all |= region

    largest = max(regions, key=len)
    for r in range(rows):
        for c in range(cols):
            if cells[r][c]["terrain"] == "open" and (r, c) not in largest:
                cells[r][c]["terrain"] = "wall"

    return cells


# ================================================================
# 公开接口
# ================================================================

def generate_dungeon(
    grid_cols: int,
    grid_rows: int,
    room_count: int = 6,
    seed: int | None = None,
    style: str = "dungeon",
) -> list[list[dict]]:
    """
    Generate a 2D grid of cells[row][col].

    Parameters
    ----------
    grid_cols   : number of columns
    grid_rows   : number of rows
    room_count  : target room count (BSP only, ignored for cave)
    seed        : RNG seed for reproducibility
    style       : "dungeon" (BSP) | "cave" (cellular automata)

    Returns
    -------
    cells[row][col] — each cell is {"terrain": str, "elevation": 0, ...}
    """
    rng = random.Random(seed)
    cols, rows = max(10, grid_cols), max(10, grid_rows)

    if style == "cave":
        return _ca_cave(rows, cols, rng)
    else:
        return _bsp_dungeon(rows, cols, max(2, room_count), rng)
