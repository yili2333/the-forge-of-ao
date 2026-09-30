"""
D&D 5e 2024 经验值系统

PHB 2024 XP 升级阈值（与 2014 版相同）：
  Level 1  →  0 XP（起始）
  Level 2  →  300 XP
  Level 3  →  900 XP
  Level 4  →  2,700 XP
  Level 5  →  6,500 XP
  Level 6  →  14,000 XP
  Level 7  →  23,000 XP
  Level 8  →  34,000 XP
  Level 9  →  48,000 XP
  Level 10 →  64,000 XP
  Level 11 →  85,000 XP
  Level 12 →  100,000 XP
  Level 13 →  120,000 XP
  Level 14 →  140,000 XP
  Level 15 →  165,000 XP
  Level 16 →  195,000 XP
  Level 17 →  225,000 XP
  Level 18 →  265,000 XP
  Level 19 →  305,000 XP
  Level 20 →  355,000 XP

怪物 CR → XP 奖励表（PHB 2024，用于遭遇计算）：
  CR 0   → 10    CR 1/8 → 25    CR 1/4 → 50    CR 1/2 → 100
  CR 1   → 200   CR 2   → 450   CR 3   → 700   CR 4   → 1,100
  CR 5   → 1,800 CR 6   → 2,300 CR 7   → 2,900 CR 8   → 3,900
  CR 9   → 5,000 CR 10  → 5,900 CR 11  → 7,200 CR 12  → 8,400
  CR 13  → 10,000 CR 14 → 11,500 CR 15 → 13,000 CR 16 → 15,000
  CR 17  → 18,000 CR 18 → 20,000 CR 19 → 22,000 CR 20 → 25,000
  CR 21  → 33,000 CR 22 → 41,000 CR 23 → 50,000 CR 24 → 62,000
  CR 25  → 75,000 CR 26 → 90,000 CR 27 → 105,000 CR 28 → 120,000
  CR 29  → 135,000 CR 30 → 155,000
"""
from __future__ import annotations

from pydantic import BaseModel

# 升至该等级所需的累计 XP（index = level）
_XP_THRESHOLDS: list[int] = [
    0,        # L0 占位
    0,        # L1
    300,      # L2
    900,      # L3
    2_700,    # L4
    6_500,    # L5
    14_000,   # L6
    23_000,   # L7
    34_000,   # L8
    48_000,   # L9
    64_000,   # L10
    85_000,   # L11
    100_000,  # L12
    120_000,  # L13
    140_000,  # L14
    165_000,  # L15
    195_000,  # L16
    225_000,  # L17
    265_000,  # L18
    305_000,  # L19
    355_000,  # L20
]

# CR → XP 奖励
_CR_XP: dict[str, int] = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100,
    "1": 200, "2": 450, "3": 700, "4": 1_100,
    "5": 1_800, "6": 2_300, "7": 2_900, "8": 3_900,
    "9": 5_000, "10": 5_900, "11": 7_200, "12": 8_400,
    "13": 10_000, "14": 11_500, "15": 13_000, "16": 15_000,
    "17": 18_000, "18": 20_000, "19": 22_000, "20": 25_000,
    "21": 33_000, "22": 41_000, "23": 50_000, "24": 62_000,
    "25": 75_000, "26": 90_000, "27": 105_000, "28": 120_000,
    "29": 135_000, "30": 155_000,
}

MAX_LEVEL = 20


def xp_for_level(level: int) -> int:
    """返回升至该等级所需的累计 XP"""
    if level <= 1:
        return 0
    if level > MAX_LEVEL:
        return _XP_THRESHOLDS[MAX_LEVEL]
    return _XP_THRESHOLDS[level]


def level_from_xp(xp: int) -> int:
    """根据累计 XP 返回当前应有等级"""
    for lvl in range(MAX_LEVEL, 0, -1):
        if xp >= _XP_THRESHOLDS[lvl]:
            return lvl
    return 1


def xp_to_next(current_xp: int) -> int:
    """距下一级还差多少 XP（已满 20 级返回 0）"""
    current_level = level_from_xp(current_xp)
    if current_level >= MAX_LEVEL:
        return 0
    return _XP_THRESHOLDS[current_level + 1] - current_xp


def cr_to_xp(cr: str) -> int:
    """将 CR 字符串（如 '5'、'1/2'）转换为 XP 奖励，未知 CR 返回 0"""
    return _CR_XP.get(str(cr).strip(), 0)


class XpGainResult(BaseModel):
    character_id: str
    xp_gained: int
    xp_before: int
    xp_after: int
    level_before: int
    level_after: int
    leveled_up: bool
    xp_to_next: int


def apply_xp(character_id: str, current_xp: int, xp_gained: int) -> XpGainResult:
    """
    计算获得 XP 后的结果（纯计算，不触发存储）。
    升级判断：level_after > level_before。
    """
    level_before = level_from_xp(current_xp)
    xp_after = current_xp + xp_gained
    level_after = level_from_xp(xp_after)
    return XpGainResult(
        character_id=character_id,
        xp_gained=xp_gained,
        xp_before=current_xp,
        xp_after=xp_after,
        level_before=level_before,
        level_after=level_after,
        leveled_up=level_after > level_before,
        xp_to_next=xp_to_next(xp_after),
    )
