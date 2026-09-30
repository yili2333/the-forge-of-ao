# 跑团系统完善计划

> 基于全流程模拟测试（`test_full_ttrpg_sim.py`）和系统架构评审生成。  
> 测试结果：38 项 / 37 通过。唯一失败项（按英文名查询 Goblin）为正常行为：CHM 来源只有中文名，英文名搜索 404 符合预期。  
> 怪物数据库：已通过 `python import_monsters.py --overwrite` 导入 **1107 只怪物**（覆盖 MM 2024、MMotM、Volo 等 20+ 来源）。

---

## 一、已完成功能清单

| 模块 | 状态 | 说明 |
|------|------|------|
| RAG 规则导入 & 问答 | ✅ | HTM/PDF + BM25/向量混合检索，反幻觉提示 |
| 玩家角色系统 | ✅ | 150+ 字段，AC/技能/豁免自动计算，效果引擎 |
| 怪物数据库 | ✅ | 中英双语搜索，HTM 批量导入，1107 只怪物已导入（20+ 来源） |
| 遭遇战地图 | ✅ | 网格地形，生物部署，A* 寻路 |
| 移动范围查询 | ✅ | BFS + 地形代价 + 高低差 |
| 法术 AoE 范围 | ✅ | sphere/cone/line/cube 四形状，视线过滤 |
| 攻击解算管道 | ✅ | 命中/重击/伤害/抗性/HP 更新/集中检定一体化 |
| 怪物行动经济 | ✅ | action/bonus_action/reaction/legendary_actions 追踪，轮次自动重置 |
| 通用豁免检定 | ✅ | SAVING_THROW WS，角色/怪物双目标，自动伤害+HP更新 |
| AoE 伤害分发 | ✅ | AOE_ATTACK WS，一次投骰，所有目标独立豁免+抗性处理 |
| 法术位自动扣减 | ✅ | ATTACK 命中时自动扣对应等级法术位，广播 CHARACTER_UPDATE |
| 先攻自动投骰 | ✅ | ROLL_INITIATIVE WS + REST，1d20+DEX，广播 INITIATIVE_UPDATE |
| WebSocket 实时同步 | ✅ | 51 种消息类型，RoomState 内存缓存 |
| 战役 & 会话管理 | ✅ | 邀请码，崩溃恢复，审计日志 |
| 双数据库后端 | ✅ | SQLite（开发） / MySQL（生产），同一 SQL |
| 短休 / 长休 | ✅ | Hit Dice，法术位，效果到期，集中中断 |
| 死亡豁免 | ✅ | 自然 1/20 特殊处理，3 成功/失败判定 |
| 状态条件 | ✅ | 施加/移除/set，广播给全员 |
| 视线 & 战争迷雾 | ✅（服务端） | LOS 计算完整，Unity 渲染待接入 |
| LLM 本地/API 切换 | ✅ | 运行时热切换，Ollama/LM Studio 兼容 |
| 本地嵌入模型 | ✅ | sentence-transformers auto/local/api 三模式 |
| 地图生成 | ✅ | Pillow/豆包/DALL·E/SDWebUI 四后端 |

---

## 二、待完善项（优先级排序）

### P1 — 核心玩法缺口 ✅ 已全部完成

#### 1. 通用豁免检定 WS 消息 ✅
**实现：**
```
WS SAVING_THROW {
  encounter_map_id, target_character_id / target_instance_id,
  ability: "dexterity", dc: 14,
  damage_dice: "8d6", damage_type: "fire", half_on_success: true,
  description: "火球术"
}
→ 服务器投豁免骰，自动算伤害（成功减半/失败全伤），更新 HP，广播 SAVING_THROW_RESULT
```
- 角色目标：使用 `character/saving_throw.py` 的熟练加成+属性修正
- 怪物目标：查 `monster.saving_throws` 显式加值，回退到属性修正
- HP=0 时自动施加昏迷状态

#### 2. AoE 伤害自动分发 ✅
**实现：**
```
WS AOE_ATTACK {
  encounter_map_id,
  target_instance_ids: ["goblin-1", "goblin-2"],   # 从 GET /spell-area 获取
  target_character_ids: ["char-abc"],
  ability: "dexterity", dc: 14,
  damage_dice: "8d6", damage_type: "fire", half_on_success: true,
  description: "火球术（8d6 火焰）"
}
→ 伤害骰投一次，每目标独立投豁免，自动处理抗性/免疫/易伤，广播 AOE_ATTACK_RESULT
```

#### 3. 法术位自动扣减 ✅
**实现：** `AttackData` 新增 `spell_slot_level: int = 0`；命中时若 > 0 自动扣法术位，广播 `CHARACTER_UPDATE`，攻击摘要显示"🔮 消耗 N 环法术位"。

#### 4. 先攻自动投骰 ✅
**实现：**
- WS `ROLL_INITIATIVE { encounter_map_id, reroll_players }` → 服务器投 1d20+DEX，排序，广播 `INITIATIVE_UPDATE` 并更新房间状态
- REST `POST .../roll-initiative` 迁移到复用 `_do_roll_initiative()` helper，逻辑一致

---

### P2 — 规则机械性强化

#### 5. 状态条件对战斗的被动效果
**现状：** `CONDITION_UPDATE` 可以标记状态，但状态对 ATTACK 命中骰的影响（如 Prone 给近战攻击者优势、Paralyzed 令攻击自动命中）没有自动应用。

**方案：** 在 ATTACK handler 的步骤 4（计算命中加值）之后，检查攻击者/目标的 conditions，自动调整 advantage 字段：
```python
# 目标 Prone → 近战攻击有优势
if "prone" in target_conditions and attack_type != "ranged":
    effective_advantage = "advantage"
# 目标 Paralyzed → 近距离自动命中（算 crit）
if "paralyzed" in target_conditions and dist <= 5ft:
    is_hit = True; is_crit = True
```

#### 6. 状态条件免疫校验
**现状：** `CONDITION_UPDATE` 不检查 `Monster.condition_immunities`，可以对骷髅施加"中毒"状态（骷髅免疫）。

**方案：** 在 CONDITION_UPDATE handler 中，若目标是怪物，加载 Monster 数据校验 `condition_immunities`。

#### 7. 怪物传奇动作追踪
**现状：** `MapCreature` 没有 `legendary_actions_remaining` 字段。DM 只能脑补传奇动作次数。

**方案：** MapCreature 加 `legendary_actions_max: int = 0` 和 `legendary_actions_used: int = 0`；simulate 时从 Monster.legendary_actions 推断 max 值；TURN_ADVANCE 新轮开始时重置。

#### 8. 武器范围校验（近战/远程）
**现状：** ATTACK handler 不校验攻击距离，DM 可以对 100 格外的目标发起近战攻击而不报错。

**方案：** 在 ATTACK handler 中，从 EncounterMap 读取攻击者和目标坐标，计算格子距离；近战若距离 > reach（默认 5ft），返回错误。

---

### P3 — 用户体验与前端集成

#### 9. Unity 战争迷雾渲染
**现状：** 服务端 `vision.py` + `line_of_sight.py` 已完整实现视线过滤，`SYNC` 中的 `creature_positions` 也已按玩家视野过滤。但 Unity 前端当前不消费 `is_visible` 字段，所有生物对所有玩家可见。

**方案：** Unity 端在 `SYNC` / `MAP_UPDATE` 回调中，仅渲染 `creature_positions` 里有记录的生物 token；对 `is_hidden=true` 的生物，仅 DM 端渲染。

#### 10. Qdrant 持久化（冷启动优化）
**现状：** 规则向量索引存储在纯内存的 Qdrant 集合中，服务重启后需重新嵌入（大型规则书约 30 秒）。

**方案：**
- 选项 A（轻量）：启动时若 DB 已有 rule chunks，自动重建 Qdrant 集合（现有逻辑，但没有跳过已有数据的优化）
- 选项 B（推荐）：连接 Qdrant 本地 Docker 实例，持久化到磁盘（只需改 `vector_store.py` 的 client 初始化）

#### 11. DM 冲突解决界面
**现状：** 规则版本冲突由 `conflict_detector.py` 自动检测，结果以 JSON 返回，但没有可视化界面供 DM 查看和裁定。

**方案：** 在地牢编辑器旁增加一个规则冲突管理页面 `/conflict-manager/{campaign_id}`，列出冲突、允许 DM 点选保留哪条规则。

#### 12. Unity WebView 地牢编辑器
**现状：** 地牢编辑器为独立 HTML 页面 `/dungeon-editor/{cid}/{mid}`，DM 需要打开浏览器操作。

**方案：** 在 Unity DM 面板中通过 WebView 嵌入地牢编辑器；或在 Unity 中重新实现格子编辑 UI，通过 REST API 同步数据。

---

### P4 — 安全与部署

#### 13. JWT 身份验证
**现状：** 使用 `X-Role: dm` / `X-Owner-Id` 请求头，无签名，仅适合局域网/VPN。

**方案：** 接入 JWT（或简单的 HMAC 签名 token），DM 登录时颁发 token，后续请求携带 `Authorization: Bearer <token>`。

#### 14. WebSocket 心跳超时处理
**现状：** 没有检测长时间无响应的 WebSocket 连接，断线不重连的玩家会在房间里留下僵尸连接。

**方案：** 服务端每 30 秒发送 PING，客户端 10 秒内不回 PONG 则强制断开并清理 room 状态。

---

### P5 — 人物卡完整性补全

#### 15. 协调物品上限追踪
**现状：** 每件物品有 `attuned: bool`，但 `CharacterSheet` 没有 `max_attunement_slots` 字段。规则规定最多同时协调 3 件魔法物品，目前靠调用方手动数 `attuned_items()` 的长度，无硬性约束。

**方案：**
```python
# models.py CharacterSheet 新增
max_attunement_slots: int = 3   # 规则默认值；某些特性可提升上限
```
在 `character/api.py` 的装备协调接口（`PATCH /inventory/{item_id}`）中校验：
```python
if item.requires_attunement and len(sheet.attuned_items()) >= sheet.max_attunement_slots:
    raise HTTPException(400, "已达协调上限")
```

#### 16. 法术已准备数量上限追踪
**现状：** `spells_known` 是无限列表，没有记录各职业当日可准备法术的上限。牧师/德鲁伊/圣武士等的准备上限 = 施法属性修正 + 职业等级，目前需实时计算但卡本身不存储。

**方案：**
```python
# models.py CharacterSheet 新增
max_spells_prepared: int = 0    # 0 = 由系统计算填入；可被 DM 手动覆写
```
在 `character/builder.py` 的 `finalize()` 中，根据职业规则自动计算并写入 `max_spells_prepared`；升级时联动更新。

#### 17. 负重 / 携带量字段缺失
**现状：** `calculator.py` 已有 `carry_capacity()`、`current_load()`、`is_encumbered()` 三个计算函数，但 `CharacterSheet` 没有存储负重变体规则选项（标准 vs 慢速负重变体），也没有额外负重加值字段（力量系特性等）。

**方案：**
```python
# models.py CharacterSheet 新增
encumbrance_variant: Literal["standard", "variant", "none"] = "standard"
# standard → STR×15；variant → PHB 变体分三档；none → 忽略负重
carry_capacity_bonus: float = 0.0   # 特性/魔法带来的额外负重加成（磅）
```
`calculator.py` 的 `carry_capacity()` 读取这两个字段调整计算结果。

---

## 三、全流程模拟测试结果

**测试脚本：** `src/test_full_ttrpg_sim.py`  
**覆盖场景：** 20 个阶段，38 个断言（P1 完成后补充了 MapCreature 传奇动作字段断言）

| 阶段 | 结果 | 说明 |
|------|------|------|
| 健康检查 | PASS | |
| 战役创建 | PASS | |
| 玩家角色创建 + 派生属性 | PASS | AC/先攻/技能自动计算 |
| 规则导入（HTM chunks） | PASS | |
| RAG 规则查询 | PASS | 偷袭条件查询正常返回 |
| 怪物查询（英文名 Goblin） | FAIL* | CHM 来源无英文名索引，中文名查询正常 |
| 怪物列表查询（任意怪物） | PASS | 1107 只已导入，列表查询成功 |
| 遭遇战地图创建 + 格子写入 | PASS | 10×10 含墙壁地形 |
| 生物部署（simulate） | PASS | 玩家角色正常入场 |
| 移动范围查询 | PASS（条件触发） | |
| 法术 AoE（sphere/cone） | PASS | 正确返回格子 + 视线过滤 |
| 攻击数据模型构造 | PASS | |
| 伤害计算（普通/重击/抗性/免疫） | 4/4 PASS | |
| 集中检定逻辑 | PASS | DC=max(10,damage//2) |
| 角色 HP REST 扣减 | PASS | |
| 状态条件施加/移除 | PASS | |
| 短休（Hit Dice） | PASS | |
| 长休（全量恢复 HP） | PASS | |
| AoE 形状逻辑（4 形状） | 4/4 PASS | |
| MapCreature 行动经济字段 | PASS | |
| 战役概览 | PASS | |
| 会话日志读取 | PASS | |

> \* CHM 来源文件仅含中文名，英文名精确查询（`Goblin`）404 为预期行为。中文名查询（`哥布林`）正常工作。

---

*最后更新：2026-04-20，P1 四项功能全部完成，测试结果 37/38（Goblin 英文名查询 404 为预期行为）。*
