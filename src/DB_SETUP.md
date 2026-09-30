# 数据库配置说明

## 概述
本项目支持SQLite和MySQL两种数据库，可通过配置灵活切换。

## 配置选项

### 1. 环境变量配置

在项目根目录创建 `.env` 文件：

```env
# LLM 配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Embedding 配置
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_MODEL=text-embedding-3-small

# 数据库配置
DATABASE_TYPE=mysql  # 或 sqlite
MYSQL_PASSWORD=your_mysql_password
```

### 2. 支持的数据库类型

- `sqlite` (默认): 使用本地SQLite数据库
- `mysql`: 使用MySQL数据库

## MySQL 设置

### 1. 安装依赖
```bash
pip install mysql-connector-python aiomysql
```

### 2. 配置 MySQL

确保MySQL服务正在运行，并创建必要的配置：

- 数据库名: `dnd_rules_db`
- 用户名: `root` (可在 config.py 中修改)
- 密码: 通过环境变量 `MYSQL_PASSWORD` 设置

### 3. 连接参数

在 `config.py` 中可以修改以下参数：

```python
mysql_host: str = "localhost"
mysql_port: int = 3306
mysql_database: str = "dnd_rules_db"
mysql_user: str = "root"
mysql_password: str = ""  # 从环境变量获取
```

## 使用方法

### 1. 初始化数据库

```python
from db import init_db

await init_db()
```

### 2. 数据库操作

所有数据库操作接口保持不变，支持以下操作：

- `save_chunk(chunk)`: 保存规则块
- `get_chunk_by_id(id)`: 根据ID获取规则块
- `get_chunks_by_ids(ids)`: 批量获取规则块
- `get_all_chunks(campaign_id)`: 获取所有规则块
- `delete_campaign_rules(campaign_id)`: 删除战役规则

### 3. 切换数据库类型

只需修改环境变量 `DATABASE_TYPE` 的值即可在SQLite和MySQL之间切换。

## 架构说明

### 数据库接口层
- `db_interface.py`: 定义通用数据库接口
- `db_factory.py`: 数据库实例工厂，根据配置创建相应实例

### 具体实现
- `sqlite_db.py`: SQLite数据库实现
- `async_mysql_db.py`: MySQL数据库实现（异步）

### 兼容性
- 所有上层代码无需修改即可支持数据库切换
- 统一的错误处理和日志记录
- 相同的数据模型和API接口

## 注意事项

1. MySQL需要提前安装并运行
2. 密码应通过环境变量设置，不要硬编码
3. 表结构在初始化时自动创建
4. 数据库连接池管理由底层实现处理