"""
战役 FastAPI 路由

包含:
  - 战役 CRUD
  - 成员/角色管理
  - 状态切换
  - DM 总览 (GET /overview)
  - DM 视角 (GET /dm-view) — 含隐藏信息
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .models import Campaign, CampaignStatus, CampaignSummary, CampaignInvite, campaign_to_summary
from .storage import (
    delete_campaign, get_campaign, list_campaigns_by_dm,
    list_campaigns_by_player, save_campaign,
)

router = APIRouter(prefix="/api/campaign", tags=["campaign"])


def _require_owner(x_owner_id: str | None) -> str:
    if not x_owner_id:
        raise HTTPException(status_code=401, detail="缺少 X-Owner-Id header")
    return x_owner_id


def _require_dm(x_role: str | None) -> None:
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="此操作需要 DM 权限")


# ============================================================
#  CRUD
# ============================================================

@router.post("", response_model=Campaign)
async def create_campaign(
    camp: Campaign,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_owner_display: str | None = Header(None, alias="X-Owner-Display"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """创建战役（需要 DM 权限）"""
    _require_dm(x_role)
    owner_id = _require_owner(x_owner_id)
    camp.dm_owner_id = owner_id
    if x_owner_display:
        camp.dm_display = x_owner_display
    return await save_campaign(camp)


@router.get("/{campaign_id}", response_model=Campaign)
async def api_get_campaign(campaign_id: str):
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    return camp


@router.get("", response_model=list[CampaignSummary])
async def api_list_campaigns(
    scope: str = Query("mine", description="mine=我的战役 / player=参与的战役"),
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
):
    owner_id = _require_owner(x_owner_id)
    if scope == "player":
        camps = await list_campaigns_by_player(owner_id)
    else:
        camps = await list_campaigns_by_dm(owner_id)
    return [campaign_to_summary(c) for c in camps]


@router.put("/{campaign_id}", response_model=Campaign)
async def api_update_campaign(
    campaign_id: str,
    camp: Campaign,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    owner_id = _require_owner(x_owner_id)
    existing = await get_campaign(campaign_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    if existing.dm_owner_id != owner_id:
        raise HTTPException(status_code=403, detail="只有战役 DM 可以修改战役")
    camp.id = campaign_id
    camp.dm_owner_id = existing.dm_owner_id
    camp.created_at = existing.created_at
    return await save_campaign(camp)


@router.delete("/{campaign_id}")
async def api_delete_campaign(
    campaign_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    owner_id = _require_owner(x_owner_id)
    existing = await get_campaign(campaign_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    if existing.dm_owner_id != owner_id:
        raise HTTPException(status_code=403, detail="只有战役 DM 可以删除战役")
    ok = await delete_campaign(campaign_id)
    return {"success": ok}


# ============================================================
#  成员管理
# ============================================================

class MemberRequest(BaseModel):
    player_id: str


@router.post("/{campaign_id}/players", response_model=Campaign)
async def add_player(
    campaign_id: str,
    req: MemberRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 将玩家加入战役"""
    _require_dm(x_role)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    if req.player_id not in camp.player_ids:
        camp.player_ids.append(req.player_id)
    return await save_campaign(camp)


@router.delete("/{campaign_id}/players/{player_id}", response_model=Campaign)
async def remove_player(
    campaign_id: str,
    player_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 将玩家移出战役"""
    _require_dm(x_role)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    camp.player_ids = [p for p in camp.player_ids if p != player_id]
    return await save_campaign(camp)


@router.post("/{campaign_id}/characters/{character_id}", response_model=Campaign)
async def add_character(
    campaign_id: str,
    character_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """将角色关联到战役"""
    _require_owner(x_owner_id)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    if character_id not in camp.character_ids:
        camp.character_ids.append(character_id)
    return await save_campaign(camp)


@router.delete("/{campaign_id}/characters/{character_id}", response_model=Campaign)
async def remove_character(
    campaign_id: str,
    character_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 将角色移出战役"""
    _require_dm(x_role)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    camp.character_ids = [c for c in camp.character_ids if c != character_id]
    return await save_campaign(camp)


# ============================================================
#  状态切换
# ============================================================

class StatusRequest(BaseModel):
    status: CampaignStatus


@router.patch("/{campaign_id}/status", response_model=Campaign)
async def update_status(
    campaign_id: str,
    req: StatusRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    _require_dm(x_role)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    camp.status = req.status
    return await save_campaign(camp)


# ============================================================
#  Phase D1 — DM 战役总览
# ============================================================

class CampaignOverview(BaseModel):
    """战役完整运行状态，供 DM 编辑器/总览面板使用"""
    campaign: CampaignSummary
    characters: list[dict[str, Any]] = Field(default_factory=list)
    active_session: dict[str, Any] | None = None
    world_map: dict[str, Any] | None = None
    encounter_maps: list[dict[str, Any]] = Field(default_factory=list)
    monsters_in_play: list[dict[str, Any]] = Field(default_factory=list)
    op_log_recent: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


@router.get("/{campaign_id}/overview", response_model=CampaignOverview)
async def campaign_overview(
    campaign_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM 战役总览。

    返回：
    - 战役元数据摘要
    - 所有参团角色（含 derived stats）
    - 最近活跃的 GameSession 快照
    - 世界地图摘要
    - 所有遭遇战地图摘要
    - 当前活跃遭遇战中的怪物列表
    - 最近 20 条操作日志
    - 简要统计（玩家数/角色数/存活/倒下）
    """
    _require_dm(x_role)

    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")

    # ---- 角色列表（含 derived stats） ----
    from character.storage import get_character
    from character.calculator import compute_derived_stats

    characters: list[dict[str, Any]] = []
    alive_count = 0
    downed_count = 0
    for char_id in camp.character_ids:
        sheet = await get_character(char_id)
        if sheet is None:
            continue
        derived = compute_derived_stats(sheet)
        hp = sheet.hit_points
        char_info: dict[str, Any] = {
            "id": sheet.id,
            "name": sheet.name,
            "owner_id": sheet.owner_id,
            "owner_display": sheet.owner_display,
            "total_level": sheet.total_level,
            "hp_current": hp.current,
            "hp_max": hp.maximum,
            "hp_temp": hp.temporary,
            "is_dying": hp.is_dying,
            "exhaustion_level": sheet.exhaustion_level,
            "conditions": [c.value for c in sheet.conditions],
            "ac": derived["ac"],
            "is_polymorphed": sheet.is_polymorphed,
            "dm_approved": sheet.dm_approved,
        }
        characters.append(char_info)
        if hp.current > 0:
            alive_count += 1
        else:
            downed_count += 1

    # ---- 最近 GameSession ----
    from session.storage import get_latest_session, get_op_log
    active_session_dict: dict[str, Any] | None = None
    op_log_recent: list[dict[str, Any]] = []
    session = await get_latest_session(campaign_id)
    if session:
        active_session_dict = session.model_dump()
        logs = await get_op_log(session.id, limit=20)
        op_log_recent = [lg.model_dump() for lg in logs]

    # ---- 世界地图 ----
    from maps.storage import get_campaign_world_map, list_encounter_maps
    from maps.models import world_map_to_summary, encounter_map_to_summary
    world_map_dict: dict[str, Any] | None = None
    wmap = await get_campaign_world_map(campaign_id)
    if wmap:
        world_map_dict = world_map_to_summary(wmap).model_dump()

    # ---- 遭遇战地图 ----
    emaps = await list_encounter_maps(campaign_id)
    encounter_maps_list = [encounter_map_to_summary(m).model_dump() for m in emaps]

    # ---- 当前遭遇战中的怪物 ----
    monsters_in_play: list[dict[str, Any]] = []
    active_map = next((m for m in emaps if m.is_active), None)
    if active_map:
        for creature in active_map.creatures:
            if not creature.is_player and creature.monster_id:
                monsters_in_play.append({
                    "instance_id": creature.instance_id,
                    "name": creature.name,
                    "monster_id": creature.monster_id,
                    "hp_current": creature.hp_current,
                    "hp_max": creature.hp_max,
                    "x": creature.x,
                    "y": creature.y,
                    "conditions": creature.conditions,
                    "is_hidden": creature.is_hidden,
                })

    # ---- 统计 ----
    stats = {
        "player_count": len(camp.player_ids),
        "character_count": len(camp.character_ids),
        "characters_alive": alive_count,
        "characters_downed": downed_count,
        "encounter_map_count": len(emaps),
        "has_active_encounter": active_map is not None,
        "session_count": camp.session_count,
    }

    return CampaignOverview(
        campaign=campaign_to_summary(camp),
        characters=characters,
        active_session=active_session_dict,
        world_map=world_map_dict,
        encounter_maps=encounter_maps_list,
        monsters_in_play=monsters_in_play,
        op_log_recent=op_log_recent,
        stats=stats,
    )


# ============================================================
#  Phase D2 — DM 遭遇战编辑器（棋盘生物管理）
# ============================================================

class PlaceCreatureRequest(BaseModel):
    """DM 向棋盘上添加生物"""
    name: str
    monster_id: str | None = None
    character_id: str | None = None
    x: int = 0
    y: int = 0
    hp_override: int | None = None       # 覆盖默认 HP
    is_hidden: bool = False


@router.post(
    "/{campaign_id}/encounter-maps/{map_id}/creatures",
    tags=["maps"],
)
async def place_creature(
    campaign_id: str,
    map_id: str,
    req: PlaceCreatureRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 在棋盘上放置生物（怪物或玩家角色）"""
    _require_dm(x_role)
    from maps.storage import get_encounter_map, save_encounter_map
    from maps.models import MapCreature
    from monster.storage import get_monster
    from character.storage import get_character

    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    hp = req.hp_override
    is_player = False

    if req.monster_id:
        monster = await get_monster(req.monster_id)
        if monster and hp is None:
            hp = monster.hp or 1
    elif req.character_id:
        sheet = await get_character(req.character_id)
        if sheet and hp is None:
            hp = sheet.hit_points.current
        is_player = True

    hp = hp or 1
    creature = MapCreature(
        name=req.name,
        monster_id=req.monster_id,
        character_id=req.character_id,
        x=req.x,
        y=req.y,
        hp_current=hp,
        hp_max=hp,
        is_hidden=req.is_hidden,
        is_player=is_player,
    )
    m.creatures.append(creature)
    saved = await save_encounter_map(m)
    return {"encounter_map": saved.model_dump(), "placed": creature.model_dump()}


@router.delete(
    "/{campaign_id}/encounter-maps/{map_id}/creatures/{instance_id}",
    tags=["maps"],
)
async def remove_creature(
    campaign_id: str,
    map_id: str,
    instance_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 从棋盘移除生物"""
    _require_dm(x_role)
    from maps.storage import get_encounter_map, save_encounter_map

    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    before = len(m.creatures)
    m.creatures = [c for c in m.creatures if c.instance_id != instance_id]
    if len(m.creatures) == before:
        raise HTTPException(status_code=404, detail=f"生物实例 {instance_id} 不存在")

    saved = await save_encounter_map(m)
    return {"success": True, "remaining_creatures": len(saved.creatures)}


class RollInitiativeRequest(BaseModel):
    """DM: 为棋盘上的所有生物掷先攻"""
    reroll_players: bool = Field(False, description="是否重掷玩家角色的先攻")


async def _do_roll_initiative(map_id: str, reroll_players: bool = False) -> dict:
    """
    核心先攻投骰逻辑（被 REST 端点和 WS 处理器共用）。

    返回:
    {
        "encounter_map_id": str,
        "initiative_order": [{"instance_id", "name", "initiative", ...}, ...]
    }
    initiative_order 已按先攻从高到低排序。
    """
    import random
    from maps.storage import get_encounter_map, save_encounter_map
    from monster.storage import get_monster
    from character.storage import get_character
    from character.calculator import ability_modifier

    m = await get_encounter_map(map_id)
    if m is None:
        return {"error": f"遭遇战地图不存在: {map_id}"}

    rng = random.Random()

    for creature in m.creatures:
        if creature.is_player and not reroll_players and creature.initiative != 0:
            continue   # 保留已有先攻

        dex_mod = 0
        if creature.is_player and creature.character_id:
            sheet = await get_character(creature.character_id)
            if sheet:
                dex_mod = ability_modifier(sheet.ability_scores.dexterity)
        elif creature.monster_id:
            monster = await get_monster(creature.monster_id)
            if monster:
                dex_mod = monster.abilities.modifier("dex")

        creature.initiative = rng.randint(1, 20) + dex_mod

    saved = await save_encounter_map(m)

    initiative_order = sorted(
        [
            {
                "instance_id": c.instance_id,
                "name": c.name,
                "initiative": c.initiative,
                "is_player": c.is_player,
                "hp_current": c.hp_current,
                "hp_max": c.hp_max,
                "is_hidden": c.is_hidden,
                "character_id": c.character_id,
                "monster_id": c.monster_id,
            }
            for c in saved.creatures
        ],
        key=lambda x: x["initiative"],
        reverse=True,
    )

    return {
        "encounter_map_id": map_id,
        "initiative_order": initiative_order,
    }


@router.post(
    "/{campaign_id}/encounter-maps/{map_id}/roll-initiative",
    tags=["maps"],
)
async def roll_initiative_for_map(
    campaign_id: str,
    map_id: str,
    req: RollInitiativeRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM: 为棋盘上所有生物掷先攻，返回排好序的先攻列表。

    响应中包含：
    - encounter_map_id
    - initiative_order：按先攻从高到低排序的列表
    """
    from maps.storage import get_encounter_map
    _require_dm(x_role)

    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    result = await _do_roll_initiative(map_id, req.reroll_players)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class DmEncounterView(BaseModel):
    """DM 遭遇战视角 — 含隐藏信息"""
    encounter_map_id: str
    name: str
    grid_cols: int
    grid_rows: int
    image_url: str | None
    all_creatures: list[dict[str, Any]] = Field(default_factory=list)     # 包含 is_hidden=True 的生物
    player_visible_creatures: list[dict[str, Any]] = Field(default_factory=list)  # 玩家可见子集
    objects: list[dict[str, Any]] = Field(default_factory=list)
    initiative_order: list[dict[str, Any]] = Field(default_factory=list)


@router.get(
    "/{campaign_id}/encounter-maps/{map_id}/dm-view",
    response_model=DmEncounterView,
    tags=["maps"],
)
async def get_encounter_dm_view(
    campaign_id: str,
    map_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM 专属遭遇战视角。

    与普通 GET /encounter-maps/{id} 的区别：
    - all_creatures 包含所有生物（含 is_hidden=True 的隐藏怪物）
    - player_visible_creatures 只包含玩家可见的生物（is_hidden=False）
    - 所有生物的完整 HP 数值可见（玩家侧只看到模糊状态）
    """
    _require_dm(x_role)
    from maps.storage import get_encounter_map

    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    def _creature_to_dict(c, dm_mode: bool) -> dict[str, Any]:
        d = c.model_dump()
        if not dm_mode:
            # 玩家视角: 怪物 HP 模糊化
            if not c.is_player:
                d["hp_current"] = None
                d["hp_max"] = None
                d["hp_status"] = _hp_status(c.hp_current, c.hp_max)
        return d

    all_creatures = [_creature_to_dict(c, dm_mode=True) for c in m.creatures]
    player_visible = [
        _creature_to_dict(c, dm_mode=False)
        for c in m.creatures
        if not c.is_hidden
    ]

    initiative_order = sorted(
        [{"instance_id": c.instance_id, "name": c.name,
          "initiative": c.initiative, "is_player": c.is_player}
         for c in m.creatures],
        key=lambda x: x["initiative"],
        reverse=True,
    )

    return DmEncounterView(
        encounter_map_id=m.id,
        name=m.name,
        grid_cols=m.grid_cols,
        grid_rows=m.grid_rows,
        image_url=m.image_url,
        all_creatures=all_creatures,
        player_visible_creatures=player_visible,
        objects=[o.model_dump() for o in m.objects],
        initiative_order=initiative_order,
    )


# ============================================================
#  遭遇结算：战利品 + XP 分配
# ============================================================

class LootItem(BaseModel):
    name: str
    quantity: int = 1
    item_type: str = "misc"    # "weapon"/"armor"/"potion"/"misc"
    notes: str = ""


class EncounterRewardRequest(BaseModel):
    """DM 结算遭遇奖励"""
    encounter_map_id: str = ""           # 可选，关联遭遇地图
    recipient_character_ids: list[str]   # 获得奖励的角色 id 列表
    xp_total: int = 0                    # 本次遭遇总经验值（自动平分）
    gold: float = 0.0                    # 金币（自动平分）
    silver: float = 0.0
    copper: float = 0.0
    items: list[LootItem] = Field(default_factory=list)  # 特定物品（不自动分配，仅记录）
    note: str = ""                       # DM 备注


class EncounterRewardResult(BaseModel):
    xp_per_character: int = 0
    gold_per_character: float = 0.0
    silver_per_character: float = 0.0
    copper_per_character: float = 0.0
    items: list[LootItem] = Field(default_factory=list)
    recipients_updated: list[str] = Field(default_factory=list)
    leveled_up: list[dict[str, Any]] = Field(default_factory=list)  # 升级信息列表
    errors: list[str] = Field(default_factory=list)


@router.post(
    "/{campaign_id}/encounter-reward",
    response_model=EncounterRewardResult,
    tags=["encounter"],
)
async def distribute_encounter_reward(
    campaign_id: str,
    req: EncounterRewardRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM 结算遭遇奖励：自动将 XP 和货币平分给指定角色，并向战役房间 WS 广播战利品消息。

    - XP 不直接触发升级，只记录在角色 class_resources（或返回数据中），由玩家确认后手动升级
    - 货币直接加入角色卡
    - 物品仅记录在结果中，需 DM 手动通过 /inventory 端点分配给具体角色
    """
    _require_dm(x_role)

    if not req.recipient_character_ids:
        raise HTTPException(status_code=400, detail="recipients 不能为空")

    from character.storage import get_character, save_character
    from character.xp_system import apply_xp as _apply_xp

    n = len(req.recipient_character_ids)
    xp_each = req.xp_total // n if n > 0 else 0
    gold_each = round(req.gold / n, 2) if n > 0 else 0.0
    silver_each = round(req.silver / n, 2) if n > 0 else 0.0
    copper_each = round(req.copper / n, 2) if n > 0 else 0.0

    updated: list[str] = []
    leveled_up: list[dict[str, Any]] = []
    errors: list[str] = []

    for char_id in req.recipient_character_ids:
        sheet = await get_character(char_id)
        if sheet is None:
            errors.append(f"角色不存在: {char_id}")
            continue
        if sheet.campaign_id != campaign_id:
            errors.append(f"角色 {char_id} 不属于此战役")
            continue

        # 分配货币
        sheet = sheet.model_copy(update={
            "gold":   round(sheet.gold + gold_each, 2),
            "silver": round(sheet.silver + silver_each, 2),
            "copper": round(sheet.copper + copper_each, 2),
        })

        # 直接累加 XP（使用 XP 系统计算升级）
        if xp_each > 0:
            xp_result = _apply_xp(char_id, sheet.xp_total, xp_each)
            sheet = sheet.model_copy(update={
                "xp_total": xp_result.xp_after,
                "xp_to_next_level": xp_result.xp_to_next,
            })
            if xp_result.leveled_up:
                leveled_up.append({
                    "character_id": char_id,
                    "character_name": sheet.name,
                    "level_before": xp_result.level_before,
                    "level_after": xp_result.level_after,
                    "xp_after": xp_result.xp_after,
                })

        await save_character(sheet)
        updated.append(char_id)

    return EncounterRewardResult(
        xp_per_character=xp_each,
        gold_per_character=gold_each,
        silver_per_character=silver_each,
        copper_per_character=copper_each,
        items=req.items,
        recipients_updated=updated,
        leveled_up=leveled_up,
        errors=errors,
    )


# ============================================================
#  战役邀请码
# ============================================================

class CreateInviteRequest(BaseModel):
    max_uses: int = Field(default=10, ge=-1, description="-1=无限次")
    expires_at: str = Field(default="", description="ISO 时间戳，空=永不过期")


@router.post("/{campaign_id}/invite", response_model=CampaignInvite, tags=["invite"])
async def create_invite_code(
    campaign_id: str,
    req: CreateInviteRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 生成邀请码，玩家凭码加入战役"""
    _require_dm(x_role)
    camp = await get_campaign(campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="战役不存在")
    from .storage import create_invite as _create_invite
    from .models import CampaignInvite
    invite = CampaignInvite(
        campaign_id=campaign_id,
        campaign_name=camp.name,
        dm_display=camp.dm_display,
        max_uses=req.max_uses,
        expires_at=req.expires_at,
    )
    return await _create_invite(invite)


@router.get("/{campaign_id}/invite", response_model=list[CampaignInvite], tags=["invite"])
async def list_invite_codes(
    campaign_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 查看该战役的所有邀请码"""
    _require_dm(x_role)
    from .storage import list_invites
    return await list_invites(campaign_id)


@router.delete("/{campaign_id}/invite/{code}", tags=["invite"])
async def deactivate_invite_code(
    campaign_id: str,
    code: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 作废一个邀请码"""
    _require_dm(x_role)
    from .storage import deactivate_invite
    ok = await deactivate_invite(code)
    return {"success": ok}


@router.post("/join/{code}", tags=["invite"])
async def join_campaign_by_invite(
    code: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
):
    """
    玩家凭邀请码加入战役（无需 DM 操作）。

    成功后返回战役基本信息，供玩家跳转到战役房间。
    """
    from fastapi import Header as _Header
    owner_id = x_owner_id
    if not owner_id:
        raise HTTPException(status_code=401, detail="需要提供 X-Owner-Id 请求头")

    from .storage import consume_invite
    invite, err = await consume_invite(code, owner_id)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if invite is None:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    await get_campaign(invite.campaign_id)  # 确认战役存在（不强制使用返回值）
    return {
        "campaign_id": invite.campaign_id,
        "campaign_name": invite.campaign_name,
        "dm_display": invite.dm_display,
        "message": f"成功加入战役「{invite.campaign_name}」",
    }


def _hp_status(current: int, maximum: int) -> str:
    """将怪物 HP 转为模糊描述（玩家侧使用）"""
    if maximum <= 0:
        return "未知"
    ratio = current / maximum
    if current <= 0:
        return "倒下"
    elif ratio > 0.75:
        return "状态良好"
    elif ratio > 0.5:
        return "轻微受伤"
    elif ratio > 0.25:
        return "重伤"
    else:
        return "濒死"
