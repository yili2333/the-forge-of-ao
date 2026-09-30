"""
战役数据持久化
支持 SQLite 和 MySQL 双后端（通过 db_helper）
"""
from __future__ import annotations

import json
from datetime import datetime

from db_helper import async_conn, IS_MYSQL, PH

from .models import Campaign, CampaignInvite


async def init_campaign_db() -> None:
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id          VARCHAR(255) PRIMARY KEY,
                    name        VARCHAR(255) NOT NULL,
                    description TEXT DEFAULT '',
                    dm_owner_id VARCHAR(255) NOT NULL,
                    dm_display  VARCHAR(255) DEFAULT '',
                    status      VARCHAR(50) DEFAULT 'planning',
                    player_ids  TEXT DEFAULT '[]',
                    character_ids TEXT DEFAULT '[]',
                    world_map_id VARCHAR(255) DEFAULT '',
                    session_count INT DEFAULT 0,
                    edition     VARCHAR(50) DEFAULT '2024',
                    tags        TEXT DEFAULT '[]',
                    created_at  VARCHAR(50),
                    updated_at  VARCHAR(50),
                    INDEX idx_campaign_dm (dm_owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaign_invites (
                    code        VARCHAR(50) PRIMARY KEY,
                    campaign_id VARCHAR(255) NOT NULL,
                    campaign_name VARCHAR(255) DEFAULT '',
                    dm_display  VARCHAR(255) DEFAULT '',
                    max_uses    INT DEFAULT 10,
                    uses        INT DEFAULT 0,
                    expires_at  VARCHAR(50) DEFAULT '',
                    created_at  VARCHAR(50),
                    is_active   TINYINT DEFAULT 1,
                    INDEX idx_invite_camp (campaign_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    dm_owner_id TEXT NOT NULL,
                    dm_display  TEXT DEFAULT '',
                    status      TEXT DEFAULT 'planning',
                    player_ids  TEXT DEFAULT '[]',
                    character_ids TEXT DEFAULT '[]',
                    world_map_id TEXT DEFAULT '',
                    session_count INTEGER DEFAULT 0,
                    edition     TEXT DEFAULT '2024',
                    tags        TEXT DEFAULT '[]',
                    created_at  TEXT,
                    updated_at  TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaign_dm ON campaigns(dm_owner_id)"
            )

            # 邀请码表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaign_invites (
                    code        TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    campaign_name TEXT DEFAULT '',
                    dm_display  TEXT DEFAULT '',
                    max_uses    INTEGER DEFAULT 10,
                    uses        INTEGER DEFAULT 0,
                    expires_at  TEXT DEFAULT '',
                    created_at  TEXT,
                    is_active   INTEGER DEFAULT 1
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invite_camp ON campaign_invites(campaign_id)"
            )
        await conn.commit()


async def save_campaign(camp: Campaign) -> Campaign:
    now = datetime.now().isoformat(timespec="seconds")
    camp = camp.model_copy(deep=True)
    if not camp.created_at:
        camp.created_at = now
    camp.updated_at = now

    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO campaigns
            (id, name, description, dm_owner_id, dm_display, status,
             player_ids, character_ids, world_map_id, session_count,
             edition, tags, created_at, updated_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            camp.id, camp.name, camp.description,
            camp.dm_owner_id, camp.dm_display, camp.status.value,
            json.dumps(camp.player_ids), json.dumps(camp.character_ids),
            camp.world_map_id, camp.session_count,
            camp.edition, json.dumps(camp.tags),
            camp.created_at, camp.updated_at,
        ))
        await conn.commit()
    return camp


async def get_campaign(campaign_id: str) -> Campaign | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM campaigns WHERE id = {PH}", (campaign_id,)
        )
        row = await cur.fetchone()
        return _row_to_campaign(row) if row else None


async def list_campaigns_by_dm(dm_owner_id: str) -> list[Campaign]:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM campaigns WHERE dm_owner_id = {PH} ORDER BY updated_at DESC",
            (dm_owner_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_campaign(r) for r in rows]


async def list_campaigns_by_player(owner_id: str) -> list[Campaign]:
    """返回该玩家参与的所有战役（通过 player_ids JSON 列扫描）"""
    async with async_conn() as conn:
        # SQLite 和 MySQL 都支持 LIKE，用 JSON 模糊匹配
        cur = await conn.execute(
            f"SELECT * FROM campaigns WHERE player_ids LIKE {PH} ORDER BY updated_at DESC",
            (f'%"{owner_id}"%',),
        )
        rows = await cur.fetchall()
        return [_row_to_campaign(r) for r in rows]


async def delete_campaign(campaign_id: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM campaigns WHERE id = {PH}", (campaign_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


def _row_to_campaign(row: dict) -> Campaign:
    return Campaign(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        dm_owner_id=row["dm_owner_id"],
        dm_display=row["dm_display"] or "",
        status=row["status"] or "planning",
        player_ids=json.loads(row["player_ids"] or "[]"),
        character_ids=json.loads(row["character_ids"] or "[]"),
        world_map_id=row["world_map_id"] or "",
        session_count=row["session_count"] or 0,
        edition=row["edition"] or "2024",
        tags=json.loads(row["tags"] or "[]"),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


# ============================================================
#  邀请码 CRUD
# ============================================================

async def create_invite(invite: CampaignInvite) -> CampaignInvite:
    """持久化一个新邀请码"""
    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO campaign_invites
            (code, campaign_id, campaign_name, dm_display, max_uses, uses,
             expires_at, created_at, is_active)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            invite.code,
            invite.campaign_id,
            invite.campaign_name,
            invite.dm_display,
            invite.max_uses,
            invite.uses,
            invite.expires_at,
            invite.created_at,
            1 if invite.is_active else 0,
        ))
        await conn.commit()
    return invite


async def get_invite(code: str) -> CampaignInvite | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM campaign_invites WHERE code = {PH}", (code.upper(),)
        )
        row = await cur.fetchone()
    return _row_to_invite(row) if row else None


async def list_invites(campaign_id: str) -> list[CampaignInvite]:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM campaign_invites WHERE campaign_id = {PH} ORDER BY created_at DESC",
            (campaign_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_invite(r) for r in rows]


async def consume_invite(code: str, player_id: str) -> tuple[CampaignInvite | None, str]:
    """
    消耗一次邀请码，将 player_id 加入对应战役。
    返回 (invite, error_msg)：error_msg 非空表示失败原因。
    """
    from datetime import datetime as _dt

    inv = await get_invite(code)
    if inv is None:
        return None, "邀请码不存在"
    if not inv.is_active:
        return inv, "邀请码已失效"
    if inv.max_uses != -1 and inv.uses >= inv.max_uses:
        return inv, "邀请码已达使用上限"
    if inv.expires_at:
        try:
            exp = _dt.fromisoformat(inv.expires_at)
            if _dt.now() > exp:
                return inv, "邀请码已过期"
        except ValueError:
            pass

    # 把玩家加入战役
    camp = await get_campaign(inv.campaign_id)
    if camp is None:
        return inv, "战役不存在"
    if player_id not in camp.player_ids:
        camp.player_ids.append(player_id)
        await save_campaign(camp)

    # 更新使用次数
    async with async_conn() as conn:
        await conn.execute(
            f"UPDATE campaign_invites SET uses = uses + 1 WHERE code = {PH}",
            (code.upper(),),
        )
        await conn.commit()

    inv.uses += 1
    return inv, ""


async def deactivate_invite(code: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"UPDATE campaign_invites SET is_active = 0 WHERE code = {PH}",
            (code.upper(),),
        )
        await conn.commit()
        return cur.rowcount > 0


def _row_to_invite(row: dict) -> CampaignInvite:
    return CampaignInvite(
        code=row["code"],
        campaign_id=row["campaign_id"],
        campaign_name=row["campaign_name"] or "",
        dm_display=row["dm_display"] or "",
        max_uses=row["max_uses"],
        uses=row["uses"],
        expires_at=row["expires_at"] or "",
        created_at=row["created_at"] or "",
        is_active=bool(row["is_active"]),
    )
