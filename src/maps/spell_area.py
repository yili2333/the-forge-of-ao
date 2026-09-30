"""
法术效果范围计算 (Spell Area of Effect)

支持 D&D 5e 四种 AoE 形状：
  sphere  — 球形/圆形（火球术 20ft 半径）
  cone    — 锥形（燃烧之手 15ft 90° 锥）
  line    — 直线（闪电链 100ft × 5ft）
  cube    — 立方体/正方形（力场立方 15ft）

函数签名：
  calculate_spell_area(
      cells, origin_row, origin_col, shape, size_ft,
      direction_row=0, direction_col=1,
      check_los=True,
  ) -> list[SpellAreaCell]

返回在范围内的格子列表，每格含：
  row, col, distance_ft, in_area, has_los, cover
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .line_of_sight import has_line_of_sight


# ================================================================
#  返回值结构
# ================================================================

@dataclass
class SpellAreaCell:
    row: int
    col: int
    distance_ft: float          # 到法术原点的距离（英尺）
    has_los: bool = True        # 原点到该格是否有视线（穿墙法术可忽略）
    cover: str = ""             # "" | "half" | "full"（取自地形）

    def as_dict(self) -> dict:
        return {
            "row":         self.row,
            "col":         self.col,
            "distance_ft": round(self.distance_ft, 1),
            "has_los":     self.has_los,
            "cover":       self.cover,
        }


# ================================================================
#  核心计算
# ================================================================

def _terrain_cover(cell: dict) -> str:
    """从格子 dict 推断掩护类型（供前端显示用，不影响是否纳入范围）"""
    t = cell.get("terrain", "open")
    if t in ("wall", "cover_full"):
        return "full"
    if t == "cover_half":
        return "half"
    return ""


def _iter_all_cells(cells: list[list[dict]]) -> list[tuple[int, int]]:
    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    return [(r, c) for r in range(rows) for c in range(cols)]


def _normalize(dr: float, dc: float) -> tuple[float, float]:
    mag = math.sqrt(dr * dr + dc * dc)
    if mag == 0:
        return 0.0, 1.0
    return dr / mag, dc / mag


# ----------------------------------------------------------------
#  sphere（球形 / 圆形）
#  cells within Euclidean distance ≤ size_ft from origin
# ----------------------------------------------------------------

def _sphere(
    cells: list[list[dict]],
    or_: int, oc: int,
    size_ft: int,
    check_los: bool,
) -> list[SpellAreaCell]:
    radius_cells = size_ft / 5.0
    result: list[SpellAreaCell] = []

    for r, c in _iter_all_cells(cells):
        dist_cells = math.sqrt((r - or_) ** 2 + (c - oc) ** 2)
        if dist_cells > radius_cells:
            continue

        dist_ft = dist_cells * 5.0
        los, _ = has_line_of_sight(cells, or_, oc, r, c) if check_los else (True, "")
        cover = _terrain_cover(cells[r][c])
        result.append(SpellAreaCell(r, c, dist_ft, los, cover))

    return result


# ----------------------------------------------------------------
#  cone（锥形）
#  D&D 5e 2024：90° 锥（半角 45°），长度 = size_ft
#  只包含原点前方扇形内且距离 ≤ size_ft 的格子
# ----------------------------------------------------------------

def _cone(
    cells: list[list[dict]],
    or_: int, oc: int,
    size_ft: int,
    dir_row: float, dir_col: float,
    check_los: bool,
) -> list[SpellAreaCell]:
    ndx, ndy = _normalize(dir_row, dir_col)   # 注意：row=y轴，col=x轴
    half_angle_cos = math.cos(math.radians(45))   # 90° 锥的半角余弦
    radius_cells = size_ft / 5.0
    result: list[SpellAreaCell] = []

    for r, c in _iter_all_cells(cells):
        if r == or_ and c == oc:
            continue   # 排除原点本身（原点格由施法者占据）

        dr, dc = r - or_, c - oc
        dist_cells = math.sqrt(dr * dr + dc * dc)
        if dist_cells > radius_cells:
            continue

        # 检查方向：格子向量与法术方向的夹角 ≤ 45°
        vx, vy = _normalize(float(dr), float(dc))
        # dir_row 对应行方向（↓为正），dir_col 对应列方向（→为正）
        dot = ndx * vx + ndy * vy
        if dot < half_angle_cos:
            continue

        dist_ft = dist_cells * 5.0
        los, _ = has_line_of_sight(cells, or_, oc, r, c) if check_los else (True, "")
        cover = _terrain_cover(cells[r][c])
        result.append(SpellAreaCell(r, c, dist_ft, los, cover))

    return result


# ----------------------------------------------------------------
#  line（直线）
#  D&D 5e：宽 5ft（1 格）× 长 size_ft
#  格子满足：
#    沿方向分量 0 < proj ≤ size_ft
#    垂直方向分量 |perp| ≤ 2.5ft（半格）
# ----------------------------------------------------------------

def _line(
    cells: list[list[dict]],
    or_: int, oc: int,
    size_ft: int,
    dir_row: float, dir_col: float,
    check_los: bool,
) -> list[SpellAreaCell]:
    ndx, ndy = _normalize(dir_row, dir_col)
    result: list[SpellAreaCell] = []

    for r, c in _iter_all_cells(cells):
        dr, dc = (r - or_) * 5.0, (c - oc) * 5.0   # 转换为英尺
        proj  =  dr * ndx + dc * ndy                  # 沿方向投影
        perp  =  dr * (-ndy) + dc * ndx               # 垂直投影

        if not (0 < proj <= size_ft):
            continue
        if abs(perp) > 2.5:
            continue

        dist_ft = math.sqrt(dr * dr + dc * dc)
        los, _ = has_line_of_sight(cells, or_, oc, r, c) if check_los else (True, "")
        cover = _terrain_cover(cells[r][c])
        result.append(SpellAreaCell(r, c, dist_ft, los, cover))

    return result


# ----------------------------------------------------------------
#  cube（立方体 / 正方形）
#  以 origin 为中心，边长 size_ft 的正方形
#  若提供方向，origin 为近边中点（即正方形从施法者向前展开）
# ----------------------------------------------------------------

def _cube(
    cells: list[list[dict]],
    or_: int, oc: int,
    size_ft: int,
    dir_row: float, dir_col: float,
    check_los: bool,
) -> list[SpellAreaCell]:
    half = size_ft / 2.0
    # 若有方向则以 origin 为近端中心，正方形向前 size_ft，两侧各延伸 half
    ndx, ndy = _normalize(dir_row, dir_col)
    result: list[SpellAreaCell] = []

    for r, c in _iter_all_cells(cells):
        dr, dc = (r - or_) * 5.0, (c - oc) * 5.0
        proj = dr * ndx + dc * ndy
        perp = dr * (-ndy) + dc * ndx

        if not (0 <= proj <= size_ft):
            continue
        if abs(perp) > half:
            continue

        dist_ft = math.sqrt(dr * dr + dc * dc)
        los, _ = has_line_of_sight(cells, or_, oc, r, c) if check_los else (True, "")
        cover = _terrain_cover(cells[r][c])
        result.append(SpellAreaCell(r, c, dist_ft, los, cover))

    return result


# ================================================================
#  公共入口
# ================================================================

VALID_SHAPES = {"sphere", "cone", "line", "cube"}


def calculate_spell_area(
    cells: list[list[dict]],
    origin_row: int,
    origin_col: int,
    shape: str,
    size_ft: int,
    direction_row: float = 0.0,
    direction_col: float = 1.0,
    check_los: bool = True,
) -> list[SpellAreaCell]:
    """
    计算法术 AoE 覆盖格子。

    Parameters
    ----------
    cells        : 遭遇战地图格子二维数组
    origin_row/col : 法术原点（通常是施法者位置或 DM 指定爆炸点）
    shape        : "sphere" | "cone" | "line" | "cube"
    size_ft      : 法术尺寸（sphere=半径, cone/line/cube=长度/边长，单位英尺）
    direction_row/col : 法术朝向向量（cone/line/cube 时有意义；sphere 忽略）
    check_los    : 是否剔除无视线格子（穿墙法术传 False）

    Returns
    -------
    list[SpellAreaCell] — 在范围内的格子列表（已去重，sphere 含原点）
    """
    if not cells:
        return []

    shape = shape.lower()
    if shape not in VALID_SHAPES:
        raise ValueError(f"未知法术形状: {shape!r}，支持: {VALID_SHAPES}")

    if shape == "sphere":
        return _sphere(cells, origin_row, origin_col, size_ft, check_los)
    if shape == "cone":
        return _cone(cells, origin_row, origin_col, size_ft,
                     direction_row, direction_col, check_los)
    if shape == "line":
        return _line(cells, origin_row, origin_col, size_ft,
                     direction_row, direction_col, check_los)
    if shape == "cube":
        return _cube(cells, origin_row, origin_col, size_ft,
                     direction_row, direction_col, check_los)
    return []   # unreachable
