"""
地图系统 FastAPI 路由

世界地图:    /api/campaign/{id}/world-map/*
遭遇战地图:  /api/campaign/{id}/encounter-maps/*
"""
from __future__ import annotations

import random
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import MAPS_DIR, image_path_to_url
from .dungeon_generator import generate_dungeon
from .generator import generate_encounter_bg, generate_region_map, generate_world_map
from .models import (
    EncounterMap, EncounterMapSummary, MapCreature, MapPosition,
    PointOfInterest, RegionMap, RegionMapSummary, RegionType,
    WorldMap, WorldMapSummary,
    encounter_map_to_summary, region_map_to_summary, world_map_to_summary,
    REGION_PROMPT_PRESETS,
)
from .storage import (
    delete_encounter_map, delete_region_map, delete_world_map,
    get_campaign_world_map, get_encounter_map, get_region_map, get_world_map,
    list_encounter_maps, list_region_maps,
    save_encounter_map, save_region_map, save_world_map,
)

router = APIRouter(prefix="/api/campaign", tags=["maps"])

UPLOAD_DIR = MAPS_DIR


def _require_dm(x_role: str | None) -> None:
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="此操作需要 DM 权限")


# ============================================================
#  世界地图
# ============================================================

@router.get("/{campaign_id}/world-map", response_model=WorldMap)
async def get_world_map_endpoint(campaign_id: str):
    """获取战役的世界地图"""
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="此战役尚未创建世界地图")
    return m


class GenerateMapRequest(BaseModel):
    prompt: str = Field(..., description="AI 生成提示词，如 '中世纪奇幻大陆，含森林、山脉、海岸'")
    width_px: int = 1024
    height_px: int = 1024


@router.post("/{campaign_id}/world-map/generate", response_model=WorldMap)
async def generate_world_map_endpoint(
    campaign_id: str,
    req: GenerateMapRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 用 AI 生成世界地图图片"""
    _require_dm(x_role)
    existing = await get_campaign_world_map(campaign_id)
    if existing is None:
        existing = WorldMap(campaign_id=campaign_id, name="World Map", image_prompt=req.prompt)

    image_path = await generate_world_map(req.prompt, req.width_px, req.height_px)
    existing.image_url = image_path
    existing.image_prompt = req.prompt
    return await save_world_map(existing)


@router.put("/{campaign_id}/world-map/prompt", response_model=WorldMap)
async def update_world_map_prompt(
    campaign_id: str,
    req: GenerateMapRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 更新世界地图生成提示词（不立即重新生成）"""
    _require_dm(x_role)
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="此战役尚未创建世界地图")
    m.image_prompt = req.prompt
    return await save_world_map(m)


@router.post("/{campaign_id}/world-map/upload", response_model=WorldMap)
async def upload_world_map(
    campaign_id: str,
    file: UploadFile = File(...),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 手动上传世界地图图片"""
    _require_dm(x_role)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"world_{campaign_id}_{file.filename}"
    dest = UPLOAD_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    m = await get_campaign_world_map(campaign_id)
    if m is None:
        m = WorldMap(campaign_id=campaign_id, name="World Map")
    m.image_url = image_path_to_url(str(dest))
    return await save_world_map(m)


# ---- POI 管理 ----

@router.post("/{campaign_id}/world-map/poi", response_model=WorldMap)
async def add_poi(
    campaign_id: str,
    poi: PointOfInterest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 添加地图兴趣点"""
    _require_dm(x_role)
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="此战役尚未创建世界地图")
    m.pois.append(poi)
    return await save_world_map(m)


@router.put("/{campaign_id}/world-map/poi/{poi_id}", response_model=WorldMap)
async def update_poi(
    campaign_id: str,
    poi_id: str,
    poi: PointOfInterest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="世界地图不存在")
    for i, p in enumerate(m.pois):
        if p.id == poi_id:
            poi.id = poi_id
            m.pois[i] = poi
            return await save_world_map(m)
    raise HTTPException(status_code=404, detail=f"POI {poi_id} 不存在")


@router.delete("/{campaign_id}/world-map/poi/{poi_id}", response_model=WorldMap)
async def delete_poi(
    campaign_id: str,
    poi_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="世界地图不存在")
    m.pois = [p for p in m.pois if p.id != poi_id]
    return await save_world_map(m)


class ProgressUpdate(BaseModel):
    owner_id: str
    position: MapPosition | None = None
    visited_poi_id: str | None = None


@router.patch("/{campaign_id}/world-map/progress", response_model=WorldMap)
async def update_player_progress(
    campaign_id: str,
    req: ProgressUpdate,
):
    """更新玩家的世界地图进度（位置/已访问地点）"""
    m = await get_campaign_world_map(campaign_id)
    if m is None:
        raise HTTPException(status_code=404, detail="世界地图不存在")
    if req.position is not None:
        m.player_positions[req.owner_id] = req.position.model_dump()
    if req.visited_poi_id:
        visited = m.visited_locations.setdefault(req.owner_id, [])
        if req.visited_poi_id not in visited:
            visited.append(req.visited_poi_id)
    return await save_world_map(m)


# ============================================================
#  遭遇战地图
# ============================================================

@router.post("/{campaign_id}/encounter-maps", response_model=EncounterMap)
async def create_encounter_map(
    campaign_id: str,
    m: EncounterMap,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 新建遭遇战棋盘"""
    _require_dm(x_role)
    m.campaign_id = campaign_id
    return await save_encounter_map(m)


@router.get("/{campaign_id}/encounter-maps", response_model=list[EncounterMapSummary])
async def list_encounter_maps_endpoint(campaign_id: str):
    maps = await list_encounter_maps(campaign_id)
    return [encounter_map_to_summary(m) for m in maps]


@router.get("/{campaign_id}/encounter-maps/{map_id}", response_model=EncounterMap)
async def get_encounter_map_endpoint(campaign_id: str, map_id: str):
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")
    return m


@router.put("/{campaign_id}/encounter-maps/{map_id}", response_model=EncounterMap)
async def update_encounter_map(
    campaign_id: str,
    map_id: str,
    m: EncounterMap,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    existing = await get_encounter_map(map_id)
    if existing is None or existing.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")
    m.id = map_id
    m.campaign_id = campaign_id
    m.created_at = existing.created_at
    return await save_encounter_map(m)


@router.delete("/{campaign_id}/encounter-maps/{map_id}")
async def delete_encounter_map_endpoint(
    campaign_id: str,
    map_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    ok = await delete_encounter_map(map_id)
    if not ok:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")
    return {"success": True}


class GenerateBgRequest(BaseModel):
    prompt: str = Field(..., description="背景图提示词，如 '幽暗的地牢，石砖地板，壁炬光芒'")
    cell_px: int = 48


@router.post("/{campaign_id}/encounter-maps/{map_id}/generate-bg", response_model=EncounterMap)
async def generate_encounter_bg_endpoint(
    campaign_id: str,
    map_id: str,
    req: GenerateBgRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")
    image_path = await generate_encounter_bg(req.prompt, m.grid_cols, m.grid_rows, req.cell_px)
    m.image_url = image_path
    m.image_prompt = req.prompt
    return await save_encounter_map(m)



class CreaturePatch(BaseModel):
    instance_id: str
    x: int | None = None
    y: int | None = None
    hp_current: int | None = None
    conditions: list[str] | None = None
    is_hidden: bool | None = None
    skip_validation: bool = False    # DM 强制移动，跳过规则校验


@router.patch("/{campaign_id}/encounter-maps/{map_id}/creatures", response_model=EncounterMap)
async def patch_creature(
    campaign_id: str,
    map_id: str,
    patch: CreaturePatch,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 移动/更新棋盘上的生物（含移动力验证）"""
    _require_dm(x_role)
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    creature = next((c for c in m.creatures if c.instance_id == patch.instance_id), None)
    if creature is None:
        raise HTTPException(status_code=404, detail=f"生物实例 {patch.instance_id} 不存在")

    # 记录移动前坐标，用于机会攻击检测
    _old_x, _old_y = creature.x, creature.y

    # ---- 移动验证 ----
    if (patch.x is not None or patch.y is not None) and not patch.skip_validation:
        from .movement import validate_move, get_creature_speed
        from character.storage import get_character, save_character

        new_x = patch.x if patch.x is not None else creature.x
        new_y = patch.y if patch.y is not None else creature.y

        max_spd = await get_creature_speed(creature)

        # 玩家角色：从 CharacterSheet 读取已用移动力
        if creature.character_id:
            sheet = await get_character(creature.character_id)
            movement_already_used = sheet.movement_used if sheet else 0
        else:
            movement_already_used = creature.movement_used

        ok, err, cost = validate_move(
            creature, new_x, new_y, m.cells, m.creatures,
            max_spd, movement_already_used,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err)

        # 扣除移动力
        if creature.character_id:
            if sheet:
                sheet.movement_used += cost
                await save_character(sheet)
        else:
            creature.movement_used += cost

    position_changed = (patch.x is not None and patch.x != _old_x) or \
                       (patch.y is not None and patch.y != _old_y)

    if patch.x is not None:
        creature.x = patch.x
    if patch.y is not None:
        creature.y = patch.y
    if patch.hp_current is not None:
        creature.hp_current = max(0, patch.hp_current)
    if patch.conditions is not None:
        creature.conditions = patch.conditions
    if patch.is_hidden is not None:
        creature.is_hidden = patch.is_hidden

    saved = await save_encounter_map(m)

    # ---- 机会攻击检测（自愿移动 + 战斗中才触发）----
    if position_changed and not patch.skip_validation:
        try:
            from character.opportunity_attack import provokes_opportunity_attack
            new_x = patch.x if patch.x is not None else _old_x
            new_y = patch.y if patch.y is not None else _old_y
            provoked = provokes_opportunity_attack(
                creature, _old_x, _old_y, new_x, new_y, m.creatures
            )
            if provoked:
                # 将触发结果写入响应头，供调用方（前端/WS 层）决策
                # 实际广播由 WS 层完成；REST 调用方可读取 X-OA-Triggered
                import json
                oa_list = [{"instance_id": a.instance_id, "name": a.name} for a in provoked]
                saved.__dict__["_oa_triggered"] = oa_list
        except Exception:
            pass

    return saved


@router.get("/{campaign_id}/encounter-maps/{map_id}/movement-range")
async def get_movement_range(
    campaign_id: str,
    map_id: str,
    creature_instance_id: str,
):
    """获取指定生物本回合剩余移动力内的可达格子列表"""
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    creature = next((c for c in m.creatures if c.instance_id == creature_instance_id), None)
    if creature is None:
        raise HTTPException(status_code=404, detail="生物不存在")

    from .movement import get_creature_speed, calculate_movement_range
    from character.storage import get_character

    max_spd = await get_creature_speed(creature)
    if creature.character_id:
        sheet = await get_character(creature.character_id)
        used = sheet.movement_used if sheet else 0
    else:
        used = creature.movement_used

    remaining = max(0, max_spd - used)
    reachable = calculate_movement_range(
        m.cells, m.creatures,
        creature.y, creature.x,
        remaining,
        exclude_instance_id=creature_instance_id,
    )

    return {
        "creature_id": creature_instance_id,
        "max_movement": max_spd,
        "movement_used": used,
        "remaining_movement": remaining,
        "reachable_cells": reachable,
    }


@router.get("/{campaign_id}/encounter-maps/{map_id}/spell-area")
async def get_spell_area(
    campaign_id: str,
    map_id: str,
    origin_row: int,
    origin_col: int,
    shape: str = "sphere",
    size_ft: int = 20,
    direction_row: float = 0.0,
    direction_col: float = 1.0,
    check_los: bool = True,
):
    """
    计算法术 AoE 覆盖范围，返回可高亮的格子列表。

    shape: sphere（火球术等圆形）| cone（锥形）| line（直线）| cube（正方形）
    size_ft: 半径/长度/边长（英尺）
    direction_row/direction_col: 法术朝向向量（cone/line/cube 时有意义）
    check_los: 是否只返回有视线的格子（穿墙法术传 false）

    示例：
      火球术 20ft 圆形，施法点 (5,5)：
        ?origin_row=5&origin_col=5&shape=sphere&size_ft=20
      燃烧之手 15ft 锥形，朝右：
        ?origin_row=5&origin_col=5&shape=cone&size_ft=15&direction_row=0&direction_col=1
      闪电链 100ft 直线，朝下：
        ?origin_row=0&origin_col=5&shape=line&size_ft=100&direction_row=1&direction_col=0
    """
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    if not m.cells:
        raise HTTPException(status_code=400, detail="地图格子数据为空，请先生成地牢或上传背景图并标注地形")

    rows = len(m.cells)
    cols = len(m.cells[0]) if rows else 0
    if not (0 <= origin_row < rows and 0 <= origin_col < cols):
        raise HTTPException(status_code=400, detail=f"原点坐标超出地图范围 ({rows}×{cols})")

    from .spell_area import calculate_spell_area, VALID_SHAPES
    if shape not in VALID_SHAPES:
        raise HTTPException(status_code=400, detail=f"不支持的形状 {shape!r}，可选：{sorted(VALID_SHAPES)}")

    if size_ft <= 0 or size_ft > 1000:
        raise HTTPException(status_code=400, detail="size_ft 必须在 1–1000 之间")

    area_cells = calculate_spell_area(
        cells=m.cells,
        origin_row=origin_row,
        origin_col=origin_col,
        shape=shape,
        size_ft=size_ft,
        direction_row=direction_row,
        direction_col=direction_col,
        check_los=check_los,
    )

    # 统计范围内有多少已知生物
    creatures_in_area: list[dict] = []
    area_set = {(cell.row, cell.col) for cell in area_cells}
    for creature in m.creatures:
        if (creature.y, creature.x) in area_set:
            creatures_in_area.append({
                "instance_id": creature.instance_id,
                "name":        creature.name,
                "row":         creature.y,
                "col":         creature.x,
                "is_player":   creature.is_player,
                "is_hidden":   creature.is_hidden,
            })

    return {
        "map_id":           map_id,
        "origin":           {"row": origin_row, "col": origin_col},
        "shape":            shape,
        "size_ft":          size_ft,
        "direction":        {"row": direction_row, "col": direction_col},
        "check_los":        check_los,
        "cells":            [c.as_dict() for c in area_cells],
        "total_cells":      len(area_cells),
        "creatures_in_area": creatures_in_area,
    }


def _parse_walk_speed(speed_str: str) -> int:
    """Extract the first walking speed value (ft) from a speed string like '30尺，飞行60尺'."""
    import re
    if not speed_str:
        return 30
    # Skip entries that start with a movement type keyword (飞行/游泳/攀爬/挖掘/悬浮)
    for segment in re.split(r"[，,、；;]", speed_str):
        segment = segment.strip()
        if re.match(r"^(飞行|游泳|攀爬|挖掘|悬浮)", segment):
            continue
        m = re.search(r"(\d+)", segment)
        if m:
            return int(m.group(1))
    return 30


class MonsterPlacementEntry(BaseModel):
    monster_id: str
    count: int = Field(default=1, ge=1, le=50)
    # --- 可选微调项（不填则使用规则库原始数值）---
    hp_override: int | None = Field(default=None, ge=1, description="覆盖 HP")
    hp_multiplier: float | None = Field(default=None, gt=0, description="HP 倍率，如 1.5 表示精英变体")
    ac_override: int | None = Field(default=None, ge=1, description="覆盖 AC（仅记录，暂不参与计算）")
    speed_override: int | None = Field(default=None, ge=0, description="覆盖步行速度（尺）")
    name_prefix: str | None = Field(default=None, description="名称前缀，如'精英'")
    is_hidden: bool = Field(default=False, description="是否以隐藏状态入场（DM视角才可见）")
    conditions: list[str] = Field(default_factory=list, description="初始状态条件，如['prone']")


class SimulateRequest(BaseModel):
    player_character_ids: list[str] = Field(default_factory=list)
    extra_monsters: list[MonsterPlacementEntry] = Field(default_factory=list)


@router.post("/{campaign_id}/encounter-maps/{map_id}/simulate", response_model=EncounterMap)
async def simulate_encounter(
    campaign_id: str,
    map_id: str,
    req: SimulateRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM: 初始化遭遇战（放置角色和怪物到棋盘，掷先攻）。
    """
    import random
    _require_dm(x_role)
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    rng = random.Random()
    creatures: list[MapCreature] = []
    col = 1

    # 放置玩家角色
    from character.storage import get_character
    for char_id in req.player_character_ids:
        sheet = await get_character(char_id)
        if sheet is None:
            continue
        dex_mod = sheet.ability_scores.modifier("dexterity")
        initiative = rng.randint(1, 20) + dex_mod
        creatures.append(MapCreature(
            name=sheet.name,
            character_id=char_id,
            x=col,
            y=1,
            hp_current=sheet.hit_points.current,
            hp_max=sheet.hit_points.maximum,
            is_player=True,
            initiative=initiative,
        ))
        col += 1

    # 放置怪物
    from monster.storage import get_monster
    monster_col = m.grid_cols - 2
    for entry in req.extra_monsters:
        monster = await get_monster(entry.monster_id)
        if monster is None:
            continue

        # HP：微调覆盖 > HP 倍率 > 规则库原值
        base_hp = monster.hp or 1
        if entry.hp_override is not None:
            final_hp = entry.hp_override
        elif entry.hp_multiplier is not None:
            final_hp = max(1, round(base_hp * entry.hp_multiplier))
        else:
            final_hp = base_hp

        # 步行速度：微调覆盖 > 解析规则库字符串
        final_speed = entry.speed_override if entry.speed_override is not None \
            else _parse_walk_speed(monster.speed or "")

        dex_mod = monster.abilities.modifier("dex") if monster.abilities else 0
        base_name = entry.name_prefix + monster.name_cn if entry.name_prefix else monster.name_cn

        # 推断传奇动作总点数（有传奇动作则默认 3，可从描述文本中解析实际数字）
        leg_max = 0
        if monster.legendary_actions:
            import re as _re
            leg_max = 3  # D&D 5e 绝大多数传奇生物为 3 点
            if monster.legendary_action_desc:
                # 中文描述格式："传奇动作次数：3（巢穴内4）"，\b 对中文字符无效
                m_num = _re.search(r'传奇动作次数[：:]\s*(\d+)', monster.legendary_action_desc)
                if not m_num:
                    m_num = _re.search(r'(\d+)', monster.legendary_action_desc)
                if m_num:
                    leg_max = int(m_num.group(1))

        for i in range(entry.count):
            initiative = rng.randint(1, 20) + dex_mod
            display_name = f"{base_name}#{i+1}" if entry.count > 1 else base_name
            creatures.append(MapCreature(
                name=display_name,
                monster_id=entry.monster_id,
                x=monster_col,
                y=2 + i,
                hp_current=final_hp,
                hp_max=final_hp,
                speed=final_speed,
                is_player=False,
                is_hidden=entry.is_hidden,
                conditions=list(entry.conditions),
                initiative=initiative,
                legendary_actions_max=leg_max,
            ))

    m.creatures = creatures
    m.is_active = True
    return await save_encounter_map(m)


# ============================================================
#  程序化地牢生成
# ============================================================

class GenerateFloorRequest(BaseModel):
    room_count: int = Field(default=6, ge=2, le=30)
    seed: int | None = None
    style: str = Field(default="dungeon", pattern="^(dungeon|cave)$")


class EncounterMapWithSeed(EncounterMap):
    seed_used: int = 0


@router.post(
    "/{campaign_id}/encounter-maps/{map_id}/generate-floor",
    response_model=EncounterMapWithSeed,
)
async def generate_floor_endpoint(
    campaign_id: str,
    map_id: str,
    req: GenerateFloorRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 程序化生成遭遇战地牢地板布局（BSP 房间 或 CA 洞穴）"""
    _require_dm(x_role)
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    actual_seed = req.seed if req.seed is not None else random.randrange(2 ** 32)
    m.cells = generate_dungeon(m.grid_cols, m.grid_rows, req.room_count, actual_seed, req.style)
    saved = await save_encounter_map(m)
    return {**saved.model_dump(), "seed_used": actual_seed}


# ============================================================
#  A* 路径规划
# ============================================================

@router.get("/{campaign_id}/encounter-maps/{map_id}/path")
async def get_path(
    campaign_id: str,
    map_id: str,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    creature_instance_id: str | None = None,
):
    """
    返回从 (from_x, from_y) 到 (to_x, to_y) 的最优路径（A*）。

    响应：{"path": [{row, col, cost}, ...], "total_cost": int} 或 {"path": null} 若不可达。
    path 中不含起点，含终点，按移动顺序排列。
    """
    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    from .pathfinding import find_path
    path = find_path(
        m.cells, m.creatures,
        start_row=from_y, start_col=from_x,
        goal_row=to_y,   goal_col=to_x,
        exclude_instance_id=creature_instance_id,
    )
    total_cost = path[-1]["cost"] if path else 0
    return {"path": path, "total_cost": total_cost}


# ============================================================
#  区域地图
# ============================================================

class CreateRegionMapRequest(BaseModel):
    name: str
    description: str = ""
    region_type: RegionType = RegionType.OTHER
    area_km: float = 10.0
    image_prompt: str = ""             # 留空则使用预制提示词
    parent_world_map_id: str | None = None
    parent_poi_id: str | None = None


class GenerateRegionRequest(BaseModel):
    prompt: str = ""                   # 留空则用当前 image_prompt 或预制提示词
    width_px: int = 1024
    height_px: int = 1024
    save_prompt: bool = True           # 是否同时更新地图的 image_prompt 字段


@router.get("/{campaign_id}/region-maps", response_model=list[RegionMapSummary])
async def list_region_maps_endpoint(campaign_id: str):
    """列出战役下所有区域地图（摘要）"""
    maps = await list_region_maps(campaign_id)
    return [region_map_to_summary(m) for m in maps]


@router.post("/{campaign_id}/region-maps", response_model=RegionMap)
async def create_region_map(
    campaign_id: str,
    req: CreateRegionMapRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 创建区域地图（图片可稍后生成）"""
    _require_dm(x_role)
    prompt = req.image_prompt or REGION_PROMPT_PRESETS.get(req.region_type.value, REGION_PROMPT_PRESETS["other"])
    m = RegionMap(
        campaign_id=campaign_id,
        name=req.name,
        description=req.description,
        region_type=req.region_type,
        area_km=req.area_km,
        image_prompt=prompt,
        parent_world_map_id=req.parent_world_map_id,
        parent_poi_id=req.parent_poi_id,
    )
    return await save_region_map(m)


@router.get("/{campaign_id}/region-maps/{map_id}", response_model=RegionMap)
async def get_region_map_endpoint(campaign_id: str, map_id: str):
    """获取区域地图详情"""
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")
    return m


@router.put("/{campaign_id}/region-maps/{map_id}/prompt", response_model=RegionMap)
async def update_region_map_prompt(
    campaign_id: str,
    map_id: str,
    body: GenerateRegionRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 更新区域地图 AI 提示词（不生成图片）"""
    _require_dm(x_role)
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")
    if body.prompt:
        m.image_prompt = body.prompt
    return await save_region_map(m)


@router.get("/{campaign_id}/region-maps/presets", response_model=dict)
async def get_region_presets():
    """返回所有区域类型的预制提示词"""
    return REGION_PROMPT_PRESETS


@router.post("/{campaign_id}/region-maps/{map_id}/generate", response_model=RegionMap)
async def generate_region_map_endpoint(
    campaign_id: str,
    map_id: str,
    req: GenerateRegionRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 用 AI 生成区域地图图片。prompt 留空则使用当前保存的提示词。"""
    _require_dm(x_role)
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")

    effective_prompt = (
        req.prompt
        or m.image_prompt
        or REGION_PROMPT_PRESETS.get(m.region_type.value, REGION_PROMPT_PRESETS["other"])
    )
    m.image_url = await generate_region_map(effective_prompt, req.width_px, req.height_px)
    if req.save_prompt:
        m.image_prompt = effective_prompt
    return await save_region_map(m)


@router.delete("/{campaign_id}/region-maps/{map_id}")
async def delete_region_map_endpoint(
    campaign_id: str,
    map_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 删除区域地图"""
    _require_dm(x_role)
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")
    await delete_region_map(map_id)
    return {"success": True}


# ---- 区域地图 POI ----

@router.post("/{campaign_id}/region-maps/{map_id}/poi", response_model=RegionMap)
async def add_region_poi(
    campaign_id: str,
    map_id: str,
    poi: PointOfInterest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 为区域地图添加兴趣点"""
    _require_dm(x_role)
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")
    m.pois.append(poi)
    return await save_region_map(m)


@router.delete("/{campaign_id}/region-maps/{map_id}/poi/{poi_id}", response_model=RegionMap)
async def delete_region_poi(
    campaign_id: str,
    map_id: str,
    poi_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 删除区域地图兴趣点"""
    _require_dm(x_role)
    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")
    m.pois = [p for p in m.pois if p.id != poi_id]
    return await save_region_map(m)


# ============================================================
#  本地地牢编辑器（浏览器 Canvas UI）
# ============================================================

_EDITOR_HTML = Path(__file__).parent.parent / "static" / "dungeon_editor.html"

editor_router = APIRouter(tags=["dungeon-editor"])


@editor_router.get("/dungeon-editor/{campaign_id}/{map_id}", response_class=HTMLResponse)
async def serve_dungeon_editor(campaign_id: str, map_id: str):
    """提供地牢编辑器 HTML 页面，注入战役 ID 和地图 ID"""
    if not _EDITOR_HTML.exists():
        raise HTTPException(status_code=503, detail="编辑器文件不存在，请检查部署")
    html = _EDITOR_HTML.read_text(encoding="utf-8")
    html = html.replace("__CAMPAIGN_ID__", campaign_id).replace("__MAP_ID__", map_id)
    return HTMLResponse(html)
