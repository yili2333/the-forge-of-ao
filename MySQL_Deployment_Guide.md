# MySQL数据库部署指南

## 概述
本指南介绍如何将D&D AI TRPG平台从SQLite切换到MySQL数据库，包括安装、配置和迁移步骤。

## 系统要求
- MySQL 8.0或更高版本
- Python 3.8或更高版本
- 至少500MB可用磁盘空间（用于规则数据）

## 安装MySQL

### Windows安装
1. 从[MySQL官网](https://dev.mysql.com/downloads/installer/)下载MySQL Installer
2. 运行安装程序，选择"Developer Default"或"Server only"
3. 在配置过程中设置root用户密码
4. 完成安装后启动MySQL服务

### 验证安装
```bash
# 检查MySQL服务状态
net start | findstr -i mysql

# 测试连接
mysql -u root -p
```

## 项目配置

### 1. 更新环境变量
修改 `.env` 文件：
```env
# 数据库配置
DATABASE_TYPE=mysql

# MySQL配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=dnd_rules_db
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_root_password
```

### 2. 安装Python依赖
```bash
pip install mysql-connector-python aiomysql
```

### 3. 验证配置
```bash
# 测试数据库连接
python -c "from src.db import init_db; import asyncio; asyncio.run(init_db())"
```

## 数据迁移（如果从SQLite迁移）

### 1. 准备迁移
确保SQLite数据库中有数据且MySQL服务正在运行。

### 2. 执行迁移
```bash
# 设置迁移方向
export SOURCE_DB_TYPE=sqlite
export TARGET_DB_TYPE=mysql

# 运行迁移脚本
python src/db_migration.py
```

## 性能优化建议

### MySQL配置优化
在 `my.ini` 或 `my.cnf` 中添加以下配置：
```ini
[mysqld]
# InnoDB设置
innodb_buffer_pool_size = 256M
innodb_log_file_size = 64M
innodb_flush_log_at_trx_commit = 2

# 连接设置
max_connections = 100
wait_timeout = 300

# 查询缓存
query_cache_size = 32M
query_cache_type = 1
```

### 数据库索引优化
系统会在初始化时自动创建以下索引：
- `idx_campaign`: 按战役ID查询
- `idx_category`: 按规则类别查询
- `idx_source`: 按来源查询
- `idx_status`: 按状态查询

## 监控和维护

### 定期备份
```sql
-- 备份规则数据
mysqldump -u root -p dnd_rules_db rule_chunks > backup_rule_chunks.sql
```

### 性能监控
```sql
-- 检查慢查询
SHOW PROCESSLIST;

-- 查看表大小
SELECT table_name, 
       ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.tables 
WHERE table_schema = 'dnd_rules_db';
```

## 故障排除

### 常见问题

#### 1. 连接被拒绝
- 检查MySQL服务是否运行
- 确认端口和主机配置正确
- 检查防火墙设置

#### 2. 权限错误
- 确保MySQL用户有足够的权限访问dnd_rules_db数据库
- 验证用户名和密码

#### 3. 字符编码问题
- 确保MySQL配置使用utf8mb4字符集
- 检查连接字符串中的charset参数

### 调试步骤
1. 启用详细日志：
   ```env
   LOG_LEVEL=DEBUG
   ```
   
2. 检查数据库连接：
   ```bash
   python -c "import mysql.connector; conn = mysql.connector.connect(host='localhost', user='root', password='your_password'); print('Connected successfully')"
   ```

## 扩展配置

### 多实例部署
对于生产环境，建议配置：
- 主从复制以提高读取性能
- 连接池管理
- 定期维护计划

### 安全配置
- 创建专用数据库用户而非使用root
- 配置SSL连接
- 限制远程访问

## 验证部署

完成配置后，运行以下命令验证一切正常工作：

```bash
# 1. 初始化数据库
python -c "from src.db import init_db; import asyncio; asyncio.run(init_db())"

# 2. 测试基本操作
python src/test_mysql_db.py

# 3. 检查数据库状态
mysql -u root -p -e "USE dnd_rules_db; SHOW TABLES;"
```

## 切换回SQLite

如需切换回SQLite，只需修改环境变量：
```env
DATABASE_TYPE=sqlite
```

然后重启应用程序。