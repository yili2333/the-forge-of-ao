# BSAI301 — 演示文稿技术参考文档
# D&D Rules AI: Online Multiplayer TTRPG Platform

> **演示要求 / Presentation Format：** 10–12 分钟演示 + 5 分钟问答  
> **本文件用途：** 覆盖六个章节的完整技术参考——用于制作幻灯片、准备答辩及预测提问  
> **This file:** Complete technical reference for all six sections — for slides, Q&A prep, and anticipated questions

---

## 第一节 — 项目背景与问题陈述
## Section 1 — Background & Problem Statement

### 背景与情境 / Context

《龙与地下城》第五版（D&D 5e）等桌面角色扮演游戏（TTRPG）正经历全球性复兴，主要动力来自网络直播文化（Critical Role、Dimension 20）及新冠疫情推动的远程游戏转变。D&D 5e（2024 版）涵盖散布于多本官方规则书中的数百条规则、完整的角色管理体系，以及 4–6 名玩家与地下城主（DM）之间的实时协作游戏。

*Tabletop RPGs like D&D 5e are experiencing a global revival driven by streaming culture and remote play. D&D 5e (2024 edition) involves hundreds of rules spread across multiple official books, a full character management system, and real-time collaborative play between a DM and 4–6 players.*

### 核心痛点 / Pain Points

当前在线跑 D&D 需要同时使用 **5 个以上独立工具**，碎片化带来三大问题：

*Playing D&D online currently requires 5+ separate tools, causing three concrete problems:*

| 痛点 | 描述 | Pain Point | Description |
|------|------|-----------|-------------|
| 规则查询摩擦 | 在 PDF 中搜索"这里能触发偷袭吗？"需中断游戏 5–10 分钟 | Rule lookup friction | Pausing game 5–10 min to search PDFs for "can I sneak attack here?" |
| 角色管理负担 | 跨场次手动追踪 HP、法术位、集中、状态异常容易出错引发争议 | Character management | Manual cross-session tracking of HP, slots, concentration — error-prone and disputed |
| DM 认知过载 | DM 须同时管理怪物、地图、先攻、迷雾、叙事，没有一体化工具 | DM cognitive overload | No integrated tool for monsters, maps, initiative, fog-of-war, and narrative |

### 系统目标 / System Goal

构建一个**可自托管的开源后端（Python/FastAPI）+ Unity 前端**平台，使 DM 和最多 6 名玩家能在**单一系统内**完成完整的 D&D 5e 游戏，并配备一个**仅根据 DM 实际导入内容回答规则的 AI 助手**（严格禁止使用模型训练数据产生幻觉答案）。

*Build a self-hostable open-source backend (Python/FastAPI) + Unity frontend platform enabling a full D&D 5e session within a single system, with an AI assistant that answers rules questions **only** from imported content — never hallucinating from training data.*

---

## 第二节 — 系统概览
## Section 2 — System Overview

### 高层架构 / High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Unity 前端 / Unity Frontend                 │
│        角色 UI │ 战斗地图 │ 规则查询面板 │ DM 工具台            │
└─────────────────┬───────────────────────┬───────────────────────┘
                  │ REST (HTTP)            │ WebSocket
                  ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                FastAPI 后端  src/main.py  (~2500 行)             │
│                                                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────┐ ┌─────────────┐  │
│  │  角色路由   │ │  地图路由   │ │  怪物路由 │ │  导入路由   │  │
│  │ character/  │ │   maps/     │ │ monster/  │ │import_router│  │
│  └─────────────┘ └─────────────┘ └──────────┘ └─────────────┘  │
│  ┌─────────────────────────────┐  ┌────────────────────────────┐ │
│  │   战役/会话管理             │  │  WebSocket 管理器          │ │
│  │ campaign/ + session/        │  │  ws_manager + ws_models     │ │
│  └─────────────────────────────┘  └────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    RAG 管道 / RAG Pipeline                  │  │
│  │                                                            │  │
│  │  用户问题                                                  │  │
│  │    ↓ DnDTermMapper（中文↔英文术语标准化）                 │  │
│  │  EmbeddingService（本地/API 自动选择）                     │  │
│  │    ↓ 并行搜索                                              │  │
│  │  VectorStore (Qdrant内存)  ←→  KeywordStore (BM25+jieba)  │  │
│  │    ↓ RRF 倒数排名融合                                      │  │
│  │  交叉引用补全 → 版本冲突检测 → 上下文预算裁剪             │  │
│  │    ↓ LLM                                                   │  │
│  │  RuleAnswerGenerator（embedded/local/api 三模式）          │  │
│  │    ↓                                                       │  │
│  │  📜裁定结论 + 📖规则依据 + 💡补充说明 + 📋来源            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 持久化层 / Persistence Layer                │  │
│  │   db_helper.py（统一接口）                                 │  │
│  │   SQLite/aiosqlite（开发） ←→ MySQL/aiomysql（生产）       │  │
│  │   表：rule_chunks, characters, monsters,                   │  │
│  │        maps, campaigns, game_sessions, session_ops         │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 代码规模 / Codebase Size

| 模块 | 文件数 | 主要文件行数 |
|------|-------|------------|
| 后端总计 / Backend total | 55+ .py | ~18,000 行 / ~18,000 lines |
| main.py | 1 | 2,532 行 |
| ws_models.py | 1 | 717 行（54 种消息类型）|
| character/ | 17 | 含 150+ 字段模型、14 个功能模块 |
| maps/ | 12 | A*寻路、BFS移动范围、视线、迷雾 |
| 测试文件 / Tests | 11 | 覆盖 RAG、角色、地图、WebSocket、LLM |

---

## 第三节 — 功能演示
## Section 3 — Feature Demonstration

### 演示流程（推荐顺序，约 5 分钟）

#### ① 导入规则书 / Import Rulebook（30 秒）

**方式一：已有服务器文件**
```
POST /api/import/rules/htm
{ "path": "DND5e_chm-main/PHB2024", "source_name": "PHB 2024", "source_key": "PHB_2024" }
→ { "success": true, "chunks_created": 847, "conflicts_found": 0 }
```

**方式二：文件直传（新部署无书时）/ File Upload (new deployment)**
```
POST /api/import/rules/upload
multipart/form-data: file=PHB2024.htm
→ { "success": true, "detected_source": "PHB 2024", "chunks_created": 847 }
```

**方式三：目录自动扫描 / Directory Auto-Scan**
```
POST /api/import/rules/scan
{ "root_path": "D:/DND5e_chm-main", "dry_run": false }
→ { "books_found": 4, "books_imported": 4, "total_chunks": 2835 }
```

- HTML heading 自动切分为结构化规则块（847 块/本书）
- 自动分类：法术块、怪物属性块、通用规则
- 每块嵌入向量 → Qdrant + BM25 + SQLite 三重索引

#### ② 规则查询 / Rule Query（60 秒）

```
POST /api/query
{ "question": "游荡者能在一回合内使用两次偷袭吗？" }
```

**预期输出：**
```
📜 裁定结论：不能。偷袭每回合只能使用一次，而不是每次攻击一次。
📖 规则依据：[PHB 2024，游荡者，偷袭]
   "从1级起，你懂得如何悄然出击并利用敌人的分心。每回合一次，
    当你使用轻型武器、手弩、短弓或投掷武器进行攻击时……"
💡 补充说明："每回合一次"意味着即使有多次攻击，每回合也只能触发一次。
📋 引用来源：PHB 2024（游荡者，偷袭），第96页
置信度：0.91
```

演示要点："LLM 本身没有任何 D&D 知识——它只能读取我们实际导入的规则块。"

*Key point: "The LLM has zero D&D knowledge of its own — it can only read the rule chunks we actually imported."*

#### ③ 角色卡 / Character Sheet（60 秒）

```
POST /api/character → char-abc123
GET  /api/character/char-abc123/summary
```

```json
{
  "derived": {
    "ac": 16, "initiative": 3, "proficiency_bonus": 3,
    "skills": { "stealth": 9, "perception": 5, "athletics": 4 },
    "saving_throws": { "dexterity": 6, "constitution": 2 },
    "spell_save_dc": 15, "hp_max_effective": 38,
    "spell_stats_by_class": {
      "Wizard": { "dc": 15, "attack_bonus": 7, "ability": "intelligence" },
      "Cleric": { "dc": 14, "attack_bonus": 6, "ability": "wisdom" }
    }
  }
}
```

演示：修改能力值 → 所有依赖属性在**服务端**重新计算，客户端只负责展示。

*Modify an ability score → all derived stats recalculated on server-side. Client is display-only.*

#### ④ WebSocket 实时战斗（90 秒）

1. 两个客户端连接（DM + 玩家）
2. DM → `COMBAT_START` → 所有行动经济重置，第 1 轮开始
3. DM → `ROLL_INITIATIVE` → 服务器为所有生物自动投 1d20+DEX，广播排序后的先攻顺序
4. 玩家 → `ROLL {notation: "1d20+5", reason: "攻击"}` → 双端实时看到 `ROLL_RESULT`
5. DM → `ATTACK` → 服务器解算命中/伤害/重击/抗性/集中检定，广播 `ATTACK_RESULT`
6. DM → `AOE_ATTACK {spell: "Fireball"}` → 服务器投一次伤害骰，所有目标独立豁免，自动扣血
7. DM → `CREATURE_MOVE` → 生物移动；若离开敌方威胁范围触发 `OPPORTUNITY_ATTACK` 提示

#### ⑤ 战术地图移动范围（60 秒）

```
GET /api/campaign/{id}/encounter-maps/{mid}/movement-range
    ?creature_instance_id=goblin-1
```

返回速度（30 尺）内所有可达格子：
- `cost=5`：开阔地形（绿色）
- `cost=10`：困难地形（黄色）
- 同时支持 A* 寻路（`GET .../path`）——生物拖动时规划最优路径

---

## 第四节 — 工程亮点
## Section 4 — Engineering Highlights

### 4.1 技术栈 / Technology Stack

| 层次 | 技术 | 选型理由 |
|------|------|---------|
| **Web 框架** | FastAPI + uvicorn | 异步优先、自动 OpenAPI 文档、原生 WebSocket 支持 |
| **数据验证** | Pydantic v2 | 运行时类型安全、Settings 管理、序列化/反序列化 |
| **向量数据库** | Qdrant（内存模式） | 零外部依赖开发、生产切 Qdrant 服务器只需改一行 |
| **关键词搜索** | rank_bm25 + jieba | BM25 精确术语匹配 + 中文分词（纯 Python，无需服务） |
| **嵌入模型** | sentence-transformers bge-small-zh-v1.5 | 93MB、纯 CPU 可跑、中文优化 |
| **本地 LLM** | llama-cpp-python (Qwen2.5-7B Q4_K_M) | 无需 GPU、7B 参数、量化到 4GB 内存 |
| **API LLM** | OpenAI 兼容接口 | 可接 GPT-4o / 智谱 GLM / Ollama 任意后端 |
| **关系型数据库** | SQLite/aiosqlite (dev) + MySQL/aiomysql (prod) | 同一套代码、一行配置切换 |
| **实时通信** | FastAPI WebSocket | 54 种类型化消息、内存 RoomState 广播 |
| **规则解析** | BeautifulSoup4 + pdfminer | HTML heading 树切分 + PDF 文本提取 |
| **路径计算** | 自实现 A* + BFS | 切比雪夫启发函数（D&D 对角线规则）|
| **前端** | Unity (C#) | WebSocket + REST 集成，角色 UI + 战斗地图渲染 |

### 4.2 关键技术决策与权衡 / Key Technical Decisions & Trade-offs

#### 决策一：混合 RAG（向量 + BM25 + RRF）

**问题：** 纯向量搜索漏掉精确术语（"偷袭"），纯关键词搜索漏掉语义相近的表达。

*Problem: Pure vector search misses exact terms; pure keyword search misses paraphrased queries.*

**方案：** 并行双路检索，倒数排名融合（Reciprocal Rank Fusion）合并结果：

```python
# retriever.py — RRF 融合
def _reciprocal_rank_fusion(self, result_lists, weights, k=60):
    rrf_scores = {}
    for results, weight in zip(result_lists, weights):
        for rank, item in enumerate(results):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + weight / (k + rank + 1)
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
```

还有**查询预处理**：`DnDTermMapper` 将中文术语标准化为英文（"偷袭" → "Sneak Attack"），同时保留中文原词做双向搜索，大幅提升混合检索的召回率。

*Also query pre-processing: DnDTermMapper normalizes Chinese terms to English ("偷袭" → "Sneak Attack") while keeping the Chinese for dual-language retrieval.*

**权衡：** 搜索延迟 +2× (~50–200ms)，但检索精度显著提升。对于正确性优先的规则助手来说可以接受。

#### 决策二：双数据库后端（SQLite / MySQL）

**问题：** 开发者需要零配置本地环境；生产需要多用户并发。

```python
# db_helper.py — 统一接口
@asynccontextmanager
async def async_conn() -> AsyncIterator[DbConn]:
    if IS_MYSQL:
        raw = await aiomysql.connect(host=..., db=...)
    else:
        async with aiosqlite.connect(s.sqlite_path) as raw:
            ...

# fetchone() 始终返回 dict（而非 sqlite3.Row 或 tuple）
# 所有 SQL 使用 PH 占位符：SQLite="?", MySQL="%s"
# SQL COUNT(*) 必须加别名：SELECT COUNT(*) AS total
```

**工程细节：** `fetchone()` 封装为返回 `dict`，因此 `SELECT COUNT(*) FROM table` 必须写成 `SELECT COUNT(*) AS total FROM table`，否则整数下标访问会抛 `KeyError`——这是我们在测试中实际发现并修复的 bug。

*Engineering detail: fetchone() always returns dict, so COUNT(*) must use an alias. We found and fixed this during testing.*

**权衡：** 约 200 行额外抽象。收益：同一代码库通过一行 `.env` 配置在笔记本（SQLite）和服务器（MySQL）上无修改运行。

#### 决策三：内存 RoomState + 异步数据库持久化

**问题：** WebSocket 消息处理需微秒级访问先攻顺序和生物位置；每条消息都查询数据库（~10ms）太慢。

**方案：**
```
RoomState（Python 字典，进程内）          ← 每条 WS 消息读写，亚毫秒
  ├── initiative, current_turn, round_number
  ├── creature_positions                   ← 每次 CREATURE_MOVE 读取
  └── scene / fog_state                    ← SYNC 时发送

异步数据库写入（即发即忘）                  ← 状态更新后非阻塞持久化
  └── GameSession / SessionOpLog
```

崩溃恢复：新 WebSocket 连接时从数据库最新 `GameSession` 重建 `RoomState`。

*Crash recovery: rebuild RoomState from latest GameSession on reconnect.*

**权衡：** 服务器崩溃最多丢失一条消息的状态。对于爱好者工具可接受。

#### 决策四：动态上下文预算（防上下文溢出）

**问题：** 本地 LLM（Qwen2.5-7B，ctx=8192）若不裁剪直接填入所有检索结果会溢出上下文窗口，导致截断或乱码。API 模式（GPT-4o，128k）则有充裕空间。

**方案：** 按 LLM 模式动态计算可用字符预算：

```python
# generator.py
_CHARS_PER_TOKEN = 1.8   # 中英混合文本经验值
_FIXED_OVERHEAD  = 1200  # 系统提示 + 问题 + 格式标签
_MAX_OUTPUT = {"embedded": 800, "local": 1200, "api": 2000}

def _budget_chars(self) -> int:
    mode = get_active_mode()
    if mode == "api":
        return int(28000 * self._CHARS_PER_TOKEN)   # API 宽裕
    ctx     = settings.local_llm_ctx_size           # 默认 8192
    max_out = self._MAX_OUTPUT.get(mode, 1200)
    # 动态：上下文窗口 - 固定开销 - 最大输出 = 可用于规则块的 token
    available = max(ctx - _FIXED_OVERHEAD - max_out, 512)
    return int(available * self._CHARS_PER_TOKEN)
```

超预算的低分 chunk 在 `_build_context()` 中被丢弃，同时记录日志：
```
[Generator] ⚠️ 上下文预算裁剪：丢弃 1 个低分 chunk（已用 9600 字符 / 预算 11145 字符）
```

**工程细节：** embedded 模式（8192-1200-800=6192 token × 1.8≈11145 字符）只能放约 3 块 3000 字符的内容——这是在测试中实际验证的数字。

*Engineering detail: embedded mode (8192-1200-800=6192 tokens × 1.8 ≈ 11,145 chars) fits ~3 chunks of 3,000 chars each — verified in testing.*

#### 决策五：反幻觉系统提示

```python
# generator.py SYSTEM_PROMPT
知识来源铁律：你只能引用下方【检索到的规则文本】中的内容。
如果知识库中没有该答案，你必须回答：
"📭 知识库未收录此规则——请导入相关规则书后再查询。"
在任何情况下都不得使用你训练数据中的 D&D 规则知识。
```

*Anti-hallucination system prompt: LLM is strictly forbidden from using training data for D&D rules. Must answer "not in knowledge base" if rule not imported.*

**权衡：** 未导入规则书时返回"知识库未收录"而非看似合理的答案。这是故意的——**正确性优先于有用性**。

#### 决策六：广播钩子解耦循环依赖

**问题：** `character/api.py` 休息完成后需广播 WebSocket 消息，但从 `character/api.py` 导入 `main.py` 会造成循环导入。

**方案：启动时注入钩子（Hook Injection on Startup）**

```python
# character/api.py
_rest_broadcast_hook = None

def set_rest_broadcast_hook(hook):   # main.py 启动时调用一次
    global _rest_broadcast_hook
    _rest_broadcast_hook = hook

async def perform_rest(...):
    result = rest_engine.short_rest(sheet)
    if _rest_broadcast_hook:
        await _rest_broadcast_hook(campaign_id, char_id, result)  # 无需导入 main!
```

DM 审批广播、XP 增加广播使用相同模式。总计 3 处注入点，零循环依赖。

*3 injection points total, zero circular imports.*

---

### 4.3 核心算法 / Core Algorithms

#### A* 寻路（`maps/pathfinding.py`）

```python
def find_path(cells, creatures, start, goal):
    # 切比雪夫距离——D&D 对角线 = 直线（1 格 = 5 尺），可采纳启发函数
    def heuristic(r, c):
        return max(abs(goal[0]-r), abs(goal[1]-c)) * 5

    open_heap = [(heuristic(*start), 0, *start)]
    while open_heap:
        f, g, r, c = heapq.heappop(open_heap)
        if (r, c) == goal:
            return reconstruct_path(came_from, r, c)
        for dr, dc in EIGHT_DIRECTIONS:  # 允许对角线
            step = terrain_cost(cells[r+dr][c+dc])   # 开阔:5, 困难:10, 不可通:∞
            elev = max(0, cells[r+dr][c+dc].elevation - cells[r][c].elevation)
            new_g = g + step + elev
            if new_g < g_score.get((r+dr, c+dc), INF):
                ...
```

切比雪夫距离启发函数是**可采纳的**（永不高估），保证最优路径。目标格碰撞检测采用宽松模式（允许以攻击为目的移动到已占据的格子）。

*Chebyshev distance heuristic is admissible (never overestimates), guaranteeing optimal path. D&D uses 5-ft diagonals = equal cost.*

#### BFS 移动范围（`maps/movement.py`）

```python
def calculate_movement_range(cells, creatures, start, max_movement):
    visited = {start: 0}     # 格子 → 到达该格的最小开销
    queue = deque([(start, 0)])
    while queue:
        (r, c), cost = queue.popleft()
        for dr, dc in EIGHT_DIRECTIONS:
            step = terrain_cost(...) + elevation_gain_cost(...)
            new_cost = cost + step
            if new_cost <= max_movement and new_cost < visited.get((r+dr,c+dc), INF):
                visited[(r+dr, c+dc)] = new_cost
                queue.append(((r+dr, c+dc), new_cost))
    return [{"row":r,"col":c,"cost":cost,"terrain":t} for (r,c),cost in visited.items()]
```

BFS 保留到每格的**最小消耗路径**（而非第一条），确保返回的范围是最大可达区域。

#### 视线检测（`maps/line_of_sight.py`）

Bresenham 射线投射沿网格采样中间格子：
- 墙/完全遮蔽 → 视线阻断
- 半遮蔽 → 视线畅通，目标获得 +2 AC（掩护规则）
- 由 `maps/vision.py` 在 `SYNC` 消息中过滤每位玩家可见生物

#### 多职业施法统计（`character/calculator.py`）

```python
def spell_stats_by_class(sheet: CharacterSheet) -> dict:
    """
    为每个施法职业分别计算法术豁免 DC 和法术攻击加值。
    新增 spellcasting_abilities 字段支持多职业（每职业独立施法属性）。
    """
    result = {}
    pb = sheet.proficiency_bonus
    for cls, ability in sheet.spellcasting_abilities.items():
        mod = sheet.ability_scores.modifier(ability)
        result[cls] = {
            "dc":           8 + pb + mod,
            "attack_bonus": pb + mod,
            "ability":      ability.value,  # e.g. "intelligence"
        }
    return result
```

向后兼容旧版单职业角色卡（`spellcasting_ability` 单字段），自动填入 `"default"` 键。

*Backward-compatible with single-class sheets — auto-fills a "default" key.*

#### 集中检定（`character/concentration.py`）

```python
def on_damage_received(sheet, damage_taken):
    if not sheet.concentration_effect_id:
        return None   # 未集中，无需检定
    dc   = max(10, damage_taken // 2)   # D&D 5e 规则：DC = max(10, 伤害/2)
    roll = d20() + con_modifier(sheet) + (pb if con_save_proficient(sheet) else 0)
    if roll < dc:
        _break_concentration(sheet)
        return {"dc": dc, "roll": roll, "success": False}
    return {"dc": dc, "roll": roll, "success": True}
```

每当处理正在集中的角色的 `CREATURE_HP` 消息时自动触发，结果广播给所有玩家。

*Auto-triggered on every CREATURE_HP message for concentrating characters.*

---

### 4.4 后端模块清单 / Backend Module Reference

#### RAG 管道模块

| 文件 | 功能 |
|------|------|
| `embedding_service.py` | 自动选择嵌入模型：bge-small-zh（93MB）→ API 兜底；磁盘缓存避免重复计算 |
| `vector_store.py` | Qdrant 内存向量库；`upsert_chunk/delete_chunk/search`；按 campaign_id 过滤 |
| `keyword_store.py` | BM25Okapi + jieba 中文分词；增量 `add_chunk/remove_chunk`；重建索引 |
| `retriever.py` | 并行双路检索 → RRF 融合 → 交叉引用补全 → 优先级排序 |
| `generator.py` | 三模式 LLM（embedded/local/api）；动态上下文预算裁剪；反幻觉提示 |
| `term_mapper.py` | 中英 D&D 术语双向标准化（100+ 词条）；查询扩展 |
| `conflict_detector.py` | 检测同名规则的版本冲突（2024 > 2014 > SRD）；标记 superseded 状态 |

#### 角色系统模块（`character/`）

| 文件 | 功能 |
|------|------|
| `models.py` | CharacterSheet（150+ 字段）；ClassLevel；AbilityScores；InventoryItem |
| `calculator.py` | 全部派生属性计算（AC、先攻、技能、豁免、施法 DC、HP）；多职业施法统计 |
| `effects_engine.py` | 主动效果追踪（祝福/诅咒/变身等）；集中效果互斥；持续时间倒计时 |
| `rest_engine.py` | 短休/长休完整规则（HP 恢复、法术位重置、特性充能、疲竭等级） |
| `spell_slots.py` | 单职业/多职业法术位计算（含术士契约槽）；D&D 2024 版多职业表 |
| `multiclass_rules.py` | 多职业熟练项继承；法术位合并算法；主职业判断 |
| `concentration.py` | 集中法术检定；体质豁免自动投骰；失败时清除效果 |
| `damage.py` | 伤害类型解析；抗性/免疫/易伤应用；重击翻倍骰子 |
| `saving_throw.py` | 属性豁免完整计算（熟练、优势/劣势、效果加成） |
| `opportunity_attack.py` | 机会攻击触发检测（离开威胁范围）；战场上旧坐标追踪 |
| `rest_engine.py` + `level_up.py` | 升级 HP 增益；能力值提升；特性解锁 |
| `rule_bridge.py` | 角色状态 → RAG 查询上下文注入（"玩家是游荡者3级"→主题关键词） |
| `encounter_difficulty.py` | 遭遇战难度计算（XP 阈值/怪物数量乘数） |
| `builder.py` | 点数购买分配；标准阵列；背景加值；物种特性；角色创建流程 |

#### 地图系统模块（`maps/`）

| 文件 | 功能 |
|------|------|
| `models.py` | WorldMap / RegionMap / EncounterMap；MapCell（terrain/elevation/fog）；MapCreature（完整行动经济） |
| `storage.py` | 地图 CRUD；生物实例管理；先攻顺序持久化 |
| `generator.py` | 4 种背景图后端（Pillow 占位/AI 生图/URL/本地文件）|
| `pathfinding.py` | A* 最短路径；切比雪夫启发函数；障碍/生物碰撞 |
| `movement.py` | BFS 移动范围；困难地形/高度差开销；速度验证 |
| `collision.py` | 格子占用检测；生物尺寸（Tiny/Small/Large/Huge）|
| `line_of_sight.py` | Bresenham 射线投射；掩护等级计算 |
| `vision.py` | 每玩家可视范围计算；`SYNC` 消息生物过滤 |
| `spell_area.py` | AoE 形状（sphere/cone/line/cube）；范围内生物列举；视线过滤 |
| `dungeon_generator.py` | HTML Canvas 地牢编辑器（浏览器内标注地形网格）|

#### 导入模块

| 文件 | 功能 |
|------|------|
| `htm_processor.py` | HTML 规则书解析：heading 树切分、表格转文本、法术/怪物自动分类 |
| `pdf_processor.py` | PDF 规则书解析（pdfminer）：文本提取、段落分割、字体大小检测标题 |
| `import_router.py` | 统一导入入口：`/rules/htm`、`/rules/upload`（multipart）、`/rules/browse`、`/rules/scan` |
| `import_htm_books.py` | 批量导入预配置书目（BOOK_CONFIGS 字典）；已知来源自动映射 |
| `rule_importer.py` | 规则块写入三重索引（VectorStore + KeywordStore + SQLite）；冲突检测集成 |
| `conflict_detector.py` | 版本冲突检测：同名规则比较、`superseded_by` 关系建立 |

#### 实时通信模块

| 文件 | 功能 |
|------|------|
| `ws_models.py` | 54 种 Pydantic 消息类型；`WSMessage` 信封（type/sender/data/ts/msg_id）|
| `ws_manager.py` | `ConnectionManager`：连接注册/注销/广播；`RoomState`：内存游戏状态 |
| `main.py`（WS 处理器）| 每种消息类型的处理逻辑：攻击解算、先攻、行动经济、AoE、豁免检定 |

#### 基础设施模块

| 文件 | 功能 |
|------|------|
| `config.py` | Pydantic BaseSettings；`@lru_cache get_settings()`；所有功能开关 |
| `db_helper.py` | 统一异步数据库接口；`DbCursor.fetchone()` 返回 dict；`PH` 占位符抽象 |
| `db.py` | rule_chunks CRUD；`list_chunks_paginated`；`delete_chunk_by_id`；`update_chunk_status` |
| `dice.py` | 骰子表达式解析器（"2d6+4"、"4d6k3" 取高）；重击翻倍支持 |
| `user_identity.py` | Discord/TOML 身份解析；`owner_id` 稳定键生成 |

---

### 4.5 测试体系 / Testing Suite

| 测试文件 | 测试内容 | 关键断言 |
|----------|----------|---------|
| `test_character.py` | 角色创建、派生属性计算、多职业法术、存储 CRUD、软删除/恢复、效果引擎、变形、休息、升级、法术位、背包 | 100% 通过（包含多职业中英文术语适配）|
| `test_new_features.py` | 多职业施法统计、上下文预算裁剪、BM25 增删索引、db 分页/删除/状态更新、`_detect_source`、新 Pydantic 模型 | 62/62 通过 |
| `test_it.py` | 端到端 API 集成（规则导入→查询→置信度验证）| `"优势" in answer`；`confidence > 0.7` |
| `test_htm_processor.py` | HTML 规则书解析质量（标题层级、法术检测、表格）| 块数量、分类准确率 |
| `test_pdf_processor.py` | PDF 解析（文本提取、段落分割）| 块数量与内容完整性 |
| `test_full_flow.py` | 完整游戏会话 15 阶段：战役创建→角色→怪物→地图→战斗→查询 | 端到端无异常 |
| `test_full_ttrpg_sim.py` | TTRPG 全场景模拟（4 玩家1DM）| 先攻/攻击/豁免/休息/升级 |
| `test_campaign_session.py` | 战役+会话持久化、崩溃恢复、审计日志 | 重连后状态一致性 |
| `test_import_quality.py` | 规则块质量验证：数据完整性、检索质量、LLM 问答 | 召回率、答案包含关键词 |
| `test_local_model.py` | 本地嵌入模型：语义相似度、跨语言检索、速度基准 | 相似度阈值、延迟 |
| `test_full_flow_client.py` | WebSocket 客户端模拟（多连接并发）| 消息广播一致性 |

---

## 第五节 — 开发中遇到的困难与解决方案
## Section 5 — Challenges Encountered & Solutions

### 5.1 技术难题总结 / Technical Challenges

| 困难 | 根本原因 | 解决方案 |
|------|----------|---------|
| **BM25 在小语料库下 IDF=0** | rank_bm25 用 `log(N-n+0.5)-log(n+0.5)`，N=2、n=1 时两项相等，IDF=0，任何词得分都为 0 | 测试时保证索引至少 3 个文档；文档中记录该限制 |
| **中文 BM25 分词不稳定** | jieba 对 2 字词（如"偷袭"）在不同上下文下分词结果可能不一致 | 测试改用英文词；生产中用 `jieba.initialize()` 预热；加大语料库减少边缘效应 |
| **上下文窗口溢出** | 嵌入模式本地 LLM ctx=4096，检索 6 块内容就超限导致截断 | 实现动态 `_budget_chars()`，按模式算可用字符；ctx 默认改 8192；`retrieval_top_k` 降为 4 |
| **`fetchone()[0]` KeyError** | `db_helper.fetchone()` 返回 dict，`SELECT COUNT(*)` 的键是字符串 `"COUNT(*)"` 不是整数 `0` | 全部改写为 `SELECT COUNT(*) AS total`，用 `row["total"]` 访问 |
| **Pydantic `extra_forbidden` 启动崩溃** | Settings 类重写后漏加 `dnd5e_chm_dir` 字段，但 `.env` 有该变量 | 重新在 Settings 类中添加对应字段并设默认值 |
| **Git stash pop 冲突** | 远端删除了 `dnd_rules.db`，stash 试图恢复该文件 | `git rm --cached dnd_rules.db`，`git stash drop`，手动重建 |
| **MAPS_DIR 相对路径失效** | `Path("data/maps")` 依赖 CWD，从父目录启动服务器时路径错误，图片找不到 | 改为 `Path(__file__).parent.parent / "data" / "maps"`，绑定 `__file__` |
| **空地图网格阻断所有移动** | `can_occupy_cell_with_map()` 在 `cells=[]` 时调用 `is_valid_position()` 返回 False | 条件分发：有地图用带地图验证，无地图用简单验证 |
| **怪物速度字符串解析失败** | 速度存为自由文本 `"30尺，飞行60尺（悬浮）"`，战斗模拟器全部用默认值 30 | 用正则 `_parse_walk_speed()` 分段过滤飞行/游泳/攀爬词语，提取步行速度 |
| **机会攻击检测时旧坐标丢失** | 数据库更新后坐标已被新值覆盖，无法比较"离开了哪里" | 在 REST/WS 处理器中更新位置前捕获 `old_x, old_y = creature.x, creature.y` |
| **LLM 无视系统提示用训练数据作答** | 主流 LLM 在上下文充分的情况下仍倾向于用训练知识补充 | 系统提示中多次重复"铁律"措辞；测试时故意不导入规则书验证是否输出"知识库未收录" |
| **rule_bridge 中英文术语测试失败** | `_zh()` 将 "Rogue" 翻译为 "游荡者"，测试断言只检查英文 | 测试改为 `any(t in topics for t in ["Rogue", "游荡者", "盗贼"])` |
| **Unity 前后端合并冲突** | Unity 团队在 worktree 分支期间向 main 推送了 `Assets/` 变更 | `git fetch origin && git merge origin/main`——零冲突（文件树完全不相交）|

### 5.2 工程实践亮点 / Engineering Practice Highlights

#### API 契约先行 / Contract-First Development

在编写任何处理器之前，将所有 54 种 WebSocket 消息类型定义为 Pydantic 模型（`ws_models.py`），并将 REST API 完整记录在 `front.md` 中，使前后端并行开发无冲突。

*Defined all 54 WebSocket message types as Pydantic models and documented the full REST API in front.md before writing any handler — enabling parallel frontend/backend development.*

#### 单一配置源 / Single Source of Configuration

所有运行时参数通过 `config.py`（Pydantic BaseSettings + `@lru_cache`）管理。代码中**绝不**直接使用 `os.environ`。

```python
class Settings(BaseSettings):
    llm_mode: str = "api"           # 一行切换到本地 LLM
    database_type: str = "sqlite"   # 一行切换到 MySQL
    embedding_mode: str = "auto"    # auto/local/api
    local_llm_ctx_size: int = 8192
    retrieval_top_k: int = 4
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

#### 规则版本管理 / Rule Version Management

每个 `RuleChunk` 带有版本字段（`edition`、`status`、`superseded_by`、`supersedes`），支持 DM 完整的规则生命周期管理：

```
导入 → active
被新版覆盖 → superseded（自动检测）
DM 手动停用 → deprecated（PATCH /api/rules/{id}/status）
清理 → DELETE /api/rules/{id}
```

#### 新部署体验 / New Deployment Experience

无服务器端文件时，DM 可通过三种方式导入规则：
1. `/rules/upload` — 直传单文件（multipart/form-data）
2. `/rules/browse` + `/rules/scan` — 浏览/自动扫描本地目录
3. `/rules/htm` — 指定已有服务器路径

`_detect_source()` 自动识别目录名对应的规则来源（12 种模式匹配）。

---

## 第六节 — 局限性与后续步骤
## Section 6 — Limitations & Next Steps

### 当前局限性

| 局限 | 影响 | 说明 |
|------|------|------|
| **无 JWT 身份验证** | 只能在可信局域网/VPN 部署 | 基于 `X-Role: dm` 请求头；有意设计用于朋友圈场景 |
| **Qdrant 内存存储** | 重启后需 ~30 秒重新嵌入 | 约 2835 条规则；可接入 Qdrant 服务器实例 |
| **Unity 未渲染战争迷雾** | 玩家可看到所有生物 | 服务端视线逻辑完整；Unity 渲染待实现 |
| **地牢编辑器仅限浏览器** | DM 须打开浏览器标注地形 | Canvas HTML 页面；计划嵌入 Unity WebView |
| **无规则冲突 UI** | 冲突仅在 API 响应 JSON 中可见 | 检测逻辑完整；管理界面未开发 |

### 后续优先级 / Next Steps by Priority

| 优先级 | 功能 | 理由 |
|--------|------|------|
| P2 | Unity 战争迷雾渲染 | 服务端逻辑已完整，前端填补即可 |
| P2 | Qdrant 持久化快照 | 消除冷启动延迟 |
| P3 | JWT 身份验证 | 公网安全部署所必需 |
| P3 | Unity WebView 地牢编辑器 | 工具链一体化 |

---

## 附录：问答快速参考
## Appendix: Q&A Quick Reference

### 预期问题与答案 / Anticipated Questions & Answers

---

**Q: 系统如何防止 LLM 编造规则？**
**How does the system prevent the LLM from hallucinating rules?**

> **A（中）：** 两层机制：① 系统提示中的"铁律"明确禁止使用训练数据；② 检索时只将实际导入的规则块填入上下文，LLM 物理上看不到其他内容。我们通过故意不导入某些规则书后查询相关规则来验证——系统必须输出"📭 知识库未收录"而非捏造答案。  
> **A (EN):** Two layers: ① A "hard rule" in the system prompt explicitly forbids using training data. ② Only imported rule chunks are placed in context — the LLM physically cannot see anything else. We validated this by querying rules for intentionally un-imported books: the system must output "📭 not in knowledge base."

---

**Q: BM25 和向量搜索各自解决什么问题？**
**What does BM25 solve vs. vector search?**

> **A（中）：** 向量搜索捕捉语义（"如何减少伤害" → 找到"格挡"规则），但会漏掉精确术语（"偷袭"），因为术语的语义向量未必最接近规则块向量。BM25 精确匹配词语，补足向量检索的盲点。RRF 融合保留两者优势，并通过倒数排名防止单一来源主导结果。  
> **A (EN):** Vector search captures semantics ("how to reduce damage" → finds "Block" rule), but misses exact terms. BM25 does exact term matching, filling that gap. RRF fusion keeps both advantages; reciprocal ranking prevents either source from dominating.

---

**Q: BM25 的 IDF 为什么在语料库很小时会是 0？这有什么影响？**
**Why is BM25 IDF zero with small corpora? What's the impact?**

> **A（中）：** rank_bm25 的 BM25Okapi 用公式 `log(N-n+0.5) - log(n+0.5)`。当 N=2、n=1（2 个文档中有 1 个包含该词），两项都等于 `log(1.5)`，IDF=0，所有词得分均为 0。只有 N≥3 时 n=1 的 IDF 才为正。这是我们在写测试时发现的——最初用 2 个文档建索引，所有搜索都返回空结果。修复：初始化时至少用 3 个文档建索引。  
> **A (EN):** BM25Okapi uses `log(N-n+0.5) - log(n+0.5)`. With N=2, n=1, both sides equal `log(1.5)`, giving IDF=0 and zero score for all queries. Only with N≥3 does n=1 give positive IDF. We discovered this when writing tests — initial 2-doc corpus made all searches return empty. Fix: always seed with ≥3 documents.

---

**Q: 动态上下文预算是怎么工作的？为什么需要它？**
**How does the dynamic context budget work, and why is it needed?**

> **A（中）：** 本地 LLM（Qwen2.5-7B）默认上下文窗口 8192 token：系统提示+问题+格式约占 1200 token，输出保留 800 token，剩余 6192 token（约 11145 字符）用于规则块。如果 4 块内容共 12000 字符，超预算，最低分的那块被丢弃。API 模式（GPT-4o，128k context）预算宽裕，不裁剪。该逻辑在 `_build_context()` 中动态计算，会打印警告日志。  
> **A (EN):** Local LLM (Qwen2.5-7B) has 8192-token context: ~1200 for system prompt+question, ~800 reserved for output, leaving 6192 tokens (~11,145 chars) for rule chunks. If 4 chunks total 12,000 chars, the lowest-scored chunk is dropped. API mode (GPT-4o, 128k) has ample budget. Calculated dynamically in `_build_context()` with a warning log.

---

**Q: SQLite 和 MySQL 是怎么共存的？**
**How do SQLite and MySQL coexist?**

> **A（中）：** `db_helper.py` 提供统一的 `async_conn()` 上下文管理器和 `DbCursor`，`fetchone()`/`fetchall()` 始终返回 `dict`（两种后端统一行为）。所有 SQL 使用 `PH` 占位符变量（SQLite 为 `?`，MySQL 为 `%s`）。切换只需改 `.env` 中的 `DATABASE_TYPE`。  
> **A (EN):** `db_helper.py` provides a unified `async_conn()` context manager and `DbCursor` whose `fetchone()`/`fetchall()` always return `dict`. All SQL uses a `PH` placeholder variable (`?` for SQLite, `%s` for MySQL). Switching requires only changing `DATABASE_TYPE` in `.env`.

---

**Q: 多人实时同步是怎么实现的？**
**How does real-time multiplayer sync work?**

> **A（中）：** 所有客户端维持 WebSocket 长连接。服务器内存中的 `RoomState` 保存战斗状态（先攻、生物位置、场景），所有消息处理直接读写内存（亚毫秒）。状态变化后异步写入数据库（非阻塞）。广播时遍历同一 `campaign_id` 的所有连接。新连接时从数据库最新 `GameSession` 重建 `RoomState`（崩溃恢复）。  
> **A (EN):** All clients maintain persistent WebSocket connections. `RoomState` in memory holds combat state (initiative, positions, scene) — all message handling reads/writes memory (sub-millisecond). DB writes happen asynchronously after state changes. On reconnect, RoomState is rebuilt from the latest GameSession (crash recovery).

---

**Q: 切比雪夫距离是什么？为什么用它做 A* 启发函数？**
**What is Chebyshev distance and why use it as the A* heuristic?**

> **A（中）：** 切比雪夫距离 = `max(|Δrow|, |Δcol|)`，即对角线和直线移动代价相同。D&D 5e 规则规定对角线移动 = 1 格 = 5 尺（与水平/垂直相同）。欧几里得距离会惩罚对角线（√2 × 5 ≈ 7.07 > 5），导致高估代价、A* 不再最优。切比雪夫启发函数**可采纳**（永不高估实际代价），保证找到最短路径。  
> **A (EN):** Chebyshev distance = `max(|Δrow|, |Δcol|)` — diagonal = straight-line cost. D&D 5e states diagonal movement costs the same as orthogonal (1 square = 5 ft). Euclidean distance penalizes diagonals (√2 × 5 ≈ 7.07 > 5), overestimating cost and making A* non-optimal. Chebyshev is admissible (never overestimates), guaranteeing optimal paths.

---

**Q: 为什么不用 LangChain 或其他现成的 RAG 框架？**
**Why not use LangChain or another off-the-shelf RAG framework?**

> **A（中）：** 我们需要 D&D 特有的查询预处理（中英文术语标准化）、自定义战役隔离过滤、版本冲突检测和角色上下文注入——这些逻辑深度嵌入检索流程。LangChain 的抽象层会增加调试难度，而自实现使每个组件可独立测试（我们的测试文件也验证了这一点）。  
> **A (EN):** We needed D&D-specific query preprocessing (zh/en term normalization), custom campaign isolation filtering, version conflict detection, and character context injection — logic deeply embedded in the retrieval pipeline. LangChain's abstraction layer would complicate debugging; self-implementation lets each component be tested in isolation (as our test suite demonstrates).

---

**Q: 本地 LLM 如何工作？不用 GPU 能跑吗？**
**How does the local LLM work? Can it run without a GPU?**

> **A（中）：** 使用 `llama-cpp-python` 在进程内加载 Qwen2.5-7B-Instruct Q4_K_M GGUF 模型（~4GB）。CPU 可跑但慢（约 5–15 秒/回答）。设置 `GPU_LAYERS=-1` 时全部层卸载到 GPU（若有）。嵌入模型（bge-small-zh，93MB）纯 CPU 可实时运行。整个系统可在无互联网连接的笔记本上运行。  
> **A (EN):** Uses `llama-cpp-python` to load Qwen2.5-7B-Instruct Q4_K_M GGUF (~4GB) in-process. Runs on CPU (~5–15s/answer) or GPU with `GPU_LAYERS=-1`. Embedding model (bge-small-zh, 93MB) runs on CPU in real-time. The entire system can run on a laptop with no internet connection.

---

**Q: 项目最大的技术收获是什么？**
**What was the biggest technical lesson from this project?**

> **A（中）：** **接口契约先于实现**。在编写任何 WebSocket 处理器之前，我们将全部 54 种消息类型定义为 Pydantic 模型，并将 REST API 完整记录在 `front.md` 中。这使前后端完全并行开发，整个项目无合并冲突。另一个收获是**在真实测试之前不要假设库的行为**——BM25 IDF 和 `fetchone()` 返回类型都是"理所当然"的假设，只有写测试才发现了实际行为。  
> **A (EN):** **Interface contract before implementation.** We defined all 54 WebSocket message types as Pydantic models and documented the full REST API before writing any handler — enabling fully parallel frontend/backend development with zero merge conflicts. Another lesson: **never assume library behavior without real tests** — BM25 IDF=0 and fetchone() return type were "obvious" assumptions that only failed in actual tests.

---

*根据完整代码库分析和本次迭代开发经验生成 / Generated from full codebase analysis and this iteration's development experience*  
*最后更新 / Last updated: 2026-04-22*  
*已反映内容 / Reflects: P1 全部功能 + 规则管理端点 + 文件上传 + 目录扫描 + 动态上下文预算 + 多职业施法 + 完整测试修复*
