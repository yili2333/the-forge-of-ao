"""
人物卡持久化层

设计要点:
1. 单表存储: characters 表保存 CharacterSheet 的 JSON 序列化
2. 关键元数据 (owner_id / campaign_id / name) 提升为列，用于查询/筛选
3. 支持 SQLite 和 MySQL 双后端（通过 db_helper）
4. 不与现有 rule_chunks 表冲突，共用同一数据库
5. 每次 save 自增 version，并更新 updated_at
6. 删除为软删除: deleted_at 列置时间戳 (避免误删，可恢复)
"""

from __future__ import annotations

import json
from datetime import datetime

from db_helper import async_conn, IS_MYSQL, PH

from .models import CharacterSheet


# ============================================================
#  建表
# ============================================================

async def init_character_db() -> None:
    """创建 characters 及 character_history 表。与 rule_chunks 共存于同一数据库。"""
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id VARCHAR(255) PRIMARY KEY,
                    owner_id VARCHAR(255) NOT NULL,
                    owner_display VARCHAR(255) DEFAULT '',
                    campaign_id VARCHAR(255),
                    name VARCHAR(255) NOT NULL,
                    edition VARCHAR(50) DEFAULT '2024',
                    total_level INT DEFAULT 1,
                    non_standard TINYINT DEFAULT 0,
                    dm_approved TINYINT DEFAULT 0,
                    data_json LONGTEXT NOT NULL,
                    version INT DEFAULT 1,
                    created_at VARCHAR(50),
                    updated_at VARCHAR(50),
                    deleted_at VARCHAR(50),
                    INDEX idx_char_owner (owner_id),
                    INDEX idx_char_campaign (campaign_id),
                    INDEX idx_char_deleted (deleted_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    character_id VARCHAR(255) NOT NULL,
                    version INT NOT NULL,
                    data_json LONGTEXT NOT NULL,
                    changed_at VARCHAR(50) NOT NULL,
                    INDEX idx_hist_char (character_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    owner_display TEXT DEFAULT '',
                    campaign_id TEXT,
                    name TEXT NOT NULL,
                    edition TEXT DEFAULT '2024',
                    total_level INTEGER DEFAULT 1,
                    non_standard INTEGER DEFAULT 0,
                    dm_approved INTEGER DEFAULT 0,
                    data_json TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    deleted_at TEXT
                )
            """)
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_char_owner ON characters(owner_id)",
                "CREATE INDEX IF NOT EXISTS idx_char_campaign ON characters(campaign_id)",
                "CREATE INDEX IF NOT EXISTS idx_char_deleted ON characters(deleted_at)",
            ]:
                await conn.execute(idx_sql)

            # E3: 版本历史表（每次 save 自动快照，保留最近 20 版）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id TEXT NOT NULL,
                    version     INTEGER NOT NULL,
                    data_json   TEXT NOT NULL,
                    changed_at  TEXT NOT NULL
                )
            """)
            try:
                await conn.execute(
                    "CREATE INDEX idx_hist_char ON character_history(character_id)"
                )
            except Exception:
                pass  # 索引已存在

        await conn.commit()


# ============================================================
#  序列化辅助
# ============================================================

def _sheet_to_row(sheet: CharacterSheet) -> tuple:
    """把 CharacterSheet 打包成 INSERT 参数元组"""
    data_json = sheet.model_dump_json()
    return (
        sheet.id,
        sheet.owner_id,
        sheet.owner_display,
        sheet.campaign_id,
        sheet.name,
        sheet.edition,
        sheet.total_level,
        1 if sheet.non_standard else 0,
        1 if sheet.dm_approved else 0,
        data_json,
        sheet.version,
        sheet.created_at,
        sheet.updated_at,
        None,  # deleted_at
    )


def _row_to_sheet(row: dict) -> CharacterSheet:
    """从数据库行恢复 CharacterSheet。以 data_json 为真源。"""
    return CharacterSheet.model_validate_json(row["data_json"])


# ============================================================
#  写操作
# ============================================================

_HISTORY_MAX_VERSIONS = 20  # 每个角色最多保留多少个历史快照


async def save_character(sheet: CharacterSheet) -> CharacterSheet:
    """
    插入或替换一张人物卡。
    语义: 若 id 已存在则 version 自增并更新 updated_at，否则按原值插入。
    每次更新都会向 character_history 写入快照（保留最近 _HISTORY_MAX_VERSIONS 版）。
    """
    now = datetime.now().isoformat(timespec="seconds")
    sheet.updated_at = now
    if not sheet.created_at:
        sheet.created_at = now

    async with async_conn() as conn:
        cursor = await conn.execute(
            f"SELECT version FROM characters WHERE id = {PH}", (sheet.id,)
        )
        row = await cursor.fetchone()
        is_update = row is not None
        if is_update:
            sheet.version = int(row["version"]) + 1

        await conn.execute(f"""
            INSERT OR REPLACE INTO characters (
                id, owner_id, owner_display, campaign_id, name,
                edition, total_level, non_standard, dm_approved,
                data_json, version, created_at, updated_at, deleted_at
            ) VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, _sheet_to_row(sheet))

        # 写版本历史快照（仅更新时，避免初始 version=1 写两次）
        if is_update:
            await conn.execute(
                f"INSERT INTO character_history (character_id, version, data_json, changed_at) "
                f"VALUES ({PH},{PH},{PH},{PH})",
                (sheet.id, sheet.version, sheet.model_dump_json(), now),
            )
            # 超出上限则删除最旧的
            await conn.execute(
                f"""
                DELETE FROM character_history
                WHERE character_id = {PH}
                  AND id NOT IN (
                      SELECT id FROM character_history
                      WHERE character_id = {PH}
                      ORDER BY id DESC
                      LIMIT {PH}
                  )
                """,
                (sheet.id, sheet.id, _HISTORY_MAX_VERSIONS),
            )

        await conn.commit()
    return sheet


async def mark_dm_approval(character_id: str, approved: bool, note: str = "") -> CharacterSheet | None:
    """DM 审批通过/拒绝一张带 non_standard 标记的人物卡。"""
    sheet = await get_character(character_id)
    if sheet is None:
        return None
    sheet.dm_approved = approved
    sheet.dm_approval_note = note
    return await save_character(sheet)


# ============================================================
#  读操作
# ============================================================

async def get_character(character_id: str, include_deleted: bool = False) -> CharacterSheet | None:
    async with async_conn() as conn:
        if include_deleted:
            cursor = await conn.execute(
                f"SELECT * FROM characters WHERE id = {PH}", (character_id,)
            )
        else:
            cursor = await conn.execute(
                f"SELECT * FROM characters WHERE id = {PH} AND deleted_at IS NULL",
                (character_id,),
            )
        row = await cursor.fetchone()
        return _row_to_sheet(row) if row else None


async def list_characters_by_owner(owner_id: str) -> list[CharacterSheet]:
    """列出某玩家的所有未删除角色（跨战役）"""
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"""
            SELECT * FROM characters
            WHERE owner_id = {PH} AND deleted_at IS NULL
            ORDER BY updated_at DESC
            """,
            (owner_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_sheet(r) for r in rows]


async def list_characters_by_campaign(campaign_id: str) -> list[CharacterSheet]:
    """列出某战役下的所有角色"""
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"""
            SELECT * FROM characters
            WHERE campaign_id = {PH} AND deleted_at IS NULL
            ORDER BY name ASC
            """,
            (campaign_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_sheet(r) for r in rows]


async def list_pending_approval(campaign_id: str | None = None) -> list[CharacterSheet]:
    """列出所有等待 DM 审批的非标准人物卡"""
    async with async_conn() as conn:
        if campaign_id:
            cursor = await conn.execute(
                f"""
                SELECT * FROM characters
                WHERE non_standard = 1 AND dm_approved = 0
                      AND campaign_id = {PH} AND deleted_at IS NULL
                ORDER BY updated_at ASC
                """,
                (campaign_id,),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT * FROM characters
                WHERE non_standard = 1 AND dm_approved = 0 AND deleted_at IS NULL
                ORDER BY updated_at ASC
                """,
            )
        rows = await cursor.fetchall()
        return [_row_to_sheet(r) for r in rows]


# ============================================================
#  删除 (软删除 + 硬删除)
# ============================================================

async def soft_delete_character(character_id: str) -> bool:
    """软删除: 置 deleted_at 时间戳，仍可恢复"""
    now = datetime.now().isoformat(timespec="seconds")
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"UPDATE characters SET deleted_at = {PH} WHERE id = {PH} AND deleted_at IS NULL",
            (now, character_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def restore_character(character_id: str) -> bool:
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"UPDATE characters SET deleted_at = NULL WHERE id = {PH}",
            (character_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def hard_delete_character(character_id: str) -> bool:
    """彻底删除。仅用于测试或管理员清理。"""
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"DELETE FROM characters WHERE id = {PH}", (character_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0


# ============================================================
#  版本历史 (E3)
# ============================================================

async def get_character_history(character_id: str, limit: int = 20) -> list[dict]:
    """
    返回角色的版本历史列表（倒序，最新在前）。
    每项含: id, version, changed_at, data_json(str)。
    """
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT id, version, changed_at, data_json FROM character_history "
            f"WHERE character_id = {PH} ORDER BY id DESC LIMIT {PH}",
            (character_id, limit),
        )
        rows = await cur.fetchall()
    return [
        {
            "history_id": r["id"],
            "version": r["version"],
            "changed_at": r["changed_at"],
            "snapshot": CharacterSheet.model_validate_json(r["data_json"]),
        }
        for r in rows
    ]


async def restore_character_version(character_id: str, history_id: int) -> CharacterSheet | None:
    """
    将角色恢复到指定 history_id 的版本（当前版本也会保存历史）。
    返回恢复后保存的新 CharacterSheet，或 None（若 history_id 不存在）。
    """
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT data_json FROM character_history WHERE id = {PH} AND character_id = {PH}",
            (history_id, character_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    sheet = CharacterSheet.model_validate_json(row["data_json"])
    # 保持 id 不变，让 save_character 自动递增 version
    return await save_character(sheet)


# ============================================================
#  导入导出 (JSON)
# ============================================================

async def export_character_json(character_id: str) -> str | None:
    sheet = await get_character(character_id)
    if sheet is None:
        return None
    return sheet.model_dump_json(indent=2)


async def import_character_json(data: str | dict, owner_id_override: str | None = None) -> CharacterSheet:
    """
    从 JSON 导入人物卡。
    若 owner_id_override 给出，则覆盖原 owner_id（用于"从他人处拷贝一份当模板"场景）。
    """
    if isinstance(data, str):
        sheet = CharacterSheet.model_validate_json(data)
    else:
        sheet = CharacterSheet.model_validate(data)

    if owner_id_override:
        sheet.owner_id = owner_id_override
        # 导入视为新卡，分配新 id 避免覆盖原卡
        import uuid
        sheet.id = f"char-{uuid.uuid4().hex[:10]}"
        sheet.version = 1
        sheet.created_at = ""
        sheet.updated_at = ""

    return await save_character(sheet)
