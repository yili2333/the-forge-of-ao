"""
遭遇难度计算器 (D&D 5e 2024 PHB)

评级体系:
  Trivial  → 玩家几乎无风险
  Easy     → 消耗少量资源
  Medium   → 中等挑战，消耗部分资源
  Hard     → 挑战性强，可能有角色倒下
  Deadly   → 极高风险，可能导致全员团灭

计算方式（XP 预算法，PHB 2024 沿用 2014 标准）：
  1. 按全队角色等级查表，得到"每个玩家"各难度阈值 XP
  2. 将怪物 XP 值按数量乘以"遭遇倍率"（1只/2-3只/4-6只/7-10只/11-14只/15+只）
  3. 调整后怪物 XP ÷ 玩家数 对比阈值，确定难度等级

遭遇倍率表：
  1 怪物     → ×1
  2 怪物     → ×1.5
  3-6 怪物  → ×2
  7-10 怪物 → ×2.5
  11-14 怪物→ ×3
  15+ 怪物  → ×4
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .xp_system import cr_to_xp, level_from_xp


# ============================================================
#  难度 XP 阈值表（每个玩家，每个等级，4个难度档）
#  来源：PHB 2024（与2014相同）
#  格式：[easy, medium, hard, deadly]
# ============================================================

_XP_THRESHOLDS_PER_LEVEL: dict[int, tuple[int, int, int, int]] = {
    1:  (25,    50,    75,    100),
    2:  (50,    100,   150,   200),
    3:  (75,    150,   225,   400),
    4:  (125,   250,   375,   500),
    5:  (250,   500,   750,   1100),
    6:  (300,   600,   900,   1400),
    7:  (350,   750,   1100,  1700),
    8:  (450,   900,   1400,  2100),
    9:  (550,   1100,  1600,  2400),
    10: (600,   1200,  1900,  2800),
    11: (800,   1600,  2400,  3600),
    12: (1000,  2000,  3000,  4500),
    13: (1100,  2200,  3400,  5100),
    14: (1250,  2500,  3800,  5700),
    15: (1400,  2800,  4300,  6400),
    16: (1600,  3200,  4800,  7200),
    17: (2000,  3900,  5900,  8800),
    18: (2100,  4200,  6300,  9500),
    19: (2400,  4900,  7300,  10900),
    20: (2800,  5700,  8500,  12700),
}


# 遭遇倍率（根据怪物总数）
def _encounter_multiplier(monster_count: int) -> float:
    if monster_count <= 1:
        return 1.0
    elif monster_count == 2:
        return 1.5
    elif monster_count <= 6:
        return 2.0
    elif monster_count <= 10:
        return 2.5
    elif monster_count <= 14:
        return 3.0
    else:
        return 4.0


class MonsterEntry(BaseModel):
    """参与遭遇的单个怪物条目"""
    cr: str = Field(..., description="CR 字符串，如 '5'、'1/2'、'1/4'")
    count: int = Field(default=1, ge=1, description="同类怪物数量")
    name: str = ""


class EncounterDifficultyRequest(BaseModel):
    """遭遇难度评估请求"""
    party_levels: list[int] = Field(
        ...,
        description="所有玩家角色的等级列表（不同等级的玩家均填入），如 [5, 5, 4, 6]",
    )
    monsters: list[MonsterEntry] = Field(
        ...,
        description="参与遭遇的所有怪物列表",
    )


class DifficultyRating(str):
    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    DEADLY = "deadly"


class EncounterDifficultyResult(BaseModel):
    """遭遇难度评估结果"""
    rating: str                          # "trivial" / "easy" / "medium" / "hard" / "deadly"
    rating_cn: str                       # 中文难度描述
    adjusted_xp: float                   # 倍率调整后的总 XP（用于对比阈值）
    raw_monster_xp: int                  # 怪物原始 XP 总和（不含倍率）
    monster_count: int                   # 怪物总数
    encounter_multiplier: float          # 使用的遭遇倍率
    party_size: int
    party_avg_level: float
    # 阈值（全队合计）
    threshold_easy: int
    threshold_medium: int
    threshold_hard: int
    threshold_deadly: int
    # 各怪物明细
    monster_details: list[dict] = Field(default_factory=list)
    # 建议
    suggestion: str = ""


_RATING_CN = {
    "trivial": "无关痛痒",
    "easy":    "轻松",
    "medium":  "中等",
    "hard":    "困难",
    "deadly":  "致命",
}


def calculate_encounter_difficulty(
    req: EncounterDifficultyRequest,
) -> EncounterDifficultyResult:
    """
    根据队伍等级和怪物 CR 计算遭遇难度。

    返回：难度评级 + 阈值 + 调整后 XP + 倍率 + 建议。
    """
    if not req.party_levels:
        raise ValueError("party_levels 不能为空")
    if not req.monsters:
        raise ValueError("monsters 不能为空")

    party_size = len(req.party_levels)
    party_avg_level = sum(req.party_levels) / party_size

    # ---- 队伍阈值（全队合计）----
    easy_total = medium_total = hard_total = deadly_total = 0
    for lvl in req.party_levels:
        clamped = max(1, min(20, lvl))
        e, m, h, d = _XP_THRESHOLDS_PER_LEVEL[clamped]
        easy_total   += e
        medium_total += m
        hard_total   += h
        deadly_total += d

    # ---- 怪物 XP 汇总 ----
    monster_count = 0
    raw_monster_xp = 0
    monster_details: list[dict] = []

    for entry in req.monsters:
        single_xp = cr_to_xp(entry.cr)
        total_xp = single_xp * entry.count
        raw_monster_xp += total_xp
        monster_count += entry.count
        monster_details.append({
            "name": entry.name or f"CR {entry.cr} 怪物",
            "cr": entry.cr,
            "count": entry.count,
            "xp_each": single_xp,
            "xp_total": total_xp,
        })

    # ---- 遭遇倍率 ----
    # 小队（≤2人）和大队（≥6人）会额外调整倍率
    multiplier = _encounter_multiplier(monster_count)
    if party_size < 3:
        # 小队对多怪更危险：升一档
        mult_options = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
        idx = mult_options.index(multiplier)
        multiplier = mult_options[min(idx + 1, len(mult_options) - 1)]
    elif party_size >= 6:
        # 大队优势：降一档
        mult_options = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
        idx = mult_options.index(multiplier)
        multiplier = mult_options[max(idx - 1, 0)]

    adjusted_xp = raw_monster_xp * multiplier

    # ---- 评级 ----
    if adjusted_xp < easy_total:
        rating = "trivial"
    elif adjusted_xp < medium_total:
        rating = "easy"
    elif adjusted_xp < hard_total:
        rating = "medium"
    elif adjusted_xp < deadly_total:
        rating = "hard"
    else:
        rating = "deadly"

    # ---- 建议 ----
    suggestion = _build_suggestion(
        rating, adjusted_xp, easy_total, medium_total, hard_total, deadly_total
    )

    return EncounterDifficultyResult(
        rating=rating,
        rating_cn=_RATING_CN[rating],
        adjusted_xp=adjusted_xp,
        raw_monster_xp=raw_monster_xp,
        monster_count=monster_count,
        encounter_multiplier=multiplier,
        party_size=party_size,
        party_avg_level=round(party_avg_level, 1),
        threshold_easy=easy_total,
        threshold_medium=medium_total,
        threshold_hard=hard_total,
        threshold_deadly=deadly_total,
        monster_details=monster_details,
        suggestion=suggestion,
    )


def _build_suggestion(
    rating: str,
    adjusted_xp: float,
    easy: int,
    medium: int,
    hard: int,
    deadly: int,
) -> str:
    """生成难度调整建议"""
    if rating == "trivial":
        gap = easy - adjusted_xp
        return f"遭遇过于轻松。再加约 {int(gap)} 调整后 XP 的怪物可达到「轻松」难度。"
    elif rating == "easy":
        gap = medium - adjusted_xp
        return f"遭遇较轻松，预计不会有角色倒下。再加约 {int(gap)} 调整后 XP 可提升到「中等」。"
    elif rating == "medium":
        gap = hard - adjusted_xp
        return f"遭遇适中，玩家会消耗部分资源。再加约 {int(gap)} 调整后 XP 可提升到「困难」。"
    elif rating == "hard":
        gap = deadly - adjusted_xp
        return f"遭遇较危险，可能有角色倒下。若想提升到「致命」，再加约 {int(gap)} 调整后 XP。"
    else:
        over = adjusted_xp - deadly
        return f"致命遭遇！调整后 XP 超出致命阈值 {int(over)} 点，存在全灭风险。建议 DM 谨慎使用。"
