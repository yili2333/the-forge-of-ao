"""
SQLite数据库模块 - 实现数据库接口
作者: Yang Zixu
功能: 基于aiosqlite的RuleChunk存储、查询、更新和删除操作
"""
import aiosqlite
import json
from models import RuleChunk, RuleCategory, RuleSource
from config import get_settings
from db_interface import DatabaseInterface
from typing import List, Optional

settings = get_settings()


class SQLiteDatabase(DatabaseInterface):
    def __init__(self):
        self.db_path = settings.sqlite_path

    async def init_db(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as conn:
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
                    edition TEXT DEFAULT 'PHB 2024',
                    status TEXT DEFAULT 'active',
                    superseded_by TEXT DEFAULT NULL,
                    supersedes TEXT DEFAULT NULL,
                    errata_note TEXT DEFAULT NULL,
                    canonical_title TEXT DEFAULT '',
                    content_hash TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_campaign 
                ON rule_chunks(campaign_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category 
                ON rule_chunks(category)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source 
                ON rule_chunks(source)
            """)

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

            # 冲突记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rule_conflicts (
                    id TEXT PRIMARY KEY,
                    conflict_type TEXT NOT NULL,
                    rule_a_id TEXT NOT NULL,
                    rule_a_title TEXT NOT NULL,
                    rule_a_source TEXT NOT NULL,
                    rule_b_id TEXT NOT NULL,
                    rule_b_title TEXT NOT NULL,
                    rule_b_source TEXT NOT NULL,
                    description TEXT NOT NULL,
                    resolution TEXT DEFAULT '',
                    auto_resolved BOOLEAN DEFAULT FALSE,
                    created_at TEXT
                )
            """)

            await conn.commit()

    async def save_chunk(self, chunk: RuleChunk):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                INSERT OR REPLACE INTO rule_chunks 
                (id, title, content, category, source, page, 
                 parent_context, related_rule_ids, keywords,
                 level_requirement, campaign_id, priority,
                 edition, status, superseded_by, supersedes, errata_note,
                 canonical_title, content_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.id, chunk.title, chunk.content,
                chunk.category.value, chunk.source.value, chunk.page,
                chunk.parent_context,
                json.dumps(chunk.related_rule_ids),
                json.dumps(chunk.keywords),
                chunk.level_requirement, chunk.campaign_id,
                chunk.priority, chunk.edition, chunk.status,
                chunk.superseded_by, chunk.supersedes, chunk.errata_note,
                chunk.canonical_title, chunk.content_hash,
                chunk.created_at, chunk.updated_at
            ))
            await conn.commit()

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[RuleChunk]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM rule_chunks WHERE id = ?", (chunk_id,)
            )
            row = await cursor.fetchone()
            if row:
                return self._row_to_chunk(row)
            return None

    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[RuleChunk]:
        if not chunk_ids:
            return []
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            placeholders = ",".join("?" * len(chunk_ids))
            cursor = await conn.execute(
                f"SELECT * FROM rule_chunks WHERE id IN ({placeholders})",
                chunk_ids
            )
            rows = await cursor.fetchall()
            return [self._row_to_chunk(r) for r in rows]

    async def get_all_chunks(self, campaign_id: Optional[str] = None) -> List[RuleChunk]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if campaign_id:
                cursor = await conn.execute(
                    "SELECT * FROM rule_chunks WHERE campaign_id IS NULL OR campaign_id = ?",
                    (campaign_id,)
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM rule_chunks WHERE campaign_id IS NULL"
                )
            rows = await cursor.fetchall()
            return [self._row_to_chunk(r) for r in rows]

    async def delete_campaign_rules(self, campaign_id: str):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM rule_chunks WHERE campaign_id = ?",
                (campaign_id,)
            )
            await conn.commit()

    def _row_to_chunk(self, row) -> RuleChunk:
        return RuleChunk(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            category=RuleCategory(row["category"]),
            source=RuleSource(row["source"]),
            page=row["page"],
            parent_context=row["parent_context"],
            related_rule_ids=json.loads(row["related_rule_ids"]),
            keywords=json.loads(row["keywords"]),
            level_requirement=row["level_requirement"],
            campaign_id=row["campaign_id"],
            priority=row["priority"],
            edition=row["edition"],
            status=row["status"],
            superseded_by=row["superseded_by"],
            supersedes=row["supersedes"],
            errata_note=row["errata_note"],
            canonical_title=row["canonical_title"],
            content_hash=row["content_hash"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            score=0.0,
            is_overridden=False
        )