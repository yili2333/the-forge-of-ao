"""
地图系统数据模型

世界地图 (WorldMap): 大地图，含 POI 标注和玩家进度追踪
遭遇战地图 (EncounterMap): 战斗棋盘，含格子数据和生物位置
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
#  世界地图
# ============================================================

class PoiType(str, Enum):
    CITY      = "city"
    DUNGEON   = "dungeon"
    RUINS     = "ruins"
    LANDMARK  = "landmark"
    TOWN      = "town"
    WILDERNESS = "wilderness"
    OTHER     = "other"


class PointOfInterest(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    x: float = 0.0                   # 百分比坐标（0-100）
    y: float = 0.0
    poi_type: PoiType = PoiType.OTHER
    description: str = ""
    is_hidden: bool = False           # DM 专属，玩家不可见
    visited_by: list[str] = Field(default_factory=list)   # owner_id 列表


class MapPosition(BaseModel):
    poi_id: str = ""                  # 当前所在 POI（空=旅途中）
    x: float = 0.0                   # 世界地图上的百分比坐标
    y: float = 0.0


class WorldMap(BaseModel):
    id: str = Field(default_factory=lambda: f"wmap-{uuid.uuid4().hex[:10]}")
    campaign_id: str
    name: str
    description: str = ""

    width_km: float = 1000.0
    height_km: float = 1000.0

    image_url: str | None = None     # 生成/上传的地图图片路径
    image_prompt: str = ""           # AI 生成用提示词（DM 可编辑）

    pois: list[PointOfInterest] = Field(default_factory=list)

    # player_positions: owner_id → MapPosition
    player_positions: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # visited_locations: owner_id → [poi_id, ...]
    visited_locations: dict[str, list[str]] = Field(default_factory=dict)

    fog_of_war: bool = True

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ============================================================
#  遭遇战地图（棋盘）
# ============================================================

class TerrainType(str, Enum):
    OPEN        = "open"
    DIFFICULT   = "difficult"
    WALL        = "wall"
    WATER       = "water"
    DOOR        = "door"
    COVER_HALF  = "cover_half"
    COVER_FULL  = "cover_full"


class CellData(BaseModel):
    terrain: TerrainType = TerrainType.OPEN
    elevation: int = 0               # 英尺，用于高地判定
    notes: str = ""                  # DM 标注
    is_visible: bool = True          # 是否已被玩家探索（迷雾）


class MapObject(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    x: int
    y: int
    object_type: str = "obstacle"    # "obstacle" / "trap" / "treasure" / "door" / "npc"
    description: str = ""
    is_hidden: bool = False          # DM 专属
    notes: str = ""


class MapCreature(BaseModel):
    instance_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    monster_id: str | None = None    # 关联 Monster 表
    character_id: str | None = None  # 关联 CharacterSheet 表
    x: int = 0
    y: int = 0
    hp_current: int = 0
    hp_max: int = 0
    conditions: list[str] = Field(default_factory=list)
    is_hidden: bool = False          # DM 视角才可见
    is_player: bool = False
    initiative: int = 0
    token_color: str = ""            # Unity 端 token 颜色标识
    speed: int = 30                  # 移动速度（英尺），怪物用；玩家角色从 CharacterSheet 读
    movement_used: int = 0           # 本回合已消耗移动力（英尺）
    action_used: bool = False        # 本回合行动已用
    bonus_action_used: bool = False  # 本回合附赠动作已用
    reaction_used: bool = False      # 本回合反应已用
    legendary_actions_max: int = 0   # 传奇动作总点数（无传奇动作的怪物为 0）
    legendary_actions_used: int = 0  # 本轮已消耗传奇动作点数（每轮开始重置）


class EncounterMap(BaseModel):
    id: str = Field(default_factory=lambda: f"emap-{uuid.uuid4().hex[:10]}")
    campaign_id: str
    name: str
    description: str = ""

    grid_cols: int = 20
    grid_rows: int = 20
    cell_size_ft: int = 5            # 每格 5 英尺

    image_url: str | None = None     # 背景图路径
    image_prompt: str = ""           # AI 生成提示词

    # 二维格子数据 (row × col)，初始化时可为空
    cells: list[list[dict[str, Any]]] = Field(default_factory=list)

    creatures: list[MapCreature] = Field(default_factory=list)
    objects: list[MapObject] = Field(default_factory=list)

    is_active: bool = False          # 是否为当前活动的遭遇战地图

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ============================================================
#  区域地图
# ============================================================

class RegionType(str, Enum):
    TOWN       = "town"
    CITY       = "city"
    FOREST     = "forest"
    DUNGEON    = "dungeon"
    COAST      = "coast"
    MOUNTAIN   = "mountain"
    PLAINS     = "plains"
    SWAMP      = "swamp"
    RUINS      = "ruins"
    OTHER      = "other"


# 每种区域类型对应的预制 AI 生成提示词
REGION_PROMPT_PRESETS: dict[str, str] = {
    "town": (
        "Fantasy RPG town map, top-down view, hand-drawn ink style, "
        "cobblestone streets, market square, tavern, blacksmith, "
        "town hall, residential districts, surrounding farmland, "
        "warm parchment paper background, detailed cartographic style"
    ),
    "city": (
        "Fantasy RPG city map, top-down bird's eye view, detailed hand-drawn style, "
        "city districts (merchant quarter, noble quarter, docks, slums), "
        "city walls with gates, cathedral, castle or palace, "
        "winding streets and alleys, parchment paper background"
    ),
    "forest": (
        "Fantasy RPG forest regional map, top-down view, hand-drawn style, "
        "dense canopy with clearings, winding forest paths, "
        "ancient ruins overgrown with vines, streams and small ponds, "
        "cave entrances, druidic stone circles, soft green watercolor tones"
    ),
    "dungeon": (
        "Fantasy RPG dungeon overview map, top-down view, hand-drawn dungeon cartography style, "
        "stone corridors and chambers, traps marked with skulls, "
        "treasure rooms, monster lairs, pit traps, torchlit passages, "
        "dark ink on parchment, classic dungeon crawl aesthetic"
    ),
    "coast": (
        "Fantasy RPG coastal region map, top-down view, hand-drawn nautical style, "
        "rocky cliffs and sandy beaches, sea caves, lighthouse, "
        "fishing village, shipwreck, tidal pools, "
        "blue watercolor ocean, sandy terrain, parchment map style"
    ),
    "mountain": (
        "Fantasy RPG mountain region map, top-down view, hand-drawn cartographic style, "
        "dramatic mountain peaks with snow caps, alpine passes, "
        "dwarven mine entrance, mountain fortress, waterfalls, "
        "highland meadows, rocky terrain, hand-drawn elevation shading"
    ),
    "plains": (
        "Fantasy RPG plains region map, top-down view, hand-drawn style, "
        "rolling grasslands, scattered farmsteads, ancient standing stones, "
        "river crossing, bandit camp, old battlefield with ruins, "
        "dirt roads connecting settlements, warm golden tones on parchment"
    ),
    "swamp": (
        "Fantasy RPG swamp region map, top-down view, hand-drawn style, "
        "murky waterways and boggy terrain, twisted dead trees, "
        "witch's hut on stilts, will-o-wisp clearing, sunken ruins, "
        "dark green and brown watercolor palette, eerie atmosphere"
    ),
    "ruins": (
        "Fantasy RPG ancient ruins map, top-down view, hand-drawn archaeological style, "
        "collapsed columns and broken walls, overgrown with vegetation, "
        "central plaza with altar, underground crypts, "
        "mysterious inscriptions, crumbling towers, parchment map with aged look"
    ),
    "other": (
        "Fantasy RPG regional map, top-down view, hand-drawn cartographic style, "
        "diverse terrain features, points of interest marked, "
        "paths and roads connecting locations, parchment paper background"
    ),
}


class RegionMap(BaseModel):
    id: str = Field(default_factory=lambda: f"rmap-{uuid.uuid4().hex[:10]}")
    campaign_id: str
    name: str
    description: str = ""

    region_type: RegionType = RegionType.OTHER
    area_km: float = 10.0              # 区域范围（公里）

    image_url: str | None = None
    image_prompt: str = ""             # DM 可自由编辑，默认由 region_type 预制

    pois: list[PointOfInterest] = Field(default_factory=list)

    # 可选：关联到父级世界地图上的 POI
    parent_world_map_id: str | None = None
    parent_poi_id: str | None = None

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ============================================================
#  请求/响应辅助模型
# ============================================================

class WorldMapSummary(BaseModel):
    id: str
    campaign_id: str
    name: str
    image_url: str | None
    poi_count: int
    player_count: int
    updated_at: str


class EncounterMapSummary(BaseModel):
    id: str
    campaign_id: str
    name: str
    grid_cols: int
    grid_rows: int
    image_url: str | None
    creature_count: int
    is_active: bool
    updated_at: str


def world_map_to_summary(m: WorldMap) -> WorldMapSummary:
    return WorldMapSummary(
        id=m.id,
        campaign_id=m.campaign_id,
        name=m.name,
        image_url=m.image_url,
        poi_count=len(m.pois),
        player_count=len(m.player_positions),
        updated_at=m.updated_at,
    )


def encounter_map_to_summary(m: EncounterMap) -> EncounterMapSummary:
    return EncounterMapSummary(
        id=m.id,
        campaign_id=m.campaign_id,
        name=m.name,
        grid_cols=m.grid_cols,
        grid_rows=m.grid_rows,
        image_url=m.image_url,
        creature_count=len(m.creatures),
        is_active=m.is_active,
        updated_at=m.updated_at,
    )


class RegionMapSummary(BaseModel):
    id: str
    campaign_id: str
    name: str
    region_type: RegionType
    image_url: str | None
    poi_count: int
    updated_at: str


def region_map_to_summary(m: RegionMap) -> RegionMapSummary:
    return RegionMapSummary(
        id=m.id,
        campaign_id=m.campaign_id,
        name=m.name,
        region_type=m.region_type,
        image_url=m.image_url,
        poi_count=len(m.pois),
        updated_at=m.updated_at,
    )
