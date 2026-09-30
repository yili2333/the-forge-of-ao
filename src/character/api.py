"""
人物卡 FastAPI 路由

路径前缀: /api/character

身份约定:
- 所有写操作需要 header `X-Owner-Id` (来自 IdentityManager 的 stable_key)
- DM 操作额外需要 `X-Role: dm`
- VPN 网络可信，不做 JWT；防误操作而非防攻击
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import storage
from .calculator import compute_ac, compute_derived_stats
from .effects_engine import apply_effect, remove_polymorph, apply_polymorph, apply_wish_permanent
from .models import ActiveEffect, CharacterSheet, Item
from .rest_engine import RestResult, long_rest, short_rest
from .spell_slots import get_spell_slots, merge_multiclass_spell_slots


router = APIRouter(prefix="/api/character", tags=["character"])

# 可选的休息完成广播回调（由 main.py 在启动时注入，避免循环导入）
# 签名: async (campaign_id, character_id, owner_id, rest_type, result) -> None
_rest_broadcast_hook: "Callable | None" = None   # type: ignore[type-arg]

# DM 审批广播 Hook（由 main.py 注入）
# 签名: async (campaign_id, sheet) -> None
_dm_approval_request_hook: "Callable | None" = None  # type: ignore[type-arg]
# 签名: async (campaign_id, sheet, approved, note) -> None
_dm_approval_result_hook: "Callable | None" = None   # type: ignore[type-arg]

# XP 增加广播 Hook（由 main.py 注入）
# 签名: async (campaign_id, owner_id, sheet_name, xp_result) -> None
_xp_broadcast_hook: "Callable | None" = None  # type: ignore[type-arg]


def set_rest_broadcast_hook(fn) -> None:
    """main.py 调用此函数注入 WS 广播回调"""
    global _rest_broadcast_hook
    _rest_broadcast_hook = fn


def set_dm_approval_hooks(request_fn, result_fn) -> None:
    """main.py 注入 DM 审批广播回调"""
    global _dm_approval_request_hook, _dm_approval_result_hook
    _dm_approval_request_hook = request_fn
    _dm_approval_result_hook = result_fn


def set_xp_broadcast_hook(fn) -> None:
    """main.py 注入 XP 广播回调"""
    global _xp_broadcast_hook
    _xp_broadcast_hook = fn


# ============================================================
#  请求/响应包装
# ============================================================

class CharacterSummary(BaseModel):
    """列表接口的精简视图"""
    id: str
    name: str
    owner_id: str
    owner_display: str
    campaign_id: str | None
    edition: str
    total_level: int
    non_standard: bool
    dm_approved: bool
    updated_at: str


def _to_summary(sheet: CharacterSheet) -> CharacterSummary:
    return CharacterSummary(
        id=sheet.id,
        name=sheet.name,
        owner_id=sheet.owner_id,
        owner_display=sheet.owner_display,
        campaign_id=sheet.campaign_id,
        edition=sheet.edition,
        total_level=sheet.total_level,
        non_standard=sheet.non_standard,
        dm_approved=sheet.dm_approved,
        updated_at=sheet.updated_at,
    )


class DMApprovalRequest(BaseModel):
    approved: bool
    note: str = ""


class ImportRequest(BaseModel):
    data: dict = Field(..., description="完整 CharacterSheet JSON 对象")
    copy_as_new: bool = Field(False, description="True 则视为新建副本，owner 改为调用者")


# ============================================================
#  身份辅助
# ============================================================

def _require_owner(x_owner_id: str | None) -> str:
    if not x_owner_id:
        raise HTTPException(status_code=401, detail="缺少 X-Owner-Id header")
    return x_owner_id


def _require_dm(x_role: str | None) -> None:
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="此操作需要 DM 权限")


def _check_ownership_or_dm(sheet: CharacterSheet, owner_id: str, role: str | None) -> None:
    if sheet.owner_id == owner_id:
        return
    if role == "dm":
        return
    raise HTTPException(status_code=403, detail="无权操作他人的角色卡")


# ============================================================
#  创建与更新
# ============================================================

@router.post("", response_model=CharacterSheet)
async def create_character(
    sheet: CharacterSheet,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_owner_display: str | None = Header(None, alias="X-Owner-Display"),
):
    """
    创建新角色卡。
    调用方应该已经在本地用 CharacterSheet 模型组装好完整数据，
    服务器只负责校验 + 持久化。
    """
    owner_id = _require_owner(x_owner_id)
    sheet.owner_id = owner_id
    if x_owner_display:
        sheet.owner_display = x_owner_display
    # 新建时强制版本重置
    sheet.version = 1
    sheet.created_at = ""
    sheet.updated_at = ""

    # 防止客户端传的 id 撞车
    if sheet.id:
        existing = await storage.get_character(sheet.id, include_deleted=True)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"角色 id 已存在: {sheet.id}。请使用 PUT /api/character/{{id}} 更新",
            )

    saved = await storage.save_character(sheet)

    # 若为非标准角色且加入了战役，异步通知 DM 审批
    if saved.non_standard and saved.campaign_id and _dm_approval_request_hook:
        import asyncio
        asyncio.create_task(_dm_approval_request_hook(saved.campaign_id, saved))

    return saved


@router.put("/{character_id}", response_model=CharacterSheet)
async def update_character(
    character_id: str,
    sheet: CharacterSheet,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """整体替换式更新。调用方需要先 GET 再 PUT，id 必须一致。"""
    owner_id = _require_owner(x_owner_id)
    if sheet.id != character_id:
        raise HTTPException(status_code=400, detail="body 中 id 与路径不一致")

    existing = await storage.get_character(character_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(existing, owner_id, x_role)

    # 保留原始 owner（防止改卡时被改主）
    sheet.owner_id = existing.owner_id
    sheet.owner_display = existing.owner_display
    sheet.created_at = existing.created_at

    saved = await storage.save_character(sheet)
    return saved


# ============================================================
#  读取
# ============================================================

@router.get("/{character_id}", response_model=CharacterSheet)
async def get_character(character_id: str):
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return sheet


@router.get("/{character_id}/summary")
async def get_character_summary(character_id: str):
    """包含派生值(AC/被动/豁免等)的完整摘要，供前端展示或 LLM 使用。"""
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {
        "sheet": sheet.model_dump(),
        "derived": compute_derived_stats(sheet),
        "context_text": sheet.to_context_summary(),
    }


@router.get("/{character_id}/context")
async def get_character_context(character_id: str):
    """只返回给 LLM 用的简明文本摘要。"""
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"context_text": sheet.to_context_summary()}


@router.get("", response_model=list[CharacterSummary])
async def list_characters(
    owner_id: str | None = Query(None),
    campaign_id: str | None = Query(None),
    scope: Literal["mine", "campaign", "pending"] = Query("mine"),
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
):
    """
    列出角色卡。scope:
    - mine     : 调用者自己的所有角色（owner_id 可选覆盖，DM 看别人时用）
    - campaign : 某战役下所有角色（需要 campaign_id）
    - pending  : 所有待 DM 审批的非标准卡
    """
    if scope == "mine":
        target = owner_id or _require_owner(x_owner_id)
        sheets = await storage.list_characters_by_owner(target)
    elif scope == "campaign":
        if not campaign_id:
            raise HTTPException(status_code=400, detail="scope=campaign 需要 campaign_id")
        sheets = await storage.list_characters_by_campaign(campaign_id)
    elif scope == "pending":
        sheets = await storage.list_pending_approval(campaign_id)
    else:
        raise HTTPException(status_code=400, detail=f"未知 scope: {scope}")

    return [_to_summary(s) for s in sheets]


# ============================================================
#  DM 审批
# ============================================================

@router.post("/{character_id}/approve", response_model=CharacterSheet)
async def approve_character(
    character_id: str,
    payload: DMApprovalRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 审批 non_standard 的角色卡"""
    _require_dm(x_role)
    result = await storage.mark_dm_approval(character_id, payload.approved, payload.note)
    if result is None:
        raise HTTPException(status_code=404, detail="角色不存在")

    # 通知角色拥有者审批结果
    if result.campaign_id and _dm_approval_result_hook:
        import asyncio
        asyncio.create_task(
            _dm_approval_result_hook(result.campaign_id, result, payload.approved, payload.note)
        )

    return result


# ============================================================
#  删除与恢复
# ============================================================

@router.delete("/{character_id}")
async def delete_character(
    character_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """软删除，可由 POST /restore 恢复"""
    owner_id = _require_owner(x_owner_id)
    existing = await storage.get_character(character_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(existing, owner_id, x_role)
    ok = await storage.soft_delete_character(character_id)
    return {"success": ok}


@router.post("/{character_id}/restore")
async def restore_character(
    character_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    owner_id = _require_owner(x_owner_id)
    existing = await storage.get_character(character_id, include_deleted=True)
    if existing is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(existing, owner_id, x_role)
    ok = await storage.restore_character(character_id)
    return {"success": ok}


# ============================================================
#  导入导出
# ============================================================

@router.get("/{character_id}/export")
async def export_character(character_id: str):
    text = await storage.export_character_json(character_id)
    if text is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"character_id": character_id, "data": text}


@router.post("/import", response_model=CharacterSheet)
async def import_character(
    req: ImportRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
):
    owner_id = _require_owner(x_owner_id)
    override = owner_id if req.copy_as_new else None
    try:
        return await storage.import_character_json(req.data, owner_id_override=override)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"导入失败: {e}")


# ============================================================
#  升级 (Level-Up)
# ============================================================

class LevelUpRequest(BaseModel):
    class_name: str = Field(..., description="升级的职业名，如 'Fighter'")
    hp_method: Literal["average", "roll"] = "average"
    asi_choice: dict[str, int] | None = Field(
        None,
        description="属性值提升，如 {'strength': 2} 或 {'strength': 1, 'dexterity': 1}（总+2）",
    )
    subclass: str | None = Field(None, description="本次升级选择的子职业（如适用）")
    update_spell_slots: bool = Field(True, description="是否自动按升级后等级重算法术位")


@router.post("/{character_id}/level-up", response_model=CharacterSheet)
async def api_level_up(
    character_id: str,
    req: LevelUpRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    为角色升级（+1 等级）。

    - 使用 average 或 roll 方式增加 HP
    - 4/8/12/16/19 级可通过 asi_choice 提升属性（总量 +2）
    - 自动更新施法者的法术位
    """
    from .builder import apply_class, finalize
    from .calculator import ability_modifier, max_hp_by_formula
    import random

    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)

    # ---- 多职业前置条件校验（PHB 2024）----
    existing_classes = [c.class_name for c in sheet.class_levels]
    from .multiclass_rules import validate_multiclass
    ok, reason = validate_multiclass(sheet.ability_scores, existing_classes, req.class_name)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # 应用 ASI（属性值提升）
    new_features: list[str] = []
    if req.asi_choice:
        total_bonus = sum(req.asi_choice.values())
        if total_bonus != 2:
            raise HTTPException(status_code=400, detail="ASI 总提升必须恰好为 +2")
        for attr, val in req.asi_choice.items():
            if not hasattr(sheet.ability_scores, attr):
                raise HTTPException(status_code=400, detail=f"未知属性: {attr}")
            current = getattr(sheet.ability_scores, attr)
            setattr(sheet.ability_scores, attr, min(20, current + val))
        new_features.append(f"ASI: {req.asi_choice}")

    # 升级职业
    old_level = sheet.get_class_level(req.class_name)
    apply_class(sheet, req.class_name, level=1, subclass=req.subclass or "")
    new_level = old_level + 1

    # 增加 HP
    con_mod = ability_modifier(sheet.ability_scores.constitution)
    hit_die = next(
        (c.hit_die_size for c in sheet.class_levels if c.class_name.lower() == req.class_name.lower()),
        8,
    )
    if req.hp_method == "roll":
        hp_gain = random.randint(1, hit_die) + con_mod
    else:
        hp_gain = hit_die // 2 + 1 + con_mod
    hp_gain = max(1, hp_gain)
    sheet.hit_points.maximum += hp_gain
    sheet.hit_points.current = min(sheet.hit_points.current + hp_gain, sheet.hit_points.maximum)
    sheet.hit_points.hit_dice_total = sheet.total_level

    # 更新法术位
    if req.update_spell_slots:
        class_level_pairs = [(c.class_name, c.level) for c in sheet.class_levels]
        merged = merge_multiclass_spell_slots(class_level_pairs)
        # 仅当合并后法术位更多时才更新（保留已花费的）
        for lvl, new_slot in merged.slots.items():
            existing = sheet.spell_slots.slots.get(lvl)
            if existing is None:
                sheet.spell_slots.slots[lvl] = new_slot
                new_features.append(f"解锁 {lvl} 级法术位")
            else:
                if new_slot.maximum > existing.maximum:
                    gained = new_slot.maximum - existing.maximum
                    existing.maximum = new_slot.maximum
                    existing.current = min(existing.current + gained, existing.maximum)
        if merged.pact_slots.maximum > sheet.spell_slots.pact_slots.maximum:
            sheet.spell_slots.pact_slots.maximum = merged.pact_slots.maximum
            sheet.spell_slots.pact_level = merged.pact_level

    # 更新 AC 缓存
    sheet.armor_class_cache = compute_ac(sheet)

    saved = await storage.save_character(sheet)
    return saved


# ============================================================
#  洗点 (Respec)
# ============================================================

class RespecRequest(BaseModel):
    keep_species: bool = True
    keep_background: bool = True
    dm_approval_required: bool = True


@router.post("/{character_id}/respec", response_model=CharacterSheet)
async def api_respec(
    character_id: str,
    req: RespecRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    洗点：重置职业/属性/技能，保留 identity 字段。
    默认需要 DM 重新审批（dm_approved → False）。
    """
    from .models import (
        AbilityScores, HitPoints, SkillProficiencies,
        SavingThrowProficiencies, SpellSlots, ClassLevel,
    )

    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)

    # 重置职业、属性、熟练
    sheet.class_levels = []
    sheet.ability_scores = AbilityScores()
    sheet.skills = SkillProficiencies()
    sheet.saving_throws = SavingThrowProficiencies()
    sheet.weapon_proficiencies = []
    sheet.armor_proficiencies = []
    sheet.tool_proficiencies = []
    sheet.hit_points = HitPoints()
    sheet.spell_slots = SpellSlots()
    sheet.class_resources = []
    sheet.spells_known = []
    sheet.cantrips_known = []
    sheet.active_effects = []
    sheet.conditions = []
    sheet.concentration_effect_id = ""
    sheet.general_feats = []
    sheet.fighting_style_feats = []
    sheet.epic_boon = ""
    sheet.weapon_masteries_learned = []
    sheet.is_polymorphed = False
    sheet.polymorph_snapshot = None
    sheet.polymorph_monster_id = ""

    if not req.keep_species:
        from .models import Species
        sheet.species = Species()
    if not req.keep_background:
        from .models import Background
        sheet.background = Background()
        sheet.origin_feat = ""
        sheet.languages = []

    if req.dm_approval_required:
        sheet.dm_approved = False
        sheet.dm_approval_note = "洗点后等待 DM 重新审批"
        sheet.non_standard = True

    saved = await storage.save_character(sheet)
    return saved


# ============================================================
#  临时效果 (Apply Effect)
# ============================================================

@router.post("/{character_id}/apply-effect", response_model=CharacterSheet)
async def api_apply_effect(
    character_id: str,
    effect: ActiveEffect,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    为角色添加一个 ActiveEffect（神明赐福/神圣庇护/武器附魔等）。
    如果效果是集中法术，会自动解除当前的集中。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = apply_effect(sheet, effect)
    sheet.armor_class_cache = compute_ac(sheet)
    return await storage.save_character(sheet)


@router.delete("/{character_id}/effects/{effect_id}", response_model=CharacterSheet)
async def api_remove_effect(
    character_id: str,
    effect_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """移除指定效果（DM 或角色本人均可操作）"""
    from .effects_engine import remove_effect as _remove_effect
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = _remove_effect(sheet, effect_id)
    sheet.armor_class_cache = compute_ac(sheet)
    return await storage.save_character(sheet)


# ============================================================
#  变形术 / 许愿术
# ============================================================

class PolymorphRequest(BaseModel):
    monster_id: str = Field(..., description="目标怪物 ID")


@router.post("/{character_id}/polymorph", response_model=CharacterSheet)
async def api_polymorph(
    character_id: str,
    req: PolymorphRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 对角色施加变形术"""
    _require_dm(x_role)
    from monster.storage import get_monster
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    monster = await get_monster(req.monster_id)
    if monster is None:
        raise HTTPException(status_code=404, detail=f"怪物 {req.monster_id} 不存在")

    sheet = apply_polymorph(sheet, monster)
    return await storage.save_character(sheet)


@router.post("/{character_id}/polymorph/revert", response_model=CharacterSheet)
async def api_revert_polymorph(
    character_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """解除变形，恢复原始角色数据"""
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    if not sheet.is_polymorphed:
        raise HTTPException(status_code=400, detail="角色当前未处于变形状态")
    sheet = remove_polymorph(sheet)
    return await storage.save_character(sheet)


class WishRequest(BaseModel):
    changes: dict = Field(
        ...,
        description=(
            "永久性修改内容，支持键: ability_scores / languages / "
            "weapon_proficiencies / skills"
        ),
        examples=[{"ability_scores": {"strength": 20}, "languages": ["Celestial"]}],
    )


@router.post("/{character_id}/wish", response_model=CharacterSheet)
async def api_wish(
    character_id: str,
    req: WishRequest,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM 使用许愿术对角色进行永久性属性修改"""
    _require_dm(x_role)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    sheet = apply_wish_permanent(sheet, req.changes)
    sheet.armor_class_cache = compute_ac(sheet)
    return await storage.save_character(sheet)


# ============================================================
#  休息 (Rest)
# ============================================================

class ShortRestRequest(BaseModel):
    hit_dice: list[str] = Field(
        default_factory=list,
        description="要花费的生命骰列表，如 ['d8', 'd8']",
    )
    dm_override: bool = Field(False, description="DM 强制允许（跳过安全地点校验）")


class LongRestRequest(BaseModel):
    dm_override: bool = Field(False, description="DM 强制允许（跳过安全地点校验）")


class RestResponse(BaseModel):
    sheet: CharacterSheet
    result: RestResult


@router.post("/{character_id}/short-rest", response_model=RestResponse)
async def api_short_rest(
    character_id: str,
    req: ShortRestRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    短休：花费生命骰回复 HP，刷新短休资源（Warlock 法术位、Ki 等）。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    updated, result = await short_rest(sheet, req.hit_dice)
    saved = await storage.save_character(updated)
    # 广播 REST_COMPLETE（若 WS 钩子已注入）
    if _rest_broadcast_hook and saved.campaign_id:
        import asyncio
        asyncio.create_task(
            _rest_broadcast_hook(saved.campaign_id, saved.id, owner_id, "short", result)
        )
    return RestResponse(sheet=saved, result=result)


@router.post("/{character_id}/long-rest", response_model=RestResponse)
async def api_long_rest(
    character_id: str,
    req: LongRestRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    长休：全回 HP 和法术位，刷新所有职业资源，恢复生命骰，减少耗竭。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    updated, result = await long_rest(sheet)
    saved = await storage.save_character(updated)
    # 广播 REST_COMPLETE
    if _rest_broadcast_hook and saved.campaign_id:
        import asyncio
        asyncio.create_task(
            _rest_broadcast_hook(saved.campaign_id, saved.id, owner_id, "long", result)
        )
    return RestResponse(sheet=saved, result=result)


# ============================================================
#  背包 (Inventory)
# ============================================================

class ItemPatch(BaseModel):
    """PATCH 背包时允许修改的字段（全部可选）"""
    quantity: int | None = None
    equipped: bool | None = None
    attuned: bool | None = None
    notes: str | None = None


class CurrencyDelta(BaseModel):
    gold: float = 0.0
    silver: float = 0.0
    copper: float = 0.0
    platinum: float = 0.0
    electrum: float = 0.0


@router.post("/{character_id}/inventory", response_model=CharacterSheet)
async def api_add_item(
    character_id: str,
    item: Item,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """添加物品到背包（返回更新后的角色表；若超重会附带 warning 但不阻止）"""
    from .calculator import carry_capacity, current_load
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)
    sheet.inventory.append(item)

    # 超重仅警告，不阻止
    if current_load(sheet) > carry_capacity(sheet):
        # 将超重信息附在响应 header（前端可选读）
        pass

    return await storage.save_character(sheet)


@router.delete("/{character_id}/inventory/{item_id}", response_model=CharacterSheet)
async def api_remove_item(
    character_id: str,
    item_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """从背包移除物品"""
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)
    before_len = len(sheet.inventory)
    sheet.inventory = [i for i in sheet.inventory if i.id != item_id]
    if len(sheet.inventory) == before_len:
        raise HTTPException(status_code=404, detail=f"物品 {item_id} 不在背包中")

    return await storage.save_character(sheet)


@router.patch("/{character_id}/inventory/{item_id}", response_model=CharacterSheet)
async def api_patch_item(
    character_id: str,
    item_id: str,
    patch: ItemPatch,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """修改背包物品属性（装备/卸下/协调/数量）"""
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)
    target = next((i for i in sheet.inventory if i.id == item_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"物品 {item_id} 不在背包中")

    if patch.quantity is not None:
        if patch.quantity <= 0:
            sheet.inventory = [i for i in sheet.inventory if i.id != item_id]
        else:
            target.quantity = patch.quantity
    if patch.equipped is not None:
        target.equipped = patch.equipped
    if patch.attuned is not None:
        if patch.attuned and not target.requires_attunement:
            raise HTTPException(status_code=400, detail="此物品不需要协调")
        target.attuned = patch.attuned
    if patch.notes is not None:
        target.notes = patch.notes

    # 装备状态改变后重算 AC
    sheet.armor_class_cache = compute_ac(sheet)
    return await storage.save_character(sheet)


@router.post("/{character_id}/currency", response_model=CharacterSheet)
async def api_update_currency(
    character_id: str,
    delta: CurrencyDelta,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """货币变化（正数增加，负数减少）。余额不足时返回 400。"""
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)

    new_vals = {
        "gold":     sheet.gold     + delta.gold,
        "silver":   sheet.silver   + delta.silver,
        "copper":   sheet.copper   + delta.copper,
        "platinum": sheet.platinum + delta.platinum,
        "electrum": sheet.electrum + delta.electrum,
    }
    negatives = [k for k, v in new_vals.items() if v < 0]
    if negatives:
        raise HTTPException(
            status_code=400,
            detail=f"货币余额不足: {', '.join(negatives)}",
        )

    for k, v in new_vals.items():
        setattr(sheet, k, v)

    return await storage.save_character(sheet)


# ============================================================
#  HP 直接修改 (治疗 / 伤害 / 临时 HP)
# ============================================================

class HpDeltaRequest(BaseModel):
    """
    HP 变化请求（正数=治疗，负数=伤害）。
    也可以直接设置 current / temporary 为绝对值。
    优先级：delta > set_current（二者只填一个）。
    """
    delta: int | None = Field(
        None,
        description="HP 变化量（正=治疗，负=伤害）。自动处理临时 HP 抵消。",
    )
    set_current: int | None = Field(None, ge=0, description="直接设置当前 HP（绝对值）")
    set_temporary: int | None = Field(None, ge=0, description="直接设置临时 HP")
    clear_death_saves: bool = Field(False, description="True=重置死亡豁免计数（复活/稳定后使用）")


@router.patch("/{character_id}/hp", response_model=CharacterSheet)
async def api_patch_hp(
    character_id: str,
    req: HpDeltaRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    直接修改角色 HP（REST 方式，不经过 WS）。

    - `delta > 0`：治疗（不超过最大 HP）
    - `delta < 0`：伤害（先扣临时 HP，超出部分扣当前 HP，最低为 0）
    - `set_current`：直接设定当前 HP
    - `set_temporary`：设定临时 HP（不叠加，取较大值）
    - `clear_death_saves`：复活/稳定后重置死亡豁免计数
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)
    hp = sheet.hit_points

    if req.delta is not None:
        if req.delta < 0:
            # 伤害：先吸收临时 HP
            damage = abs(req.delta)
            if hp.temporary > 0:
                absorbed = min(hp.temporary, damage)
                hp.temporary -= absorbed
                damage -= absorbed
            hp.current = max(0, hp.current - damage)
        else:
            # 治疗：恢复 HP（不超上限），同时清零死亡豁免
            hp.current = min(hp.maximum, hp.current + req.delta)
            if req.delta > 0 and hp.current > 0:
                hp.death_saves = hp.death_saves.model_copy(
                    update={"successes": 0, "failures": 0, "stable": False}
                )
    elif req.set_current is not None:
        hp.current = min(hp.maximum, req.set_current)

    if req.set_temporary is not None:
        # 临时 HP 不叠加：取较大值（PHB 2024 规则）
        hp.temporary = max(hp.temporary, req.set_temporary)

    if req.clear_death_saves:
        from .models import DeathSaves
        hp.death_saves = DeathSaves()

    return await storage.save_character(sheet)


# ============================================================
#  状态异常 REST 端点（非 WS 场景使用）
# ============================================================

class ConditionPatchRequest(BaseModel):
    action: str = Field(..., description="'add' | 'remove' | 'set'")
    conditions: list[str] = Field(
        ...,
        description="条件列表，如 ['blinded', 'poisoned']。action='set' 时替换全部。",
    )


@router.patch("/{character_id}/conditions", response_model=CharacterSheet)
async def api_patch_conditions(
    character_id: str,
    req: ConditionPatchRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    通过 REST 为角色添加 / 移除 / 替换状态异常。

    - `action=add`：向列表追加（去重）
    - `action=remove`：从列表中移除
    - `action=set`：用传入列表完全替换当前状态（可传空列表清除全部）
    """
    from .models import Condition

    _require_owner(x_owner_id)  # DM 或本人均可
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, x_owner_id, x_role)

    # 校验条件名
    valid_vals = {c.value for c in Condition}
    invalid = [c for c in req.conditions if c not in valid_vals]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的状态条件: {invalid}。合法值: {sorted(valid_vals)}",
        )

    cond_objs = [Condition(c) for c in req.conditions]
    current = list(sheet.conditions)

    if req.action == "add":
        for c in cond_objs:
            if c not in current:
                current.append(c)
    elif req.action == "remove":
        current = [c for c in current if c not in cond_objs]
    elif req.action == "set":
        current = cond_objs
    else:
        raise HTTPException(status_code=400, detail=f"无效 action: {req.action!r}（应为 add/remove/set）")

    sheet = sheet.model_copy(update={"conditions": current})
    return await storage.save_character(sheet)


# ============================================================
#  耗竭等级（Exhaustion）— PHB 2024 为 10 级
# ============================================================

class ExhaustionRequest(BaseModel):
    delta: int = Field(
        ...,
        description="耗竭变化量（+1 增加一级，-1 减少一级）",
    )


@router.patch("/{character_id}/exhaustion", response_model=CharacterSheet)
async def api_patch_exhaustion(
    character_id: str,
    req: ExhaustionRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    修改角色耗竭等级（PHB 2024 共 10 级）。

    - 上限为 10（第 10 级：死亡）
    - 下限为 0（无耗竭）
    - 长休后减少 1 级（由 long-rest 端点处理，此端点供 DM 直接调整）
    """
    _EXHAUSTION_MAX = 10
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    new_level = max(0, min(_EXHAUSTION_MAX, sheet.exhaustion_level + req.delta))
    sheet = sheet.model_copy(update={"exhaustion_level": new_level})
    return await storage.save_character(sheet)


# ============================================================
#  版本历史 (E3)
# ============================================================

class HistoryEntry(BaseModel):
    history_id: int
    version: int
    changed_at: str
    snapshot: CharacterSheet


@router.get("/{character_id}/history", response_model=list[HistoryEntry])
async def api_get_history(
    character_id: str,
    limit: int = Query(20, ge=1, le=100),
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    获取角色版本历史（最近 N 版，倒序）。
    角色本人或 DM 可查看。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    entries = await storage.get_character_history(character_id, limit=limit)
    return [HistoryEntry(**e) for e in entries]


@router.post("/{character_id}/history/{history_id}/restore", response_model=CharacterSheet)
async def api_restore_version(
    character_id: str,
    history_id: int,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    将角色回滚到指定历史版本。
    当前状态会作为一个新历史快照保留，回滚后版本号自增。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    restored = await storage.restore_character_version(character_id, history_id)
    if restored is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    return restored


# ============================================================
#  法术准备管理
# ============================================================

# 需要"每日准备"的职业（PHB 2024）
# 可准备法术数 = 对应能力修正 + 职业等级（祭司:WIS, 德鲁伊:WIS, 圣武士:CHA, 法师:INT）
_PREPARED_CASTER_ABILITY: dict[str, str] = {
    "cleric":  "wisdom",
    "druid":   "wisdom",
    "paladin": "charisma",
    "wizard":  "intelligence",
    # 部分子职业也是准备施法者，但在此只处理基础职业
}


def _max_prepared(sheet: CharacterSheet, class_name: str) -> int:
    """计算该角色当前职业下可准备的最大法术数"""
    ability_key = _PREPARED_CASTER_ABILITY.get(class_name.lower(), "intelligence")
    level = next(
        (cl.level for cl in sheet.class_levels if cl.class_name.lower() == class_name.lower()),
        1,
    )
    mod = sheet.ability_scores.modifier(ability_key)
    return max(1, level + mod)


class PrepareSpellRequest(BaseModel):
    spell_name: str
    class_name: str = ""     # 多职业时指定来源职业；单职业可省略


class UnprepareSpellRequest(BaseModel):
    spell_name: str
    class_name: str = ""


@router.post("/{character_id}/spells/prepare", response_model=CharacterSheet)
async def api_prepare_spell(
    character_id: str,
    body: PrepareSpellRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    将一个已知法术标记为"已准备"。
    仅限需要准备施法的职业（祭司/德鲁伊/圣武士/法师）。
    超出准备上限时返回 400。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    # 确认职业是准备施法者
    class_name = body.class_name or (
        sheet.class_levels[0].class_name if sheet.class_levels else ""
    )
    if class_name.lower() not in _PREPARED_CASTER_ABILITY:
        raise HTTPException(
            status_code=400,
            detail=f"职业 '{class_name}' 不是需要准备法术的施法者",
        )

    # 找到目标法术
    spells = list(sheet.spells_known)
    target = next(
        (s for s in spells if s.name.lower() == body.spell_name.lower()
         and (not body.class_name or s.source_class.lower() == class_name.lower())),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"未找到法术: {body.spell_name}")

    if target.prepared or target.always_prepared:
        raise HTTPException(status_code=400, detail="该法术已经处于准备状态")

    # 检查准备上限（cantrip 不占名额）
    if target.level > 0:
        current_prepared = sum(
            1 for s in spells
            if s.prepared and not s.always_prepared and s.level > 0
            and (not class_name or s.source_class.lower() == class_name.lower())
        )
        max_prep = _max_prepared(sheet, class_name)
        if current_prepared >= max_prep:
            raise HTTPException(
                status_code=400,
                detail=f"已达准备上限 {max_prep}（{class_name} Lv{sheet.total_level}）",
            )

    # 标记已准备
    idx = spells.index(target)
    spells[idx] = target.model_copy(update={"prepared": True})
    sheet = sheet.model_copy(update={"spells_known": spells})
    return await storage.save_character(sheet)


@router.delete("/{character_id}/spells/prepare", response_model=CharacterSheet)
async def api_unprepare_spell(
    character_id: str,
    body: UnprepareSpellRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    取消法术准备状态（always_prepared 的法术不可取消）。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    spells = list(sheet.spells_known)
    class_name = body.class_name or ""
    target = next(
        (s for s in spells if s.name.lower() == body.spell_name.lower()
         and (not class_name or s.source_class.lower() == class_name.lower())),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"未找到法术: {body.spell_name}")
    if target.always_prepared:
        raise HTTPException(status_code=400, detail="域法术/誓约法术不可取消准备")
    if not target.prepared:
        raise HTTPException(status_code=400, detail="该法术尚未准备")

    idx = spells.index(target)
    spells[idx] = target.model_copy(update={"prepared": False})
    sheet = sheet.model_copy(update={"spells_known": spells})
    return await storage.save_character(sheet)


@router.get("/{character_id}/spells/prepare")
async def api_get_prepared_spells(
    character_id: str,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    查看已准备的法术列表及准备上限信息。
    """
    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    prepared = [s for s in sheet.spells_known if s.prepared or s.always_prepared]
    # 按职业分组计算上限
    limits = {}
    for cl in sheet.class_levels:
        cn = cl.class_name.lower()
        if cn in _PREPARED_CASTER_ABILITY:
            limits[cl.class_name] = {
                "max": _max_prepared(sheet, cn),
                "used": sum(
                    1 for s in sheet.spells_known
                    if s.prepared and not s.always_prepared and s.level > 0
                    and s.source_class.lower() == cn
                ),
            }

    return {
        "prepared_spells": [s.model_dump() for s in prepared],
        "preparation_limits": limits,
    }


# ============================================================
#  经验值 (XP)
# ============================================================

class XpGrantRequest(BaseModel):
    xp_amount: int = Field(..., ge=0, description="授予的经验值（≥0）")
    note: str = Field("", description="来源备注，如「击败骷髅王」")


@router.post("/{character_id}/xp")
async def api_grant_xp(
    character_id: str,
    req: XpGrantRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    为角色增加经验值。

    - 自动计算是否触发升级
    - 更新 `xp_total` 和 `xp_to_next_level` 缓存字段
    - 若角色在战役中且满足升级条件，通过 WS 广播 `xp_gain` 消息提示升级
    - 升级动作本身需另行调用 `POST /level-up`（玩家手动确认）
    """
    from .xp_system import apply_xp

    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    result = apply_xp(character_id, sheet.xp_total, req.xp_amount)
    sheet = sheet.model_copy(update={
        "xp_total": result.xp_after,
        "xp_to_next_level": result.xp_to_next,
    })
    saved = await storage.save_character(sheet)

    # 广播 XP 增加结果
    if _xp_broadcast_hook and saved.campaign_id:
        import asyncio
        asyncio.create_task(
            _xp_broadcast_hook(
                saved.campaign_id,
                saved.owner_id,
                saved.name,
                saved.id,
                result,
                req.note,
            )
        )

    return {
        "sheet": saved.model_dump(),
        "xp_result": result.model_dump(),
    }


# ============================================================
#  施法（消耗法术位）
# ============================================================

class CastSpellRequest(BaseModel):
    spell_name: str = Field("", description="法术名（记录用，可省略）")
    slot_level: int = Field(..., ge=1, le=9, description="消耗的法术位等级")
    is_pact_slot: bool = Field(False, description="True=消耗誓约法术位（Warlock）")
    requires_concentration: bool = Field(
        False,
        description="True=此法术需要集中；自动解除旧集中效果",
    )
    concentration_effect_id: str = Field(
        "",
        description="新集中效果的 ActiveEffect id（若已通过 /apply-effect 添加）",
    )


@router.post("/{character_id}/cast-spell", response_model=CharacterSheet)
async def api_cast_spell(
    character_id: str,
    req: CastSpellRequest,
    x_owner_id: str | None = Header(None, alias="X-Owner-Id"),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    消耗一个法术位（法术施放入口）。

    - 消耗 `slot_level` 级法术位（或 Warlock 誓约法术位）
    - 若 `requires_concentration=True`，自动解除角色当前持有的集中效果
    - 若指定了 `concentration_effect_id`，将其设置为当前集中目标
    - 不验证角色是否真的会这个法术（验证由客户端或前置步骤负责）
    """
    from .effects_engine import remove_effect as _remove_effect

    owner_id = _require_owner(x_owner_id)
    sheet = await storage.get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _check_ownership_or_dm(sheet, owner_id, x_role)

    sheet = sheet.model_copy(deep=True)

    # --- 消耗法术位 ---
    if req.is_pact_slot:
        pact = sheet.spell_slots.pact_slots
        if pact.current <= 0:
            raise HTTPException(status_code=400, detail="誓约法术位已全部耗尽")
        pact.current -= 1
    else:
        slot_key = req.slot_level
        slot = sheet.spell_slots.slots.get(slot_key)
        if slot is None:
            raise HTTPException(
                status_code=400,
                detail=f"角色没有 {req.slot_level} 级法术位（未解锁）",
            )
        if slot.current <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"{req.slot_level} 级法术位已全部耗尽（已用 {slot.maximum}/{slot.maximum}）",
            )
        slot.current -= 1

    # --- 集中处理 ---
    if req.requires_concentration:
        if sheet.concentration_effect_id:
            # 解除旧集中
            sheet = _remove_effect(sheet, sheet.concentration_effect_id)
        # 设置新集中目标（若已提前通过 apply-effect 添加）
        if req.concentration_effect_id:
            sheet = sheet.model_copy(
                update={"concentration_effect_id": req.concentration_effect_id}
            )

    # 重算 AC（部分效果影响 AC）
    sheet.armor_class_cache = compute_ac(sheet)
    return await storage.save_character(sheet)


# ============================================================
#  遭遇难度计算器（无副作用，纯计算）
# ============================================================

from .encounter_difficulty import (  # noqa: E402
    EncounterDifficultyRequest,
    EncounterDifficultyResult,
    calculate_encounter_difficulty,
)


@router.post("/encounter-difficulty", response_model=EncounterDifficultyResult)
async def api_encounter_difficulty(req: EncounterDifficultyRequest):
    """
    计算遭遇战难度评级（纯计算，无副作用，无需身份验证）。

    - 输入：队伍各角色等级列表 + 怪物 CR 列表
    - 输出：难度等级（trivial/easy/medium/hard/deadly）+ XP 阈值 + 遭遇倍率 + 调整建议
    """
    return calculate_encounter_difficulty(req)
