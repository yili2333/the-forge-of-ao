"""
临时效果引擎

处理所有 ActiveEffect 的生命周期:
  apply_effect       - 添加效果（自动处理集中冲突）
  remove_effect      - 移除效果（清理关联状态）
  tick_effects       - 推进持续时间（按轮/短休/长休触发）
  apply_polymorph    - 变形术（保存快照，替换六维/HP/速度/AC）
  remove_polymorph   - 解除变形（从快照恢复）
  apply_wish_permanent - 许愿术（永久修改基础属性）
"""
from __future__ import annotations

from typing import Literal

from .models import (
    ActiveEffect,
    AbilityScores,
    CharacterSheet,
    Condition,
    DurationType,
    HitPoints,
    ProficiencyLevel,
    Skill,
    Speed,
)


# ============================================================
#  apply / remove / tick
# ============================================================

def apply_effect(sheet: CharacterSheet, effect: ActiveEffect) -> CharacterSheet:
    """
    将效果应用到角色。
    - 若是集中法术，先解除当前正在集中的效果
    - 添加效果到 active_effects
    - 应用 grants_conditions
    返回修改后的深复制 sheet。
    """
    sheet = sheet.model_copy(deep=True)

    if effect.concentration:
        _break_concentration(sheet)
        sheet.concentration_effect_id = effect.id

    sheet.active_effects.append(effect)

    for cond in effect.grants_conditions:
        if cond not in sheet.conditions:
            sheet.conditions.append(cond)

    return sheet


def remove_effect(sheet: CharacterSheet, effect_id: str) -> CharacterSheet:
    """
    移除指定效果，同时撤销它独有的 grants_conditions（其他效果仍在赋予的条件保留）。
    """
    sheet = sheet.model_copy(deep=True)

    target = next((e for e in sheet.active_effects if e.id == effect_id), None)
    if target is None:
        return sheet

    sheet.active_effects = [e for e in sheet.active_effects if e.id != effect_id]

    # 其余效果仍在赋予的状态集合
    still_granted: set[Condition] = set()
    for e in sheet.active_effects:
        still_granted.update(e.grants_conditions)

    sheet.conditions = [
        c for c in sheet.conditions
        if c not in target.grants_conditions or c in still_granted
    ]

    if sheet.concentration_effect_id == effect_id:
        sheet.concentration_effect_id = ""

    return sheet


def tick_effects(
    sheet: CharacterSheet,
    trigger: Literal["round", "short_rest", "long_rest"] = "round",
    rounds: int = 1,
) -> tuple[CharacterSheet, list[ActiveEffect]]:
    """
    推进效果持续时间，返回 (新 sheet, 已过期效果列表)。

    trigger:
      "round"      - 每轮战斗结束（处理 ROUNDS / UNTIL_END_OF_TURN 等）
      "short_rest" - 短休结束（处理 UNTIL_SHORT_REST）
      "long_rest"  - 长休结束（处理 UNTIL_SHORT_REST + UNTIL_LONG_REST）
    """
    sheet = sheet.model_copy(deep=True)
    expired: list[ActiveEffect] = []
    surviving: list[ActiveEffect] = []

    for effect in sheet.active_effects:
        dt = effect.duration_type

        if trigger == "round":
            if dt == DurationType.ROUNDS:
                new_val = effect.duration_value - rounds
                if new_val <= 0:
                    expired.append(effect)
                    continue
                effect = effect.model_copy(update={"duration_value": new_val})
            elif dt in (
                DurationType.UNTIL_END_OF_TURN,
                DurationType.UNTIL_START_OF_NEXT_TURN,
            ):
                expired.append(effect)
                continue
            # MINUTES / HOURS: 不按轮推进

        elif trigger == "short_rest":
            if dt == DurationType.UNTIL_SHORT_REST:
                expired.append(effect)
                continue

        elif trigger == "long_rest":
            if dt in (DurationType.UNTIL_SHORT_REST, DurationType.UNTIL_LONG_REST):
                expired.append(effect)
                continue

        surviving.append(effect)

    sheet.active_effects = surviving

    # 清理过期效果赋予的状态
    still_granted: set[Condition] = set()
    for e in sheet.active_effects:
        still_granted.update(e.grants_conditions)

    expired_conds: set[Condition] = set()
    for e in expired:
        expired_conds.update(e.grants_conditions)

    sheet.conditions = [
        c for c in sheet.conditions
        if c not in expired_conds or c in still_granted
    ]

    # 清理集中
    expired_ids = {e.id for e in expired}
    if sheet.concentration_effect_id in expired_ids:
        sheet.concentration_effect_id = ""

    return sheet, expired


# ============================================================
#  变形术 (Polymorph)
# ============================================================

def apply_polymorph(sheet: CharacterSheet, monster) -> CharacterSheet:
    """
    变形术: 用怪物数值替换六维属性/AC/HP/速度。
    保留角色意识（INT/WIS/CHA 取角色与怪物的较高值）。
    原始数据保存到 polymorph_snapshot。

    monster: monster.models.Monster 实例（运行时导入以避免循环依赖）
    """
    sheet = sheet.model_copy(deep=True)

    # 保存快照（排除 polymorph 字段本身）
    snap = sheet.model_dump()
    snap.pop("is_polymorphed", None)
    snap.pop("polymorph_snapshot", None)
    snap.pop("polymorph_monster_id", None)
    sheet.polymorph_snapshot = snap
    sheet.polymorph_monster_id = getattr(monster, "id", "") or ""
    sheet.is_polymorphed = True

    # 替换六维属性（INT/WIS/CHA 取较高值，保留角色意识）
    ma = monster.abilities
    ca = sheet.ability_scores
    sheet.ability_scores = AbilityScores(
        strength=ma.str,
        dexterity=ma.dex,
        constitution=ma.con,
        intelligence=max(ma.int_, ca.intelligence),
        wisdom=max(ma.wis, ca.wisdom),
        charisma=max(ma.cha, ca.charisma),
    )

    # 替换 HP（获得怪物 HP 池）
    # Monster 模型的 HP 字段是 .hp (int)
    hp_val = getattr(monster, "hp", None) or 1
    sheet.hit_points = HitPoints(
        current=hp_val,
        maximum=hp_val,
        hit_die_size=8,
        hit_dice_total=max(1, hp_val // 8),
    )

    # 替换速度（Monster.speed 是字符串，如 "30尺，飞行60尺（悬浮）"）
    speed_str = getattr(monster, "speed", "") or ""
    sheet.speed = _parse_monster_speed(speed_str)

    # 替换 AC（Monster 模型的 AC 字段是 .ac）
    sheet.armor_class_cache = getattr(monster, "ac", None) or 10

    return sheet


def remove_polymorph(sheet: CharacterSheet) -> CharacterSheet:
    """
    解除变形，从 polymorph_snapshot 恢复原始角色数据。
    若角色未变形则原样返回。
    """
    if not sheet.is_polymorphed or not sheet.polymorph_snapshot:
        return sheet

    restored = CharacterSheet.model_validate(sheet.polymorph_snapshot)
    restored.is_polymorphed = False
    restored.polymorph_snapshot = None
    restored.polymorph_monster_id = ""
    return restored


# ============================================================
#  许愿术 (Wish) 永久变化
# ============================================================

def apply_wish_permanent(sheet: CharacterSheet, changes: dict) -> CharacterSheet:
    """
    许愿术: 永久修改角色基础属性/语言/熟练等。
    同时添加一条 source="wish" 的 PERMANENT ActiveEffect 以便追踪。

    changes 示例::

        {
          "ability_scores": {"strength": 20, "constitution": 18},
          "languages": ["Celestial"],
          "skills": {"athletics": "expertise"},
          "weapon_proficiencies": ["longsword"]
        }
    """
    sheet = sheet.model_copy(deep=True)

    if "ability_scores" in changes:
        for attr, val in changes["ability_scores"].items():
            if hasattr(sheet.ability_scores, attr):
                setattr(sheet.ability_scores, attr, int(val))

    if "languages" in changes:
        for lang in changes["languages"]:
            if lang not in sheet.languages:
                sheet.languages.append(lang)

    if "weapon_proficiencies" in changes:
        for prof in changes["weapon_proficiencies"]:
            if prof not in sheet.weapon_proficiencies:
                sheet.weapon_proficiencies.append(prof)

    if "skills" in changes:
        for skill_name, level_str in changes["skills"].items():
            try:
                sk = Skill(skill_name)
                sheet.skills.set(sk, ProficiencyLevel(level_str))
            except ValueError:
                pass

    # 记录追踪效果
    wish_effect = ActiveEffect(
        name="许愿术 (Wish)",
        source="wish",
        description=f"永久性属性变化: {changes}",
        duration_type=DurationType.PERMANENT,
    )
    sheet.active_effects.append(wish_effect)

    return sheet


# ============================================================
#  内部工具
# ============================================================

def _parse_monster_speed(speed_str: str) -> Speed:
    """
    从 Monster.speed 字符串（如 "30尺，飞行60尺（悬浮）"）解析 Speed 对象。
    提取第一个数字作为步行速度，并识别飞行/游泳/攀爬/掘地关键词。
    """
    import re

    def _first_int(s: str) -> int:
        m = re.search(r"\d+", s)
        return int(m.group()) if m else 0

    walk = fly = swim = climb = burrow = 0
    hover = False

    # 按逗号或中文顿号分割
    parts = re.split(r"[，,、]", speed_str)
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        val = _first_int(part)
        part_lower = part.lower()
        if "飞行" in part or "fly" in part_lower:
            fly = val
            if "悬浮" in part or "hover" in part_lower:
                hover = True
        elif "游泳" in part or "swim" in part_lower:
            swim = val
        elif "攀爬" in part or "climb" in part_lower:
            climb = val
        elif "掘地" in part or "burrow" in part_lower:
            burrow = val
        elif i == 0:
            walk = val

    return Speed(walk=walk or 30, fly=fly, swim=swim, climb=climb, burrow=burrow, hover=hover)


def _break_concentration(sheet: CharacterSheet) -> None:
    """解除当前集中（in-place，不做深复制）"""
    if not sheet.concentration_effect_id:
        return
    eid = sheet.concentration_effect_id
    target = next((e for e in sheet.active_effects if e.id == eid), None)
    if target:
        sheet.active_effects = [e for e in sheet.active_effects if e.id != eid]
        still_granted: set[Condition] = set()
        for e in sheet.active_effects:
            still_granted.update(e.grants_conditions)
        sheet.conditions = [
            c for c in sheet.conditions
            if c not in target.grants_conditions or c in still_granted
        ]
    sheet.concentration_effect_id = ""
