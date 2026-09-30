"""
数据库迁移脚本
作者: Yang Zixu
功能: 支持SQLite到MySQL的数据迁移
"""
import asyncio
from sqlite_db import SQLiteDatabase
from async_mysql_db import AsyncMySQLDatabase
from config import get_settings
import os


async def migrate_sqlite_to_mysql():
    """
    从SQLite迁移到MySQL
    """
    print("Starting migration from SQLite to MySQL...")
    
    # 创建源数据库（SQLite）
    sqlite_db = SQLiteDatabase()
    
    # 创建目标数据库（MySQL）
    mysql_db = AsyncMySQLDatabase()
    
    # 初始化目标数据库
    await mysql_db.init_db()
    
    # 从SQLite获取所有数据
    print("Fetching all chunks from SQLite...")
    all_chunks = await sqlite_db.get_all_chunks()
    print(f"Found {len(all_chunks)} chunks to migrate")
    
    # 逐个保存到MySQL
    migrated_count = 0
    for i, chunk in enumerate(all_chunks):
        try:
            await mysql_db.save_chunk(chunk)
            migrated_count += 1
            if migrated_count % 10 == 0:
                print(f"Migrated {migrated_count}/{len(all_chunks)} chunks...")
        except Exception as e:
            print(f"Error migrating chunk {chunk.id}: {e}")
    
    print(f"Migration completed! Migrated {migrated_count} chunks.")
    

async def migrate_mysql_to_sqlite():
    """
    从MySQL迁移到SQLite
    """
    print("Starting migration from MySQL to SQLite...")
    
    # 创建源数据库（MySQL）
    mysql_db = AsyncMySQLDatabase()
    
    # 创建目标数据库（SQLite）
    sqlite_db = SQLiteDatabase()
    
    # 初始化目标数据库
    await sqlite_db.init_db()
    
    # 从MySQL获取所有数据
    print("Fetching all chunks from MySQL...")
    all_chunks = await mysql_db.get_all_chunks()
    print(f"Found {len(all_chunks)} chunks to migrate")
    
    # 逐个保存到SQLite
    migrated_count = 0
    for i, chunk in enumerate(all_chunks):
        try:
            await sqlite_db.save_chunk(chunk)
            migrated_count += 1
            if migrated_count % 10 == 0:
                print(f"Migrated {migrated_count}/{len(all_chunks)} chunks...")
        except Exception as e:
            print(f"Error migrating chunk {chunk.id}: {e}")
    
    print(f"Migration completed! Migrated {migrated_count} chunks.")


async def main():
    # 从环境变量确定迁移方向
    source_type = os.getenv('SOURCE_DB_TYPE', 'sqlite').lower()
    target_type = os.getenv('TARGET_DB_TYPE', 'mysql').lower()
    
    print(f"Migration: {source_type} -> {target_type}")
    
    if source_type == 'sqlite' and target_type == 'mysql':
        await migrate_sqlite_to_mysql()
    elif source_type == 'mysql' and target_type == 'sqlite':
        await migrate_mysql_to_sqlite()
    else:
        print(f"Unsupported migration direction: {source_type} -> {target_type}")
        print("Supported directions: sqlite -> mysql, mysql -> sqlite")


if __name__ == "__main__":
    asyncio.run(main())