"""
异步MySQL数据库模块
作者: Yang Zixu
功能: 提供异步的RuleChunk存储、查询、更新和删除操作
"""
import aiomysql
import json
from models import RuleChunk, RuleCategory, RuleSource
from config import get_settings
from typing import List, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


class AsyncMySQLDatabase:
    def __init__(self):
        self.host = 'localhost'
        self.database = 'dnd_rules_db'
        self.user = 'root'  # 可以从配置中获取
        self.password = ''  # 从环境变量获取
        
        # 从环境变量获取密码
        import os
        self.password = os.getenv('MYSQL_PASSWORD', '')
        if not self.password:
            logger.warning("警告: MYSQL_PASSWORD 环境变量未设置")

    async def get_pool(self):
        """获取数据库连接池"""
        pool = await aiomysql.create_pool(
            host=self.host,
            port=3306,
            user=self.user,
            password=self.password,
            db=self.database,
            charset='utf8mb4',
            autocommit=False,
            minsize=1,
            maxsize=10
        )
        return pool

    async def init_db(self):
        """初始化数据库表"""
        conn = None
        cur = None
        try:
            # 首先尝试创建数据库
            create_db_conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                charset='utf8mb4'
            )
            create_db_cur = await create_db_conn.cursor()
            await create_db_cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            await create_db_cur.close()
            create_db_conn.close()
            logger.info(f"数据库 {self.database} 准备就绪")

            # 获取连接并创建表
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=False
            )
            cur = await conn.cursor()

            # 创建规则块表
            create_rule_chunks_table = """
            CREATE TABLE IF NOT EXISTS rule_chunks (
                id VARCHAR(255) PRIMARY KEY,
                title TEXT NOT NULL,
                content LONGTEXT NOT NULL,
                category VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                page INT DEFAULT NULL,
                parent_context TEXT DEFAULT '',
                related_rule_ids JSON DEFAULT (JSON_ARRAY()),
                keywords JSON DEFAULT (JSON_ARRAY()),
                level_requirement INT DEFAULT NULL,
                campaign_id VARCHAR(255) DEFAULT NULL,
                priority INT DEFAULT 0,
                edition VARCHAR(50) DEFAULT 'PHB 2024',
                status VARCHAR(20) DEFAULT 'active',
                superseded_by VARCHAR(255) DEFAULT NULL,
                supersedes VARCHAR(255) DEFAULT NULL,
                errata_note TEXT DEFAULT NULL,
                canonical_title VARCHAR(255) DEFAULT '',
                content_hash VARCHAR(255) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_campaign (campaign_id),
                INDEX idx_category (category),
                INDEX idx_source (source),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            await cur.execute(create_rule_chunks_table)

            # 创建反馈表
            create_feedback_table = """
            CREATE TABLE IF NOT EXISTS feedback (
                id INT AUTO_INCREMENT PRIMARY KEY,
                query TEXT NOT NULL,
                answer LONGTEXT NOT NULL,
                is_helpful BOOLEAN,
                correct_answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            await cur.execute(create_feedback_table)

            # 创建规则冲突表
            create_conflicts_table = """
            CREATE TABLE IF NOT EXISTS rule_conflicts (
                id VARCHAR(255) PRIMARY KEY,
                conflict_type VARCHAR(50) NOT NULL,
                rule_a_id VARCHAR(255) NOT NULL,
                rule_a_title VARCHAR(255) NOT NULL,
                rule_a_source VARCHAR(50) NOT NULL,
                rule_b_id VARCHAR(255) NOT NULL,
                rule_b_title VARCHAR(255) NOT NULL,
                rule_b_source VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                resolution TEXT DEFAULT '',
                auto_resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            await cur.execute(create_conflicts_table)

            await conn.commit()
            logger.info("数据库表创建成功")

        except Exception as e:
            if conn:
                await conn.rollback()
            logger.error(f"初始化数据库时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    async def save_chunk(self, chunk: RuleChunk):
        """保存规则块"""
        conn = None
        cur = None
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=False
            )
            cur = await conn.cursor()

            # 准备JSON数据
            related_rule_ids_json = json.dumps(chunk.related_rule_ids, ensure_ascii=False)
            keywords_json = json.dumps(chunk.keywords, ensure_ascii=False)

            query = """
            INSERT INTO rule_chunks (
                id, title, content, category, source, page, parent_context,
                related_rule_ids, keywords, level_requirement, campaign_id, priority,
                edition, status, superseded_by, supersedes, errata_note, canonical_title, content_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                content = VALUES(content),
                category = VALUES(category),
                source = VALUES(source),
                page = VALUES(page),
                parent_context = VALUES(parent_context),
                related_rule_ids = VALUES(related_rule_ids),
                keywords = VALUES(keywords),
                level_requirement = VALUES(level_requirement),
                campaign_id = VALUES(campaign_id),
                priority = VALUES(priority),
                edition = VALUES(edition),
                status = VALUES(status),
                superseded_by = VALUES(superseded_by),
                supersedes = VALUES(supersedes),
                errata_note = VALUES(errata_note),
                canonical_title = VALUES(canonical_title),
                content_hash = VALUES(content_hash),
                updated_at = CURRENT_TIMESTAMP
            """

            params = (
                chunk.id, chunk.title, chunk.content, chunk.category.value, chunk.source.value,
                chunk.page, chunk.parent_context, related_rule_ids_json, keywords_json,
                chunk.level_requirement, chunk.campaign_id, chunk.priority,
                chunk.edition, chunk.status, chunk.superseded_by, chunk.supersedes,
                chunk.errata_note, chunk.canonical_title, chunk.content_hash
            )

            await cur.execute(query, params)
            await conn.commit()
            logger.debug(f"成功保存规则块: {chunk.id}")

        except Exception as e:
            if conn:
                await conn.rollback()
            logger.error(f"保存规则块时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[RuleChunk]:
        """根据ID获取规则块"""
        conn = None
        cur = None
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=True
            )
            cur = await conn.cursor(aiomysql.DictCursor)

            query = "SELECT * FROM rule_chunks WHERE id = %s"
            await cur.execute(query, (chunk_id,))
            row = await cur.fetchone()

            if row:
                return self._row_to_chunk(row)
            return None

        except Exception as e:
            logger.error(f"获取规则块时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[RuleChunk]:
        """根据ID列表获取规则块"""
        if not chunk_ids:
            return []
        
        conn = None
        cur = None
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=True
            )
            cur = await conn.cursor(aiomysql.DictCursor)

            # 构建查询语句
            format_strings = ','.join(['%s'] * len(chunk_ids))
            query = f"SELECT * FROM rule_chunks WHERE id IN ({format_strings})"
            await cur.execute(query, tuple(chunk_ids))
            rows = await cur.fetchall()

            return [self._row_to_chunk(row) for row in rows]

        except Exception as e:
            logger.error(f"批量获取规则块时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    async def get_all_chunks(self, campaign_id: Optional[str] = None) -> List[RuleChunk]:
        """获取所有规则块"""
        conn = None
        cur = None
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=True
            )
            cur = await conn.cursor(aiomysql.DictCursor)

            if campaign_id:
                query = "SELECT * FROM rule_chunks WHERE campaign_id IS NULL OR campaign_id = %s"
                await cur.execute(query, (campaign_id,))
            else:
                query = "SELECT * FROM rule_chunks WHERE campaign_id IS NULL"
                await cur.execute(query)
            rows = await cur.fetchall()

            return [self._row_to_chunk(row) for row in rows]

        except Exception as e:
            logger.error(f"获取所有规则块时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    async def delete_campaign_rules(self, campaign_id: str):
        """删除战役相关的规则"""
        conn = None
        cur = None
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=3306,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=False
            )
            cur = await conn.cursor()

            query = "DELETE FROM rule_chunks WHERE campaign_id = %s"
            await cur.execute(query, (campaign_id,))
            affected_rows = cur.rowcount

            await conn.commit()
            logger.info(f"删除了 {affected_rows} 条战役规则: {campaign_id}")

        except Exception as e:
            if conn:
                await conn.rollback()
            logger.error(f"删除战役规则时发生错误: {e}")
            raise
        finally:
            if cur:
                await cur.close()
            if conn:
                await conn.close()

    def _row_to_chunk(self, row) -> RuleChunk:
        """将数据库行转换为RuleChunk对象"""
        # 处理JSON字段
        related_rule_ids = json.loads(row["related_rule_ids"]) if row["related_rule_ids"] else []
        keywords = json.loads(row["keywords"]) if row["keywords"] else []

        return RuleChunk(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            category=RuleCategory(row["category"]),
            source=RuleSource(row["source"]),
            page=row["page"],
            parent_context=row["parent_context"] or "",
            related_rule_ids=related_rule_ids,
            keywords=keywords,
            level_requirement=row["level_requirement"],
            campaign_id=row["campaign_id"],
            priority=row["priority"] or 0,
            edition=row["edition"] or "PHB 2024",
            status=row["status"] or "active",
            superseded_by=row["superseded_by"],
            supersedes=row["supersedes"],
            errata_note=row["errata_note"],
            canonical_title=row["canonical_title"] or "",
            content_hash=row["content_hash"] or "",
            created_at=str(row["created_at"]) if row["created_at"] else "",
            updated_at=str(row["updated_at"]) if row["updated_at"] else "",
            score=0.0,  # 运行时附加
            is_overridden=False  # 运行时附加
        )