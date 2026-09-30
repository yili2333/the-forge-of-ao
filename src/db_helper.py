"""
统一数据库抽象层
支持 SQLite (aiosqlite) 和 MySQL (aiomysql) 双后端。
根据环境变量 DATABASE_TYPE 自动切换，默认 sqlite。

用法:
    from db_helper import async_conn, IS_MYSQL, PH

    async with async_conn() as conn:
        cur = await conn.execute("SELECT * FROM foo WHERE id = ?", (id,))
        row = await cur.fetchone()   # -> dict | None
        rows = await cur.fetchall()  # -> list[dict]
        await conn.commit()
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

# ──────────────────────────────────────────────
#  后端检测
# ──────────────────────────────────────────────
_DB_TYPE = os.getenv("DATABASE_TYPE", "sqlite").lower()
IS_MYSQL: bool = _DB_TYPE == "mysql"
PH: str = "%s" if IS_MYSQL else "?"


# ──────────────────────────────────────────────
#  SQL 适配（仅 MySQL 时生效）
# ──────────────────────────────────────────────
def _adapt_sql(sql: str) -> str:
    """把 SQLite 风格的 SQL 转换为 MySQL 风格。"""
    if not IS_MYSQL:
        return sql
    sql = sql.replace("?", "%s")
    sql = sql.replace("INSERT OR REPLACE INTO", "REPLACE INTO")
    sql = sql.replace("AUTOINCREMENT", "AUTO_INCREMENT")
    return sql


# ──────────────────────────────────────────────
#  DbCursor 包装
# ──────────────────────────────────────────────
class DbCursor:
    """统一游标，fetchone/fetchall 始终返回 dict。"""

    def __init__(self, raw_cursor, is_mysql: bool):
        self._cur = raw_cursor
        self._is_mysql = is_mysql

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    async def fetchone(self) -> dict | None:
        row = await self._cur.fetchone()
        if row is None:
            return None
        if self._is_mysql:
            # aiomysql DictCursor 已经返回 dict
            return dict(row)
        else:
            # aiosqlite.Row 支持映射协议
            return dict(row)

    async def fetchall(self) -> list[dict]:
        rows = await self._cur.fetchall()
        if self._is_mysql:
            return [dict(r) for r in rows]
        else:
            return [dict(r) for r in rows]


# ──────────────────────────────────────────────
#  DbConn 包装
# ──────────────────────────────────────────────
class DbConn:
    """统一连接，execute 自动做 SQL 适配。"""

    def __init__(self, raw_conn, is_mysql: bool):
        self._conn = raw_conn
        self._is_mysql = is_mysql

    async def execute(self, sql: str, params: Any = ()) -> DbCursor:
        sql = _adapt_sql(sql)
        if self._is_mysql:
            cur = await self._conn.cursor(__import__("aiomysql").DictCursor)
            await cur.execute(sql, params or ())
        else:
            # aiosqlite：确保 row_factory 设为 Row
            import aiosqlite
            self._conn.row_factory = aiosqlite.Row
            cur = await self._conn.execute(sql, params or ())
        return DbCursor(cur, self._is_mysql)

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()


# ──────────────────────────────────────────────
#  async_conn() 异步上下文管理器
# ──────────────────────────────────────────────
@asynccontextmanager
async def async_conn() -> AsyncIterator[DbConn]:
    """
    异步上下文管理器，返回 DbConn。
    每次调用都新建连接（简单可靠）。
    出现异常时自动 rollback，正常退出时不自动 commit（由调用方决定）。
    """
    if IS_MYSQL:
        import aiomysql
        from config import get_settings
        s = get_settings()
        raw = await aiomysql.connect(
            host=s.mysql_host,
            port=s.mysql_port,
            user=s.mysql_user,
            password=s.mysql_password,
            db=s.mysql_database,
            charset="utf8mb4",
            autocommit=False,
        )
        conn = DbConn(raw, is_mysql=True)
        try:
            yield conn
        except Exception:
            await conn.rollback()
            raise
        finally:
            raw.close()
    else:
        import aiosqlite
        from config import get_settings
        s = get_settings()
        async with aiosqlite.connect(s.sqlite_path) as raw:
            conn = DbConn(raw, is_mysql=False)
            try:
                yield conn
            except Exception:
                await conn.rollback()
                raise
