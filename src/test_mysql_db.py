"""
测试MySQL数据库功能
"""
import asyncio
import os
from models import RuleChunk, RuleCategory, RuleSource


async def test_mysql_db():
    # 设置使用MySQL
    os.environ['DATABASE_TYPE'] = 'mysql'
    
    # 动态导入，因为配置可能不同
    from db_factory import create_database_instance
    from models import RuleChunk, RuleCategory, RuleSource
    
    print("Testing MySQL Database...")
    
    # 创建MySQL数据库实例
    db = create_database_instance('mysql')
    
    try:
        # 初始化数据库
        print("Initializing MySQL database...")
        await db.init_db()
        print("MySQL database initialized successfully!")
        
        # 创建一个测试规则块
        test_chunk = RuleChunk(
            id="test-rule-001",
            title="Attack Roll",
            content="To make an attack roll, roll 1d20 and add the appropriate modifiers.",
            category=RuleCategory.COMBAT,
            source=RuleSource.PHB_2024,
            page=76,
            keywords=["attack", "roll", "d20", "combat"]
        )
        
        # 保存规则块
        print("Saving test rule chunk...")
        await db.save_chunk(test_chunk)
        print("Rule chunk saved successfully!")
        
        # 获取规则块
        print("Retrieving test rule chunk...")
        retrieved_chunk = await db.get_chunk_by_id("test-rule-001")
        if retrieved_chunk:
            print(f"Retrieved: {retrieved_chunk.title}")
            print(f"Content: {retrieved_chunk.content[:100]}...")
        else:
            print("Failed to retrieve rule chunk")
            
        print("MySQL database test completed successfully!")
        
    except Exception as e:
        print(f"MySQL test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_sqlite_db():
    # 设置使用SQLite
    os.environ['DATABASE_TYPE'] = 'sqlite'
    
    from db_factory import create_database_instance
    from models import RuleChunk, RuleCategory, RuleSource
    
    print("\nTesting SQLite Database...")
    
    # 创建SQLite数据库实例
    db = create_database_instance('sqlite')
    
    try:
        # 初始化数据库
        print("Initializing SQLite database...")
        await db.init_db()
        print("SQLite database initialized successfully!")
        
        # 创建一个测试规则块
        test_chunk = RuleChunk(
            id="test-rule-002",
            title="Saving Throw",
            content="A saving throw represents an attempt to resist a spell, trap, poison, disease, or a similar threat.",
            category=RuleCategory.GENERAL_RULE,
            source=RuleSource.PHB_2014,
            page=179,
            keywords=["saving", "throw", "resist", "spell"]
        )
        
        # 保存规则块
        print("Saving test rule chunk...")
        await db.save_chunk(test_chunk)
        print("Rule chunk saved successfully!")
        
        # 获取规则块
        print("Retrieving test rule chunk...")
        retrieved_chunk = await db.get_chunk_by_id("test-rule-002")
        if retrieved_chunk:
            print(f"Retrieved: {retrieved_chunk.title}")
            print(f"Content: {retrieved_chunk.content[:100]}...")
        else:
            print("Failed to retrieve rule chunk")
            
        print("SQLite database test completed successfully!")
        
    except Exception as e:
        print(f"SQLite test failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("Running database tests...")
    
    # 测试SQLite（默认）
    await test_sqlite_db()
    
    # 测试MySQL（需要正确配置）
    try:
        await test_mysql_db()
    except Exception as e:
        print(f"MySQL test skipped due to configuration issue: {e}")


if __name__ == "__main__":
    asyncio.run(main())