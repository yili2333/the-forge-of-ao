# D&D Rules AI — 功能总览

> 最后更新：2026-04-16  
> 技术栈：FastAPI + SQLite (aiosqlite) + Qdrant(内存) + WebSocket  
> 规则版本：D&D 5e 2024 为主，向下兼容 2014

---

## 目录

1. [RAG 规则引擎](#1-rag-规则引擎)
2. [角色系统](#2-角色系统)
3. [怪物系统](#3-怪物系统)
4. [战役系统](#4-战役系统)
5. [地图系统](#5-地图系统)
6. [游戏会话系统](#6-游戏会话系统)
7. [WebSocket 实时通信](#7-websocket-实时通信)
8. [骰子引擎](#8-骰子引擎)
9. [基础设施](#9-基础设施)
10. [数据库结构](#10-数据库结构)
11. [联机方式](#11-联机方式)

---

## 1. RAG 规则引擎

> 核心：检索增强生成，所有答案严格来自知识库，拒绝使用模型训练数据补充

### 检索流程

```
用户问题
  ↓
混合检索（向量 + BM25 关键词）
  ↓
RRF 融合排序（Reciprocal Rank Fusion）
  ↓
交叉引用补充（自动拉取关联规则，最多 3 条）
  ↓
版本冲突检测（2024 覆盖 2014，官方勘误 > 基础规则）
  ↓
LLM 生成答案（仅允许引用检索到的内容）
```

### 嵌入模型（自动选择）

| 硬件 | 优先使用 | 备选 |
|---|---|---|
| GPU ≥ 4GB | BAAI/bge-m3（多语言，最高质量）| bge-small-zh |
| CPU（当前）| BAAI/bge-small-zh-v1.5（93MB）| MiniLM-L6-v2 |
| 本地全失败 | API 兜底（智谱 embedding-3） | — |

本地模型优先从项目 `models/` 目录加载（支持离线部署）。

### 知识库管理

- **导入来源**：HTM/HTML 文件（支持多格式解析）、PDF（基础支持）、手动文本
- **已导入数据**：PHB 2024（789条）、Basic Rules 2024（693条）、MM 2024（677条）、DMG 2024（670条）、自定义（6条），共 2835 条
- **战役隔离**：自制规则（Homebrew）按 campaign_id 隔离，只在对应战役内检索
- **版本冲突标记**：检索时自动识别被覆盖的旧版规则，在答案中以 ⚠️ 标注

### 答案格式

每条答案固定四段：
```
📜 裁定结论
📖 规则依据
💡 补充说明
📋 引用来源
```

知识库无相关内容时输出 `📭 知识库未收录`，不补充训练数据。

### 角色上下文查询

`POST /api/character/{id}/ask` 在查询前自动注入角色状态（等级、技能熟练、当前 HP、法术位、状态异常等），LLM 答案会结合角色实际情况给出具体裁定。

---

## 2. 角色系统

> 基于 D&D 5e 2024 版规则，支持多职业

### 角色表字段

| 分类 | 内容 |
|---|---|
| 六维属性 | STR / DEX / CON / INT / WIS / CHA，自动计算修正值 |
| 职业等级 | 多职业支持（数组），每职业含生命骰、子职业 |
| 生命值 | 当前/最大 HP，死亡豁免计数（成功/失败各3次） |
| 法术系统 | 1-9 环法术位（可用/已用），施法豁免 DC，法术攻击加值 |
| 技能 | 18 项技能，各有 未熟练/熟练/专精 三档 |
| 豁免 | 六维各自的熟练标记 |
| 疲惫 | 0-10 级（2024版，非 2014 的 6 级） |
| 状态异常 | 13 种标准状态（盲目、魅惑、耳聋等） |
| 临时效果 | 名称、来源、持续类型、专注标记 |
| 装备 | 护甲/盾牌/武器（装备状态），背包物品（数量/重量/价值）|
| 货币 | CP / SP / EP / GP / PP |
| 元数据 | owner_id、campaign_id、版本、DM 审批状态 |

### 派生值自动计算

- **AC**：根据护甲类型（无甲/轻甲/中甲/重甲）+ DEX 上限 + 盾牌 + 魔法加值自动计算
- **先攻**：DEX 修正值（部分职业特性可加）
- **熟练加值**：按总等级自动分档（+2 到 +6）
- **施法 DC**：8 + 施法属性修正 + 熟练加值

### 建卡功能

- 属性分配方式：标准数组（15/14/13/12/10/8）、购点法（27点）、掷骰（4d6取高三）、手动输入
- 非标准建卡自动标记 `non_standard=true`，需要 DM 审批才能参团

### 升级 & 洗点

```
POST /api/character/{id}/level-up
  参数：class_name, hp_method(average/roll), asi_choice, subclass

POST /api/character/{id}/respec
  重置职业/属性/技能，保留身份信息，需 DM 审批
```

### 效果与状态

```
POST /api/character/{id}/apply-effect   # 施加临时效果（Bless、专注法术等）
DELETE /api/character/{id}/effects/{id} # 移除效果
POST /api/character/{id}/polymorph      # DM 触发变形术（保留 HP/AC 快照）
POST /api/character/{id}/polymorph/revert  # 解除变形，恢复快照
POST /api/character/{id}/wish           # DM 许愿术（永久修改基础属性）
```

**专注机制**：同时只能维持一个专注效果，新效果自动打断旧专注。

### 休息机制

**短休（1小时）**
- 消耗生命骰（dX + CON 修正）回复 HP
- 刷新短休资源：Warlock 誓约位、武僧气点等
- 清除"持续到短休"的效果

**长休（8小时）**
- HP 全回，所有法术位恢复
- 消耗过的生命骰恢复一半
- 死亡豁免清零，疲惫 -1
- 清除所有临时效果

### 法术位表

支持：全施法者（Wizard/Sorcerer/Cleric/Druid/Bard）、半施法者（Paladin/Ranger）、1/3 施法者（Eldritch Knight/Arcane Trickster）、Warlock 誓约槽。

多职业时自动合并计算施法者等级。

### 背包 & 货币

```
POST   /api/character/{id}/inventory              # 添加物品
DELETE /api/character/{id}/inventory/{item_id}    # 移除物品
PATCH  /api/character/{id}/inventory/{item_id}    # 修改（装备/卸下/数量）
POST   /api/character/{id}/currency               # 货币增减
```

### 版本历史

每次保存自动创建快照，最多保留 20 个历史版本，可回滚。

```
GET  /api/character/{id}/history
POST /api/character/{id}/history/{history_id}/restore
```

### DM 审批流程

1. 玩家提交非标准角色 → 后台广播 `dm_approval_request` 给 DM
2. DM 审批（通过/拒绝 + 备注）→ 广播 `dm_approval_result` 给玩家
3. 审批通过前角色不能参与战役

---

## 3. 怪物系统

### 数据库

- **现有数据**：1107 只怪物，来源：MM 2024（504）、MMotM（253）、Giants（69）、Planescape（39）等
- **字段**：名称（中/英）、体型、生物类型、阵营、AC、HP、HP公式、六维属性、豁免、技能、抗性/免疫、感官、行动（普通/传奇/巢穴）、CR、XP、来源

### 搜索

```
GET /api/monsters?q=地精           # 关键词搜索（中文名/英文名/生物类型）
GET /api/monsters?creature_type=亡灵&cr=5   # 按类型+CR筛选
GET /api/monsters?limit=50&offset=0        # 分页
```

返回格式：
```json
{ "monsters": [...], "total": 1107, "limit": 50, "offset": 0 }
```

### 导入

```
POST /api/monsters/import
Body: { "path": "D:/dnd-rules-ai/怪物图鉴2025", "source": "MM 2024", "overwrite": false }
```

支持两种 HTML 格式：
- 怪物图鉴2025 格式（`<div class="stat-block">`）
- DNDBeyond 字幕组格式（`<FONT color=#800000>`）

---

## 4. 战役系统

### 战役管理

```
POST   /api/campaign                    # 创建战役（需 X-Role: dm）
GET    /api/campaign/{id}               # 详情
GET    /api/campaign                    # 列表（可按 owner/player 范围过滤）
PUT    /api/campaign/{id}               # 更新
PATCH  /api/campaign/{id}/status        # 状态流转（planning→active→paused/completed）
DELETE /api/campaign/{id}
```

### 成员管理

```
POST   /api/campaign/{id}/invite           # 生成邀请码（可设最大使用次数/过期时间）
GET    /api/campaign/{id}/invite           # 查看有效邀请码
DELETE /api/campaign/{id}/invite/{code}    # 使邀请码失效
POST   /api/campaign/join/{code}           # 玩家用邀请码加入
POST   /api/campaign/{id}/players          # DM 直接添加玩家
DELETE /api/campaign/{id}/players/{id}     # 踢出玩家
POST   /api/campaign/{id}/characters/{id}  # 将角色绑定到战役
```

### DM 总览

```
GET /api/campaign/{id}/overview
```

返回：战役基本信息、所有角色状态（HP/AC/条件）、遭遇战地图列表、在场怪物列表、最近操作日志（20条）。

---

## 5. 地图系统

### 大地图（世界地图）

- 关联战役，记录战役发生的宏观地理
- **地点标注（POI）**：城市、地牢、遗迹、地标等，DM 可设置为隐藏（玩家不可见）
- **玩家位置追踪**：记录每个玩家当前所在 POI 或坐标
- **探索进度**：已访问地点列表，迷雾战争开关

```
POST /api/campaign/{id}/world-map/generate  # AI 生成大地图图片
POST /api/campaign/{id}/world-map/poi       # 添加地点标注
PATCH /api/campaign/{id}/world-map/progress # 更新玩家位置
```

### 遭遇战棋盘

- 网格地图（默认 20×20 格，每格 5 英尺）
- 每格可设置地形类型（开阔/困难地形/熔岩/水域等）
- 场上生物列表：位置（格坐标）、HP、状态异常、是否对玩家隐藏

```
POST /api/campaign/{id}/encounter-maps                        # 新建棋盘
POST /api/campaign/{id}/encounter-maps/{id}/generate-bg      # AI 生成背景图
POST /api/campaign/{id}/encounter-maps/{id}/simulate         # 初始化遭遇战（放置角色+怪物，掷先攻）
PATCH /api/campaign/{id}/encounter-maps/{id}/creatures       # 移动/更新生物
```

### 地图图片生成

三种后端（通过 `MAP_GENERATOR` 环境变量选择）：

| 后端 | 说明 | 要求 |
|---|---|---|
| `pillow`（默认）| 本地色块占位图 | 无 |
| `dalle` | DALL-E 3 高质量生成 | OpenAI API |
| `sdwebui` | Stable Diffusion 本地生成 | 本地 GPU + SD WebUI |

遭遇战地图生成后自动用 Pillow 叠加精确网格线（AI 生成的网格不精确）。

---

## 6. 游戏会话系统

### 会话快照

每次先攻顺序变更或场景切换时自动保存快照到数据库，服务重启后可恢复：
- 当前轮次编号
- 先攻列表（所有生物排列顺序）
- 当前行动者索引
- 活跃遭遇战地图 ID
- 场景描述

### 操作日志（OpLog）

追加式只增日志，记录每次游戏操作：

```
操作类型     payload 示例
roll        { "notation": "1d20", "result": 18, "reason": "先攻" }
hp_change   { "instance_id": "xxx", "delta": -8, "cause": "地精攻击" }
initiative  { "round": 1, "current_turn": 2, "entries_count": 4 }
scene_change { "encounter_map_id": "emap-xxx", "description": "矿坑入口" }
rest        { "rest_type": "short", "hp_gained": 5 }
```

用途：事后回放、DM 复盘、断线重连状态恢复。

---

## 7. WebSocket 实时通信

### 连接

```
ws://host:8000/ws/{campaign_id}?owner_id=Player1%230001&role=player
ws://host:8000/ws/{campaign_id}?owner_id=DM%23001&role=dm
```

### 连接时自动同步

新成员连接或重连时，服务器推送完整状态快照（SYNC）：
- 房间内所有成员列表
- 当前先攻顺序 + 轮次
- 活跃地图 ID + 生物位置（玩家看不到隐藏生物）
- 角色数据（玩家获得自己的角色，DM 获得全部）

### 消息类型

| 类型 | 方向 | 说明 |
|---|---|---|
| `join` / `leave` | S→C | 成员进出广播 |
| `sync` | S→C | 连接/重连全量状态同步 |
| `ping` / `pong` | 双向 | 心跳保活 |
| `chat` | C↔C | 频道聊天（广播） |
| `roll` | C→S | 掷骰请求 |
| `roll_result` | S→C | 掷骰结果广播 |
| `initiative_update` | DM→S | 更新先攻顺序 |
| `turn_advance` | DM→S | 推进到下一行动者 |
| `combat_start` / `combat_end` | DM→S | 战斗开始/结束 |
| `scene_update` | DM→S | 切换场景 |
| `creature_move` | DM→S | 移动棋盘生物（写入DB + 广播） |
| `creature_hp` | DM→S | 修改生物 HP |
| `condition_update` | DM→S | 施加/移除状态异常 |
| `death_save` | C→S | 死亡豁免（广播全员） |
| `character_update` | S→C | 角色数据变更推送 |
| `map_update` | S→C | 大地图变化推送 |
| `fog_update` | DM→S | 迷雾战争变更 |
| `poi_reveal` | DM→S | 向玩家揭示隐藏地点 |
| `rule_query` | C→S | 通过 WS 查询规则 |
| `rule_result` | S→C | 规则答案（仅发给提问者） |
| `npc_chat` | C→S | 与 NPC 对话 |
| `npc_response` | S→C | NPC 回复（LLM 生成） |
| `rest_complete` | S→C | 休息结束广播 |
| `dm_approval_request` | S→DM | 有角色待审批 |
| `dm_approval_result` | S→玩家 | 审批结果通知 |
| `loot_grant` | S→C | 战利品/XP 分配广播 |
| `xp_gain` | S→C | 经验获得通知 |

### DM 信息过滤

- `is_hidden=true` 的生物只广播给 DM
- 玩家 SYNC 时隐藏生物自动过滤

---

## 8. 骰子引擎

支持完整的 D&D 骰子表达式：

```
1d20          基本掷骰
2d6+3         带加值
4d6k3         掷4个d6取最高3个（建卡常用）
4d6kl1        取最低1个
1d20adv       优势（掷两次取高）
1d20dis       劣势（掷两次取低）
```

返回：总值、所有骰子结果、实际参与计算的骰子、修正值、可读分解（如 `[3,5,6](k3=14)+2=16`）。

---

## 9. 基础设施

### LLM 配置（`.env`）

```ini
# 规则问答生成（支持任意 OpenAI 兼容接口）
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 嵌入模型 API 兜底（本地模型失败时使用）
EMBEDDING_API_KEY=...
EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_MODEL=embedding-3
```

换模型只改 `.env`，代码无需修改。支持 OpenAI / DeepSeek / Ollama / LM Studio 等。

### 规则书导入 API

```
POST /api/rules/import/htm    # 从 HTM/HTML 文件导入
POST /api/rules/import/pdf    # 从 PDF 导入（基础支持）
POST /api/monsters/import     # 从 HTM 文件导入怪物手册
```

---

## 10. 数据库结构

单个 SQLite 文件（`dnd_rules.db`），11 张表：

| 表名 | 模块 | 说明 |
|---|---|---|
| `rule_chunks` | RAG | 规则知识库（2835 条） |
| `feedback` | RAG | 用户反馈 |
| `characters` | 角色 | 角色表（含软删除） |
| `character_history` | 角色 | 版本快照（每角色最多20条） |
| `monsters` | 怪物 | 怪物数据库（1107 只） |
| `campaigns` | 战役 | 战役信息 |
| `campaign_invites` | 战役 | 邀请码 |
| `game_sessions` | 会话 | 游戏状态快照 |
| `session_op_log` | 会话 | 操作流水日志 |
| `world_maps` | 地图 | 大地图 |
| `encounter_maps` | 地图 | 遭遇战棋盘 |

数据库路径通过 `SQLITE_PATH` 环境变量配置，默认为项目根目录 `dnd_rules.db`。

---

## 11. 联机方式

### 局域网 / Radmin VPN（推荐）

后端已绑定 `0.0.0.0`，无需任何配置改动。

```bash
python main.py   # 启动，监听 0.0.0.0:8000
```

- **局域网**：其他玩家用主机的局域网 IP 访问 `http://192.168.x.x:8000`
- **Radmin VPN**：主机创建虚拟网络，玩家安装后加入，使用 Radmin IP（`26.x.x.x`）访问

### 公网穿透（临时）

```bash
cloudflared tunnel --url http://localhost:8000   # 生成临时 HTTPS 域名
```

### 认证说明

当前使用基于 Header 的信任认证（`X-Owner-Id`、`X-Role`），适合 VPN 封闭网络内使用。若暴露至公网，需在前层添加访问控制。
