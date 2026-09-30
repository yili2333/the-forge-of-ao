"""
数据库工厂类
作者: Yang Zixu
功能: 根据配置创建相应的数据库实例（SQLite或MySQL）
"""
from config import get_settings
from db_interface import DatabaseInterface
from sqlite_db import SQLiteDatabase
from async_mysql_db import AsyncMySQLDatabase
import os


def create_database_instance(db_type: str = None) -> DatabaseInterface:
    """
    根据配置创建数据库实例
    
    Args:
        db_type: 数据库类型 ('sqlite' 或 'mysql')，如果不提供则从环境变量获取
        
    Returns:
        DatabaseInterface: 数据库实例
    """
    settings = get_settings()
    
    # 确定数据库类型
    target_db_type = db_type or os.getenv('DATABASE_TYPE', 'sqlite').lower()
    
    if target_db_type == 'mysql':
        print("Using MySQL Database")
        return AsyncMySQLDatabase()
    else:
        print("Using SQLite Database")
        return SQLiteDatabase()


async def init_database(db_instance: DatabaseInterface = None):
    """
    初始化数据库
    
    Args:
        db_instance: 数据库实例，如果不提供则根据配置创建
    """
    if db_instance is None:
        db_instance = create_database_instance()
    
    print("Initializing database...")
    await db_instance.init_db()
    print("Database initialization completed.")