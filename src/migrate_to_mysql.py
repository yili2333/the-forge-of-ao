"""
从 SQLite 迁移到 MySQL 的一次性脚本

用法：
  1. 确保 .env 里配置好 MYSQL_* 环境变量（DATABASE_TYPE 可为任意值，脚本直接读 SQLite 和 MySQL）
  2. 确保 MySQL 服务正在运行
  3. cd src && python migrate_to_mysql.py

迁移表：
  rule_chunks, feedback, rule_conflicts,
  characters, character_history,
  monsters,
  campaigns, campaign_invites,
  world_maps, encounter_maps,
  game_sessions, session_op_log
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 确保能 import 项目模块
_SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(_SRC))

import aiosqlite
import aiomysql

from config import get_settings


# ──────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────

async def get_sqlite_conn(sqlite_path: str):
    conn = await aiosqlite.connect(sqlite_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def get_mysql_conn(s):
    """先尝试创建 database，再返回连接到该 db 的 conn"""
    # 先无 db 连接，创建 database
    bare = await aiomysql.connect(
        host=s.mysql_host, port=s.mysql_port,
        user=s.mysql_user, password=s.mysql_password,
        charset="utf8mb4",
    )
    async with bare.cursor() as cur:
        await cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{s.mysql_database}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    bare.close()

    conn = await aiomysql.connect(
        host=s.mysql_host, port=s.mysql_port,
        user=s.mysql_user, password=s.mysql_password,
        db=s.mysql_database, charset="utf8mb4",
        autocommit=False,
    )
    return conn


def _row_to_dict(row) -> dict:
    return dict(row)


# ──────────────────────────────────────────────
#  通用表迁移
# ──────────────────────────────────────────────

async def migrate_table(
    sqlite_conn,
    mysql_conn,
    table: str,
    columns: list[str],
    truncate: bool = True,
) -> int:
    """
    从 SQLite 的 table 读取所有行，插入 MySQL。
    columns 决定列顺序（同时用于 SELECT 和 INSERT）。
    """
    # 读 SQLite
    try:
        async with sqlite_conn.execute(
            f"SELECT {','.join(columns)} FROM {table}"
        ) as cur:
            rows = await cur.fetchall()
    except Exception as e:
        print(f"  [SKIP] {table}: SQLite read error: {e}")
        return 0

    if not rows:
        print(f"  [SKIP] {table}: empty in SQLite")
        return 0

    # 写 MySQL
    async with mysql_conn.cursor() as cur:
        if truncate:
            await cur.execute(f"TRUNCATE TABLE `{table}`")

        ph = ",".join(["%s"] * len(columns))
        col_str = ",".join([f"`{c}`" for c in columns])
        insert_sql = f"INSERT INTO `{table}` ({col_str}) VALUES ({ph})"

        count = 0
        for row in rows:
            values = tuple(row[c] for c in columns)
            try:
                await cur.execute(insert_sql, values)
                count += 1
            except Exception as e:
                print(f"    [WARN] row insert failed in {table}: {e}")

    await mysql_conn.commit()
    print(f"  [OK] {table}: {count} rows migrated")
    return count


# ──────────────────────────────────────────────
#  各表列定义
# ──────────────────────────────────────────────

TABLE_COLUMNS = {
    "rule_chunks": [
        "id", "title", "content", "category", "source", "page",
        "parent_context", "related_rule_ids", "keywords",
        "level_requirement", "campaign_id", "priority", "created_at",
        "edition", "status", "superseded_by", "supersedes",
        "errata_note", "canonical_title", "content_hash", "updated_at",
    ],
    "feedback": [
        "id", "query", "answer", "is_helpful", "correct_answer", "created_at",
    ],
    "rule_conflicts": [
        "id", "conflict_type",
        "rule_a_id", "rule_a_title", "rule_a_source",
        "rule_b_id", "rule_b_title", "rule_b_source",
        "description", "resolution", "auto_resolved", "created_at",
    ],
    "characters": [
        "id", "owner_id", "owner_display", "campaign_id", "name",
        "edition", "total_level", "non_standard", "dm_approved",
        "data_json", "version", "created_at", "updated_at", "deleted_at",
    ],
    "character_history": [
        "id", "character_id", "version", "data_json", "changed_at",
    ],
    "monsters": [
        "id", "name_cn", "name_en", "size", "creature_type",
        "subtype", "alignment",
        "ac", "ac_note", "hp", "hp_formula", "speed", "initiative_bonus",
        "str", "dex", "con", "int_", "wis", "cha",
        "saving_throws", "skills",
        "damage_vulnerabilities", "damage_resistances",
        "damage_immunities", "condition_immunities",
        "senses", "passive_perception", "languages", "equipment",
        "cr", "xp", "proficiency_bonus",
        "traits", "actions", "bonus_actions", "reactions",
        "legendary_actions", "legendary_action_desc",
        "lair_actions", "mythic_actions",
        "source", "source_file", "tags",
        "created_at", "updated_at",
    ],
    "campaigns": [
        "id", "name", "description", "dm_owner_id", "dm_display", "status",
        "player_ids", "character_ids", "world_map_id", "session_count",
        "edition", "tags", "created_at", "updated_at",
    ],
    "campaign_invites": [
        "code", "campaign_id", "campaign_name", "dm_display",
        "max_uses", "uses", "expires_at", "created_at", "is_active",
    ],
    "world_maps": [
        "id", "campaign_id", "name", "description",
        "width_km", "height_km", "image_url", "image_prompt",
        "pois_json", "player_positions_json", "visited_locations_json",
        "fog_of_war", "created_at", "updated_at",
    ],
    "encounter_maps": [
        "id", "campaign_id", "name", "description",
        "grid_cols", "grid_rows", "cell_size_ft",
        "image_url", "image_prompt",
        "cells_json", "creatures_json", "objects_json",
        "is_active", "created_at", "updated_at",
    ],
    "game_sessions": [
        "id", "campaign_id", "round_number", "current_turn_index",
        "initiative_json", "scene_json", "active_encounter_map_id",
        "started_at", "last_active_at",
    ],
    "session_op_log": [
        "id", "session_id", "op_type", "actor_id",
        "payload", "round_number", "ts",
    ],
}


# ──────────────────────────────────────────────
#  初始化 MySQL 表结构（委托给各 storage 模块）
# ──────────────────────────────────────────────

async def init_mysql_schema():
    """强制以 MySQL 模式初始化所有表结构"""
    # 临时覆盖环境变量，让 db_helper 以 mysql 模式工作
    os.environ["DATABASE_TYPE"] = "mysql"

    # db_helper 在模块级别读取环境变量，需要重新导入或重新初始化
    import importlib
    import db_helper
    importlib.reload(db_helper)

    from db import init_db
    from character.storage import init_character_db
    from monster.storage import init_monster_db
    from campaign.storage import init_campaign_db
    from maps.storage import init_map_db
    from session.storage import init_session_db

    print("Initializing MySQL schema...")
    await init_db()
    await init_character_db()
    await init_monster_db()
    await init_campaign_db()
    await init_map_db()
    await init_session_db()
    print("MySQL schema ready.")


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

async def main():
    s = get_settings()

    print(f"Source SQLite: {s.sqlite_path}")
    print(f"Target MySQL:  {s.mysql_user}@{s.mysql_host}:{s.mysql_port}/{s.mysql_database}")
    print()

    if not Path(s.sqlite_path).exists():
        print(f"ERROR: SQLite file not found: {s.sqlite_path}")
        sys.exit(1)

    # 初始化 MySQL 表结构
    await init_mysql_schema()

    # 打开 SQLite（只读模式读取）
    sqlite_conn = await get_sqlite_conn(s.sqlite_path)
    mysql_conn = await get_mysql_conn(s)

    print("\nMigrating tables...")
    total = 0
    for table, columns in TABLE_COLUMNS.items():
        count = await migrate_table(sqlite_conn, mysql_conn, table, columns)
        total += count

    await sqlite_conn.close()
    mysql_conn.close()

    print(f"\nDone! Total rows migrated: {total}")


if __name__ == "__main__":
    asyncio.run(main())
