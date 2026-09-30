"""
游戏场次持久化
支持 SQLite 和 MySQL 双后端（通过 db_helper）
"""
from __future__ import annotations

import json
from datetime import datetime

from db_helper import async_conn, IS_MYSQL, PH

from .models import GameSession, SessionOpLog


async def init_session_db() -> None:
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS game_sessions (
                    id              VARCHAR(255) PRIMARY KEY,
                    campaign_id     VARCHAR(255) NOT NULL,
                    round_number    INT DEFAULT 0,
                    current_turn_index INT DEFAULT 0,
                    initiative_json MEDIUMTEXT DEFAULT '[]',
                    scene_json      MEDIUMTEXT,
                    active_encounter_map_id VARCHAR(255) DEFAULT '',
                    started_at      VARCHAR(50),
                    last_active_at  VARCHAR(50),
                    INDEX idx_sess_campaign (campaign_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS session_op_log (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    session_id  VARCHAR(255) NOT NULL,
                    op_type     VARCHAR(100) NOT NULL,
                    actor_id    VARCHAR(255) DEFAULT '',
                    payload     MEDIUMTEXT DEFAULT '{}',
                    round_number INT DEFAULT 0,
                    ts          VARCHAR(50),
                    INDEX idx_oplog_session (session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS game_sessions (
                    id              TEXT PRIMARY KEY,
                    campaign_id     TEXT NOT NULL,
                    round_number    INTEGER DEFAULT 0,
                    current_turn_index INTEGER DEFAULT 0,
                    initiative_json TEXT DEFAULT '[]',
                    scene_json      TEXT,
                    started_at      TEXT,
                    last_active_at  TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sess_campaign ON game_sessions(campaign_id)"
            )
            # 向后兼容：旧库无此列时自动添加
            try:
                await conn.execute(
                    "ALTER TABLE game_sessions ADD COLUMN active_encounter_map_id TEXT DEFAULT ''"
                )
                await conn.commit()
            except Exception:
                pass  # 列已存在，忽略

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS session_op_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    op_type     TEXT NOT NULL,
                    actor_id    TEXT DEFAULT '',
                    payload     TEXT DEFAULT '{}',
                    round_number INTEGER DEFAULT 0,
                    ts          TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oplog_session ON session_op_log(session_id)"
            )
        await conn.commit()


async def save_session(session: GameSession) -> GameSession:
    session = session.model_copy(deep=True)
    session.last_active_at = datetime.now().isoformat(timespec="seconds")

    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO game_sessions
            (id, campaign_id, round_number, current_turn_index,
             initiative_json, scene_json, active_encounter_map_id,
             started_at, last_active_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            session.id,
            session.campaign_id,
            session.round_number,
            session.current_turn_index,
            json.dumps([e.model_dump() for e in session.initiative]),
            session.scene.model_dump_json() if session.scene else None,
            session.active_encounter_map_id,
            session.started_at,
            session.last_active_at,
        ))
        await conn.commit()
    return session


async def get_session(session_id: str) -> GameSession | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM game_sessions WHERE id = {PH}", (session_id,)
        )
        row = await cur.fetchone()
        return _row_to_session(row) if row else None


async def get_latest_session(campaign_id: str) -> GameSession | None:
    """返回该战役最近一次更新的场次快照"""
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM game_sessions WHERE campaign_id = {PH} "
            f"ORDER BY last_active_at DESC LIMIT 1",
            (campaign_id,),
        )
        row = await cur.fetchone()
        return _row_to_session(row) if row else None


async def append_op_log(log: SessionOpLog) -> None:
    """Fire-and-forget 写入操作日志"""
    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT INTO session_op_log
            (session_id, op_type, actor_id, payload, round_number, ts)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            log.session_id,
            log.op_type,
            log.actor_id,
            json.dumps(log.payload),
            log.round_number,
            log.ts,
        ))
        await conn.commit()


async def get_op_log(session_id: str, limit: int = 50) -> list[SessionOpLog]:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM session_op_log WHERE session_id = {PH} "
            f"ORDER BY id DESC LIMIT {PH}",
            (session_id, limit),
        )
        rows = await cur.fetchall()
        return [_row_to_oplog(r) for r in rows]


def _row_to_session(row: dict) -> GameSession:
    from .models import InitiativeEntry, SceneData
    initiative_raw = json.loads(row["initiative_json"] or "[]")
    scene_raw = row["scene_json"]

    return GameSession(
        id=row["id"],
        campaign_id=row["campaign_id"],
        round_number=row["round_number"] or 0,
        current_turn_index=row["current_turn_index"] or 0,
        initiative=[InitiativeEntry(**e) for e in initiative_raw],
        scene=SceneData.model_validate_json(scene_raw) if scene_raw else None,
        active_encounter_map_id=row.get("active_encounter_map_id") or "",
        started_at=row["started_at"] or "",
        last_active_at=row["last_active_at"] or "",
    )


def _row_to_oplog(row: dict) -> SessionOpLog:
    return SessionOpLog(
        id=row["id"],
        session_id=row["session_id"],
        op_type=row["op_type"],
        actor_id=row["actor_id"] or "",
        payload=json.loads(row["payload"] or "{}"),
        round_number=row["round_number"] or 0,
        ts=row["ts"] or "",
    )
