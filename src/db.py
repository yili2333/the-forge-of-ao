import json
from models import RuleChunk, RuleCategory, RuleSource
from config import get_settings
from db_helper import async_conn, IS_MYSQL, PH


async def init_db():
    """初始化数据库表（幂等，支持旧库迁移）"""
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rule_chunks (
                    id VARCHAR(255) PRIMARY KEY,
                    title TEXT NOT NULL,
                    content LONGTEXT NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    page INT DEFAULT NULL,
                    parent_context TEXT DEFAULT '',
                    related_rule_ids JSON,
                    keywords JSON,
                    level_requirement INT DEFAULT NULL,
                    campaign_id VARCHAR(255) DEFAULT NULL,
                    priority INT DEFAULT 0,
                    created_at VARCHAR(50),
                    edition VARCHAR(50) DEFAULT 'PHB 2024',
                    status VARCHAR(20) DEFAULT 'active',
                    superseded_by VARCHAR(255) DEFAULT NULL,
                    supersedes VARCHAR(255) DEFAULT NULL,
                    errata_note TEXT DEFAULT NULL,
                    canonical_title VARCHAR(255) DEFAULT '',
                    content_hash VARCHAR(255) DEFAULT '',
                    updated_at VARCHAR(50),
                    INDEX idx_campaign (campaign_id),
                    INDEX idx_category (category),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    query TEXT NOT NULL,
                    answer LONGTEXT NOT NULL,
                    is_helpful BOOLEAN,
                    correct_answer TEXT,
                    created_at VARCHAR(50)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rule_chunks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    page INTEGER,
                    parent_context TEXT DEFAULT '',
                    related_rule_ids TEXT DEFAULT '[]',
                    keywords TEXT DEFAULT '[]',
                    level_requirement INTEGER,
                    campaign_id TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TEXT,
                    edition TEXT DEFAULT 'PHB 2024',
                    status TEXT DEFAULT 'active',
                    superseded_by TEXT,
                    supersedes TEXT,
                    errata_note TEXT,
                    canonical_title TEXT DEFAULT '',
                    content_hash TEXT DEFAULT '',
                    updated_at TEXT
                )
            """)

            # 对旧库做字段迁移（ALTER TABLE 不支持 IF NOT EXISTS，用 try/except）
            _new_columns = [
                ("edition",         "TEXT DEFAULT 'PHB 2024'"),
                ("status",          "TEXT DEFAULT 'active'"),
                ("superseded_by",   "TEXT"),
                ("supersedes",      "TEXT"),
                ("errata_note",     "TEXT"),
                ("canonical_title", "TEXT DEFAULT ''"),
                ("content_hash",    "TEXT DEFAULT ''"),
                ("updated_at",      "TEXT"),
            ]
            for col, col_def in _new_columns:
                try:
                    await conn.execute(
                        f"ALTER TABLE rule_chunks ADD COLUMN {col} {col_def}"
                    )
                except Exception:
                    pass  # 列已存在，忽略

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_campaign ON rule_chunks(campaign_id)",
                "CREATE INDEX IF NOT EXISTS idx_category ON rule_chunks(category)",
                "CREATE INDEX IF NOT EXISTS idx_status ON rule_chunks(status)",
            ]:
                await conn.execute(idx_sql)

            # 反馈表（用于持续改进）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    is_helpful BOOLEAN,
                    correct_answer TEXT,
                    created_at TEXT
                )
            """)

        await conn.commit()


async def save_chunk(chunk: RuleChunk):
    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO rule_chunks
            (id, title, content, category, source, page,
             parent_context, related_rule_ids, keywords,
             level_requirement, campaign_id, priority, created_at,
             edition, status, superseded_by, supersedes,
             errata_note, canonical_title, content_hash, updated_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},
                    {PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            chunk.id, chunk.title, chunk.content,
            chunk.category.value, chunk.source.value, chunk.page,
            chunk.parent_context,
            json.dumps(chunk.related_rule_ids),
            json.dumps(chunk.keywords),
            chunk.level_requirement, chunk.campaign_id,
            chunk.priority, chunk.created_at,
            chunk.edition, chunk.status,
            chunk.superseded_by, chunk.supersedes,
            chunk.errata_note, chunk.canonical_title,
            chunk.content_hash, chunk.updated_at,
        ))
        await conn.commit()


async def get_chunk_by_id(chunk_id: str) -> RuleChunk | None:
    async with async_conn() as conn:
        cursor = await conn.execute(
            f"SELECT * FROM rule_chunks WHERE id = {PH}", (chunk_id,)
        )
        row = await cursor.fetchone()
        if row:
            return _row_to_chunk(row)
        return None


async def get_chunks_by_ids(chunk_ids: list[str]) -> list[RuleChunk]:
    if not chunk_ids:
        return []
    async with async_conn() as conn:
        placeholders = ",".join([PH] * len(chunk_ids))
        cursor = await conn.execute(
            f"SELECT * FROM rule_chunks WHERE id IN ({placeholders})",
            chunk_ids
        )
        rows = await cursor.fetchall()
        return [_row_to_chunk(r) for r in rows]


async def get_all_chunks(campaign_id: str | None = None) -> list[RuleChunk]:
    async with async_conn() as conn:
        if campaign_id:
            cursor = await conn.execute(
                f"SELECT * FROM rule_chunks WHERE campaign_id IS NULL OR campaign_id = {PH}",
                (campaign_id,)
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM rule_chunks WHERE campaign_id IS NULL"
            )
        rows = await cursor.fetchall()
        return [_row_to_chunk(r) for r in rows]


async def list_chunks_paginated(
    source: str | None = None,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    campaign_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RuleChunk], int]:
    """分页列出规则块，支持按来源/状态/分类/关键词过滤。返回 (chunks, total)。"""
    async with async_conn() as conn:
        conditions = []
        params: list = []

        if source:
            conditions.append(f"source = {PH}")
            params.append(source)
        if status:
            conditions.append(f"status = {PH}")
            params.append(status)
        if category:
            conditions.append(f"category = {PH}")
            params.append(category)
        if keyword:
            conditions.append(f"(title LIKE {PH} OR content LIKE {PH})")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if campaign_id:
            conditions.append(f"(campaign_id IS NULL OR campaign_id = {PH})")
            params.append(campaign_id)
        else:
            conditions.append("campaign_id IS NULL")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_cur = await conn.execute(
            f"SELECT COUNT(*) FROM rule_chunks {where}", params
        )
        total = (await count_cur.fetchone())[0]

        data_cur = await conn.execute(
            f"SELECT * FROM rule_chunks {where} ORDER BY source, title LIMIT {PH} OFFSET {PH}",
            params + [limit, offset],
        )
        rows = await data_cur.fetchall()
        return [_row_to_chunk(r) for r in rows], total


async def delete_chunk_by_id(chunk_id: str) -> bool:
    """删除单条规则，返回是否找到并删除。"""
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM rule_chunks WHERE id = {PH}", (chunk_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


async def delete_chunks_by_source(source: str) -> int:
    """删除某个来源的所有规则，返回删除条数。"""
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM rule_chunks WHERE source = {PH}", (source,)
        )
        await conn.commit()
        return cur.rowcount


async def update_chunk_status(chunk_id: str, status: str) -> bool:
    """修改单条规则的 status（active/deprecated），返回是否找到。"""
    async with async_conn() as conn:
        cur = await conn.execute(
            f"UPDATE rule_chunks SET status = {PH} WHERE id = {PH}",
            (status, chunk_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def delete_campaign_rules(campaign_id: str):
    async with async_conn() as conn:
        await conn.execute(
            f"DELETE FROM rule_chunks WHERE campaign_id = {PH}",
            (campaign_id,)
        )
        await conn.commit()


def _row_to_chunk(row: dict) -> RuleChunk:
    return RuleChunk(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        category=RuleCategory(row["category"]),
        source=RuleSource(row["source"]),
        page=row["page"],
        parent_context=row["parent_context"] or "",
        related_rule_ids=json.loads(row["related_rule_ids"] or "[]") if isinstance(row["related_rule_ids"], str) else (row["related_rule_ids"] or []),
        keywords=json.loads(row["keywords"] or "[]") if isinstance(row["keywords"], str) else (row["keywords"] or []),
        level_requirement=row["level_requirement"],
        campaign_id=row["campaign_id"],
        priority=row["priority"] or 0,
        created_at=str(row["created_at"]) if row["created_at"] else "",
        # 版本管理字段（旧行可能为 None，使用模型默认值兜底）
        edition=row["edition"] or "PHB 2024",
        status=row["status"] or "active",
        superseded_by=row["superseded_by"],
        supersedes=row["supersedes"],
        errata_note=row["errata_note"],
        canonical_title=row["canonical_title"] or "",
        content_hash=row["content_hash"] or "",
        updated_at=str(row["updated_at"]) if row["updated_at"] else "",
    )
