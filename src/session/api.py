"""
游戏场次 FastAPI 路由

GET  /api/campaign/{campaign_id}/sessions            — 列出该战役的所有场次快照
GET  /api/campaign/{campaign_id}/sessions/latest     — 获取最新场次
GET  /api/session/{session_id}                       — 获取单个场次详情
GET  /api/session/{session_id}/log                   — 获取操作日志
DELETE /api/session/{session_id}                     — 删除场次（DM 专属）
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from .models import GameSession, SessionOpLog
from .storage import (
    append_op_log,
    get_latest_session,
    get_op_log,
    get_session,
)

import aiosqlite
from config import get_settings

router = APIRouter(tags=["session"])

_DB_PATH = get_settings().sqlite_path


def _require_dm(x_role: str | None) -> None:
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="此操作需要 DM 权限")


# ===== 战役维度 =====

@router.get("/api/campaign/{campaign_id}/sessions", response_model=list[GameSession])
async def list_sessions(
    campaign_id: str,
    limit: int = Query(20, ge=1, le=100),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 列出战役的所有游戏场次快照（按时间倒序）"""
    _require_dm(x_role)
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM game_sessions WHERE campaign_id = ? "
            "ORDER BY last_active_at DESC LIMIT ?",
            (campaign_id, limit),
        )
        rows = await cur.fetchall()

    from .storage import _row_to_session
    return [_row_to_session(r) for r in rows]


@router.get("/api/campaign/{campaign_id}/sessions/latest", response_model=GameSession)
async def get_latest(campaign_id: str):
    """获取该战役最近一次活跃的场次快照（用于重连恢复）"""
    session = await get_latest_session(campaign_id)
    if session is None:
        raise HTTPException(status_code=404, detail="该战役尚无游戏记录")
    return session


# ===== 单场次维度 =====

@router.get("/api/session/{session_id}", response_model=GameSession)
async def get_session_detail(session_id: str):
    """获取单个游戏场次的完整快照"""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="场次不存在")
    return session


@router.get("/api/session/{session_id}/log", response_model=list[SessionOpLog])
async def get_session_log(
    session_id: str,
    limit: int = Query(50, ge=1, le=500),
    op_type: str | None = Query(None, description="按操作类型过滤，如 roll/hp_change/initiative/rest"),
):
    """获取场次操作日志（倒序，最新在前）"""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="场次不存在")

    logs = await get_op_log(session_id, limit=limit)
    if op_type:
        logs = [l for l in logs if l.op_type == op_type]
    return logs


@router.delete("/api/session/{session_id}")
async def delete_session(
    session_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 删除场次快照及操作日志"""
    _require_dm(x_role)
    async with aiosqlite.connect(_DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT id FROM game_sessions WHERE id = ?", (session_id,)
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="场次不存在")
        await conn.execute("DELETE FROM session_op_log WHERE session_id = ?", (session_id,))
        await conn.execute("DELETE FROM game_sessions WHERE id = ?", (session_id,))
        await conn.commit()
    return {"success": True, "deleted_session_id": session_id}


@router.post("/api/session/{session_id}/log", response_model=SessionOpLog)
async def add_op_log(
    session_id: str,
    log: SessionOpLog,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    DM: 手动追加一条操作日志。
    通常由服务器内部触发，此端点用于测试或离线补录。
    """
    _require_dm(x_role)
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="场次不存在")
    log.session_id = session_id
    await append_op_log(log)
    return log
