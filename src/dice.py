"""
骰子解析与掷骰模块

支持的语法:
  1d20          → 掷 1 个 d20
  2d6+3         → 掷 2d6 加固定值 3
  4d6k3         → 掷 4d6 保留最高 3 个（属性值生成）
  4d6kl3        → 掷 4d6 保留最低 3 个
  1d20adv       → 优势（掷两次取高）
  1d20dis       → 劣势（掷两次取低）
  d20           → 等同 1d20

返回 DiceResult:
  .total        → 最终合计值
  .rolls        → 每颗骰子的点数（未经 keep/drop 过滤）
  .kept         → 实际纳入合计的骰子点数
  .modifier     → 固定加值
  .expression   → 规整化后的表达式字符串
  .breakdown    → 便于显示的字符串，如 "[3, 5, 6](k3=14)+2=16"
"""

from __future__ import annotations

import re
import random
from dataclasses import dataclass, field


@dataclass
class DiceResult:
    total: int
    rolls: list[int]          # 所有骰子点数
    kept: list[int]            # 纳入合计的点数（keep/adv/dis 过滤后）
    modifier: int              # 固定加减值
    expression: str            # 规整化表达式
    breakdown: str             # 可读拆分字符串


# ================================================================
#  解析
# ================================================================

_DICE_RE = re.compile(
    r"""
    ^
    (?P<count>\d*)          # 骰子数量，缺省=1
    d(?P<sides>\d+)         # d<面数>
    (?:
      k(?P<keep_mode>l?)    # k = keep high, kl = keep low
      (?P<keep_n>\d+)       # 保留数量
    )?
    (?P<adv>adv|dis)?       # 优势/劣势
    (?P<mod>[+-]\d+)?       # 固定加值
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


class DiceError(ValueError):
    """无效骰子表达式"""


def parse_and_roll(expression: str, rng: random.Random | None = None) -> DiceResult:
    """
    解析并掷骰。
    expression: 骰子表达式字符串，例如 "2d6+3"、"4d6k3"、"1d20adv"
    rng: 可注入的 Random 实例（测试用）
    """
    rng = rng or random.SystemRandom()
    expr = expression.strip().lower().replace(" ", "")

    m = _DICE_RE.match(expr)
    if not m:
        raise DiceError(f"无法解析骰子表达式: {expression!r}")

    count = int(m.group("count") or 1)
    sides = int(m.group("sides"))
    keep_mode = m.group("keep_mode")   # "" = keep high, "l" = keep low, None = no keep
    keep_n = int(m.group("keep_n")) if m.group("keep_n") else None
    adv = (m.group("adv") or "").lower()          # "adv" | "dis" | ""
    modifier = int(m.group("mod") or 0)

    if sides < 2:
        raise DiceError(f"骰子面数至少为 2，收到: {sides}")
    if count < 1:
        raise DiceError(f"骰子数量至少为 1，收到: {count}")
    if count > 100:
        raise DiceError(f"骰子数量不能超过 100，收到: {count}")

    # --- 优势/劣势 ---
    if adv in ("adv", "dis"):
        r1 = rng.randint(1, sides)
        r2 = rng.randint(1, sides)
        rolls = [r1, r2]
        kept = [max(r1, r2)] if adv == "adv" else [min(r1, r2)]
        norm_expr = f"1d{sides}{adv}"
        if modifier:
            norm_expr += f"{modifier:+d}"
        total = kept[0] + modifier
        bd = _fmt_adv(rolls, kept[0], adv, modifier, total)
        return DiceResult(total, rolls, kept, modifier, norm_expr, bd)

    # --- 普通掷骰 ---
    rolls = [rng.randint(1, sides) for _ in range(count)]

    # keep 逻辑
    if keep_n is not None:
        if keep_n < 1 or keep_n > count:
            raise DiceError(
                f"keep 数量 {keep_n} 超出骰子数量范围 [1, {count}]"
            )
        sorted_rolls = sorted(rolls, reverse=(keep_mode == ""))  # "" = high
        kept = sorted_rolls[:keep_n]
        norm_expr = f"{count}d{sides}k{'l' if keep_mode == 'l' else ''}{keep_n}"
    else:
        kept = rolls[:]
        norm_expr = f"{count}d{sides}"

    if modifier:
        norm_expr += f"{modifier:+d}"

    total = sum(kept) + modifier
    bd = _fmt_normal(rolls, kept, modifier, total)
    return DiceResult(total, rolls, kept, modifier, norm_expr, bd)


# ----------------------------------------------------------------
#  格式化工具
# ----------------------------------------------------------------

def _fmt_normal(rolls: list[int], kept: list[int], mod: int, total: int) -> str:
    rolls_str = ", ".join(str(r) for r in rolls)
    if rolls == kept:
        s = f"[{rolls_str}]"
    else:
        kept_str = ", ".join(str(r) for r in kept)
        s = f"[{rolls_str}]→保留[{kept_str}]"
    if mod:
        s += f"{mod:+d}"
    s += f" = {total}"
    return s


def _fmt_adv(rolls: list[int], chosen: int, mode: str, mod: int, total: int) -> str:
    tag = "优势" if mode == "adv" else "劣势"
    s = f"[{rolls[0]}, {rolls[1]}]{tag}→{chosen}"
    if mod:
        s += f"{mod:+d}"
    s += f" = {total}"
    return s


# ================================================================
#  批量掷骰（快捷方式）
# ================================================================

def roll(expression: str) -> DiceResult:
    """快捷函数，等同 parse_and_roll(expression)"""
    return parse_and_roll(expression)


def roll_ability_scores() -> list[int]:
    """
    标准属性值生成：每项 4d6 取最高 3，共 6 项
    返回未排序的 6 个属性值
    """
    scores = []
    for _ in range(6):
        r = parse_and_roll("4d6k3")
        scores.append(r.total)
    return scores
