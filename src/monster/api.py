"""
怪物系统 FastAPI 路由
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from monster.models import Monster, MonsterSummary, MonsterListResponse
from monster.storage import (
    save_monster, get_monster, get_monster_by_name,
    list_monsters, search_monsters, delete_monster, count_monsters,
)

router = APIRouter(prefix="/api/monsters", tags=["monsters"])


@router.get("", response_model=MonsterListResponse)
async def api_list_monsters(
    creature_type: str | None = Query(None, description="按生物类型筛选，如'亡灵'"),
    cr: str | None = Query(None, description="按 CR 筛选，如'5'"),
    source: str | None = Query(None, description="按来源筛选"),
    q: str | None = Query(None, description="搜索关键词（支持中文名/英文名/生物类型）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出怪物（支持按类型/CR/来源筛选，或关键词搜索）

    返回格式：{"monsters": [...], "total": N, "limit": N, "offset": N}
    """
    if q:
        monsters = await search_monsters(q, limit=limit)
        return MonsterListResponse(monsters=monsters, total=len(monsters), limit=limit, offset=0)
    monsters = await list_monsters(
        creature_type=creature_type, cr=cr,
        source=source, limit=limit, offset=offset,
    )
    total = await count_monsters()
    return MonsterListResponse(monsters=monsters, total=total, limit=limit, offset=offset)


@router.get("/count")
async def api_count_monsters():
    return {"count": await count_monsters()}


@router.get("/{monster_id}", response_model=Monster)
async def api_get_monster(monster_id: str):
    """按 ID 获取完整怪物数据"""
    m = await get_monster(monster_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"怪物 {monster_id} 不存在")
    return m


@router.get("/by-name/{name}", response_model=Monster)
async def api_get_monster_by_name(name: str):
    """按中文名或英文名精确查找"""
    m = await get_monster_by_name(name)
    if not m:
        raise HTTPException(status_code=404, detail=f"未找到怪物：{name}")
    return m



@router.put("/{monster_id}", response_model=Monster)
async def api_update_monster(monster_id: str, monster: Monster):
    """完整更新怪物数据（DM 手动编辑用）"""
    existing = await get_monster(monster_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"怪物 {monster_id} 不存在")
    monster.id = monster_id
    return await save_monster(monster, overwrite=True)


@router.delete("/{monster_id}")
async def api_delete_monster(monster_id: str):
    ok = await delete_monster(monster_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"怪物 {monster_id} 不存在")
    return {"success": True}
