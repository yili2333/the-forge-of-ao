"""
MySQL数据库模块 - 替换原有的SQLite实现
作者: Yang Zixu
功能: 实现RuleChunk的存储、查询、更新和删除操作
"""
import asyncio
import json
import mysql.connector
from mysql.connector import Error
from models import RuleChunk, RuleCategory, RuleSource
from config import get_settings
from typing import List, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


class MySQLDatabase:
    def __init__(self):
        self.host = 'localhost'
        self.database = 'dnd_rules_db'
        self.user = 'root'  # 默认用户名，可根据实际情况修改
        self.password = ''  # 应该从配置中获取，这里先留空
        
        # 从环境变量获取密码
        import os
        self.password = os.getenv('MYSQL_PASSWORD', '')
        if not self.password:
            logger.warning("警告: MYSQL_PASSWORD 环境变量未设置")

    async def get_connection(self):
        """获取数据库连接"""
        try:
            connection = mysql.connector.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password,
                charset='utf8mb4',
                autocommit=False
            )
            return connection
        except Error as e:
            logger.error(f"MySQL连接错误: {e}")
            raise

    async def init_db(self):
        """初始化数据库表"""
        connection = None
        cursor = None
        try:
            # 首先尝试创建数据库
            create_db_conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password
            )
            create_db_cursor = create_db_conn.cursor()
            create_db_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            create_db_cursor.close()
            create_db_conn.close()
            logger.info(f"数据库 {self.database} 准备就绪")

            connection = await self.get_connection()
            cursor = connection.cursor()

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
            cursor.execute(create_rule_chunks_table)

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
            cursor.execute(create_feedback_table)

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
            cursor.execute(create_conflicts_table)

            connection.commit()
            logger.info("数据库表创建成功")

        except Error as e:
            if connection:
                connection.rollback()
            logger.error(f"初始化数据库时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    async def save_chunk(self, chunk: RuleChunk):
        """保存规则块"""
        connection = None
        cursor = None
        try:
            connection = await self.get_connection()
            cursor = connection.cursor()

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

            cursor.execute(query, params)
            connection.commit()
            logger.debug(f"成功保存规则块: {chunk.id}")

        except Error as e:
            if connection:
                connection.rollback()
            logger.error(f"保存规则块时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[RuleChunk]:
        """根据ID获取规则块"""
        connection = None
        cursor = None
        try:
            connection = await self.get_connection()
            cursor = connection.cursor(dictionary=True)

            query = "SELECT * FROM rule_chunks WHERE id = %s"
            cursor.execute(query, (chunk_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_chunk(row)
            return None

        except Error as e:
            logger.error(f"获取规则块时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[RuleChunk]:
        """根据ID列表获取规则块"""
        if not chunk_ids:
            return []
        connection = None
        cursor = None
        try:
            connection = await self.get_connection()
            cursor = connection.cursor(dictionary=True)

            # 构建查询语句
            placeholders = ','.join(['%s'] * len(chunk_ids))
            query = f"SELECT * FROM rule_chunks WHERE id IN ({placeholders})"
            cursor.execute(query, tuple(chunk_ids))
            rows = cursor.fetchall()

            return [self._row_to_chunk(row) for row in rows]

        except Error as e:
            logger.error(f"批量获取规则块时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    async def get_all_chunks(self, campaign_id: Optional[str] = None) -> List[RuleChunk]:
        """获取所有规则块"""
        connection = None
        cursor = None
        try:
            connection = await self.get_connection()
            cursor = connection.cursor(dictionary=True)

            if campaign_id:
                query = "SELECT * FROM rule_chunks WHERE campaign_id IS NULL OR campaign_id = %s"
                cursor.execute(query, (campaign_id,))
            else:
                query = "SELECT * FROM rule_chunks WHERE campaign_id IS NULL"
                cursor.execute(query)
            rows = cursor.fetchall()

            return [self._row_to_chunk(row) for row in rows]

        except Error as e:
            logger.error(f"获取所有规则块时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    async def delete_campaign_rules(self, campaign_id: str):
        """删除战役相关的规则"""
        connection = None
        cursor = None
        try:
            connection = await self.get_connection()
            cursor = connection.cursor()

            query = "DELETE FROM rule_chunks WHERE campaign_id = %s"
            cursor.execute(query, (campaign_id,))
            affected_rows = cursor.rowcount

            connection.commit()
            logger.info(f"删除了 {affected_rows} 条战役规则: {campaign_id}")

        except Error as e:
            if connection:
                connection.rollback()
            logger.error(f"删除战役规则时发生错误: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

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

    async def close(self):
        """关闭数据库连接（如有需要）"""
        pass