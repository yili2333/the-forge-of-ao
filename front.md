# D&D Rules AI — 前端开发指南

> 面向 Unity C# 客户端开发者  
> 后端地址：`http://<host>:8000`（局域网 / Radmin VPN）  
> 实时通信：WebSocket `ws://<host>:8000/ws/{campaign_id}`  
> 交互文档：`http://<host>:8000/docs`（Swagger UI，可直接在线测试所有接口）

---

## 目录

1. [认证方式](#1-认证方式)
2. [接口速查表](#2-接口速查表)
3. [关键数据结构](#3-关键数据结构)
4. [WebSocket 协议](#4-websocket-协议)
5. [典型游戏流程](#5-典型游戏流程)
6. [地图系统设计说明](#6-地图系统设计说明)
7. [开发建议](#7-开发建议)

> **最后更新：2026-04-21**  
> 新增：规则书文件夹扫描导入（`/browse` + `/scan`）、多职业施法 `spell_stats_by_class`

---

## 1. 认证方式

所有请求通过 HTTP Header 传递身份，**无需登录/Token**：

| Header | 说明 | 示例 |
|---|---|---|
| `X-Owner-Id` | 玩家唯一标识，写操作必须携带 | `Player1#0001` |
| `X-Owner-Display` | 显示名（建角色时可选） | `铁拳` |
| `X-Role` | `dm` 表示 DM 权限操作，不填视为普通玩家 | `dm` |

**C# 示例：**
```csharp
var request = UnityWebRequest.Post(url, jsonBody);
request.SetRequestHeader("X-Owner-Id", "Player1#0001");
request.SetRequestHeader("X-Role", "dm"); // DM 操作时加
request.SetRequestHeader("Content-Type", "application/json");
```

---

## 2. 接口速查表

### 🏥 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 服务存活检查，返回 `{"status":"ok"}` |

---

### 🧙 角色（前缀 `/api/character`）

#### 基础 CRUD

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/character` | 玩家 | 创建角色表 |
| `GET` | `/api/character/{id}` | 所有人 | 获取完整角色表 |
| `GET` | `/api/character/{id}/summary` | 所有人 | **UI 首选**：派生值速查（AC、先攻、技能、豁免等） |
| `PUT` | `/api/character/{id}` | Owner | 全量更新角色表 |
| `DELETE` | `/api/character/{id}` | Owner/DM | 软删除 |
| `GET` | `/api/character` | 所有人 | 列表（`?owner_id=`或`?campaign_id=`过滤）|
| `POST` | `/api/character/{id}/approve` | DM | 审批角色（`{"approved":true,"note":""}`) |
| `GET` | `/api/character/{id}/export` | 所有人 | 导出为 JSON |
| `POST` | `/api/character/import` | 玩家 | 从 JSON 导入 |

#### 成长

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/character/{id}/level-up` | Owner | 升级（见下方 Body 说明）|
| `POST` | `/api/character/{id}/respec` | Owner | 洗点重建，需 DM 批准 |
| `POST` | `/api/character/{id}/xp` | DM | 授予经验值 |

#### 战斗状态

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `PATCH` | `/api/character/{id}/hp` | Owner | HP 增减（`{"delta": -8}`，负为受伤）|
| `PATCH` | `/api/character/{id}/conditions` | Owner/DM | 增删状态异常 |
| `PATCH` | `/api/character/{id}/exhaustion` | Owner/DM | 修改疲惫等级 |
| `POST` | `/api/character/{id}/apply-effect` | Owner | 施加临时效果（Bless 等）|
| `DELETE` | `/api/character/{id}/effects/{effect_id}` | Owner/DM | 移除效果 |
| `POST` | `/api/character/{id}/polymorph` | DM | 变形术 |
| `POST` | `/api/character/{id}/polymorph/revert` | Owner | 解除变形 |
| `POST` | `/api/character/{id}/wish` | DM | 许愿术（永久修改属性）|

#### 法术

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/character/{id}/spells/prepare` | Owner | 准备法术 |
| `DELETE` | `/api/character/{id}/spells/prepare` | Owner | 取消准备 |
| `GET` | `/api/character/{id}/spells/prepare` | Owner | 已准备法术列表 |
| `POST` | `/api/character/{id}/cast-spell` | Owner | 施法（消耗法术位）|

#### 背包 & 货币

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/character/{id}/inventory` | Owner | 添加物品 |
| `DELETE` | `/api/character/{id}/inventory/{item_id}` | Owner | 移除物品 |
| `PATCH` | `/api/character/{id}/inventory/{item_id}` | Owner | 修改物品（装备/卸下/数量）|
| `POST` | `/api/character/{id}/currency` | Owner | 货币变动（`{"gold":50,"silver":-10}`) |

#### 休息

| 方法 | 路径 | Body | 说明 |
|---|---|---|---|
| `POST` | `/api/character/{id}/short-rest` | `{"hit_dice":["d10"]}` | 短休（消耗生命骰回血）|
| `POST` | `/api/character/{id}/long-rest` | `{}` | 长休（全回 HP/法术位）|

#### 历史 & 规则查询

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/character/{id}/history` | 历史版本列表（最多20条）|
| `POST` | `/api/character/{id}/history/{history_id}/restore` | 回滚到历史版本 |
| `POST` | `/api/character/{id}/ask` | 结合角色上下文查规则（LLM 回答）|

---

### 🐉 怪物（前缀 `/api/monsters`）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/monsters` | 列表检索（`?q=地精&creature_type=人形&cr=1`）|
| `GET` | `/api/monsters/{id}` | 完整怪物数据块 |
| `GET` | `/api/monsters/by-name/{name}` | 按中英文名精确查找 |
| `GET` | `/api/monsters/count` | 数据库总数 |

> 返回格式：`{"monsters":[...],"total":1107,"limit":50,"offset":0}`

---

### ⚔️ 战役（前缀 `/api/campaign`）

#### 战役 CRUD

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/campaign` | DM | 创建战役 |
| `GET` | `/api/campaign/{id}` | 所有人 | 详情 |
| `GET` | `/api/campaign` | 所有人 | 列表 |
| `PUT` | `/api/campaign/{id}` | DM | 更新 |
| `PATCH` | `/api/campaign/{id}/status` | DM | 状态变更 |
| `DELETE` | `/api/campaign/{id}` | DM | 删除 |

#### 成员管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/campaign/{id}/invite` | DM | 生成邀请码 |
| `GET` | `/api/campaign/{id}/invite` | DM | 查看邀请码 |
| `POST` | `/api/campaign/join/{code}` | 玩家 | 用邀请码加入 |
| `POST` | `/api/campaign/{id}/characters/{char_id}` | DM | 绑定角色到战役 |
| `DELETE` | `/api/campaign/{id}/players/{player_id}` | DM | 踢出玩家 |

#### DM 工具

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/campaign/{id}/overview` | DM 总览（角色/地图/怪物/日志）|
| `POST` | `/api/campaign/{id}/encounter-reward` | 分配战斗奖励（XP+战利品）|

---

### 🗺️ 地图（前缀 `/api/campaign/{id}/`）

> **重要**：`image_url` 字段均为 HTTP 可访问的路径（如 `/static/maps/world_abc123.png`），前端可直接用 `http://<host>:8000{image_url}` 加载图片。

#### 世界大地图

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `.../world-map` | 所有人 | 获取大地图（含 POI）|
| `POST` | `.../world-map/generate` | DM | AI 生成艺术图（见下方说明）|
| `POST` | `.../world-map/upload` | DM | 手动上传图片 |
| `PUT` | `.../world-map/prompt` | DM | 更新 AI 提示词（不生图）|
| `POST` | `.../world-map/poi` | DM | 添加兴趣点标注 |
| `PUT` | `.../world-map/poi/{poi_id}` | DM | 修改标注 |
| `DELETE` | `.../world-map/poi/{poi_id}` | DM | 删除标注 |
| `PATCH` | `.../world-map/progress` | 玩家 | 更新自己的位置 |

#### 区域地图（新增）

区域地图是世界地图与遭遇战地图之间的中间层，表示城镇、森林、地牢、海岸等具体地点。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `.../region-maps` | 所有人 | 列表（摘要）|
| `POST` | `.../region-maps` | DM | 创建区域地图 |
| `GET` | `.../region-maps/{mid}` | 所有人 | 详情 |
| `PUT` | `.../region-maps/{mid}/prompt` | DM | 修改 AI 提示词（不生图）|
| `GET` | `.../region-maps/presets` | 所有人 | 返回所有区域类型的预制提示词 |
| `POST` | `.../region-maps/{mid}/generate` | DM | AI 生成艺术图 |
| `DELETE` | `.../region-maps/{mid}` | DM | 删除 |
| `POST` | `.../region-maps/{mid}/poi` | DM | 添加兴趣点 |
| `DELETE` | `.../region-maps/{mid}/poi/{poi_id}` | DM | 删除兴趣点 |

区域类型（`region_type`）：`town` / `city` / `forest` / `dungeon` / `coast` / `mountain` / `plains` / `swamp` / `ruins` / `other`  
每种类型均有内置预制提示词，DM 可在创建时覆盖，也可事后通过 `/prompt` 端点修改。

#### 遭遇战棋盘

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `.../encounter-maps` | DM | 新建棋盘 |
| `GET` | `.../encounter-maps` | 所有人 | 棋盘列表 |
| `GET` | `.../encounter-maps/{mid}` | 所有人 | 棋盘详情（含生物位置）|
| `POST` | `.../encounter-maps/{mid}/generate-bg` | DM | AI 生成背景艺术图 |
| `POST` | `.../encounter-maps/{mid}/simulate` | DM | 初始化遭遇（放置生物+掷先攻）|
| `POST` | `.../encounter-maps/{mid}/creatures` | DM | 手动放置生物 |
| `PATCH` | `.../encounter-maps/{mid}/creatures` | DM | 移动/更新生物 |
| `DELETE` | `.../encounter-maps/{mid}/creatures/{iid}` | DM | 移除生物 |
| `POST` | `.../encounter-maps/{mid}/roll-initiative` | DM | 为场上生物掷先攻 |
| `GET` | `.../encounter-maps/{mid}/movement-range` | DM | BFS 可达格子（`?creature_instance_id=xxx`）|
| `GET` | `.../encounter-maps/{mid}/path` | DM | A* 寻路（`?from_x=&from_y=&to_x=&to_y=`）|
| `GET` | `.../encounter-maps/{mid}/dm-view` | DM | DM 视角（含隐藏生物）|

---

### 📦 统一导入（前缀 `/api/import`）

所有图片文件统一存储于 `data/maps/`，均通过 `/static/maps/` URL 访问。

#### 规则书导入

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/import/rules/upload` | DM | **直接上传文件**（HTM/HTML/PDF），新环境首选 |
| `GET` | `/api/import/rules/browse` | DM | 浏览服务器目录（服务器有资源时用）|
| `POST` | `/api/import/rules/scan` | DM | 扫描服务器文件夹并自动导入（服务器有资源时用）|
| `POST` | `/api/import/rules/htm` | DM | 指定服务器路径或提交预解析 chunks 导入 |
| `POST` | `/api/import/rules/pdf` | DM | 指定服务器路径或提交预解析 chunks 导入 |
| `POST` | `/api/import/rules/custom` | DM | 导入 DM 手写 Homebrew 规则条目（JSON）|
| `POST` | `/api/import/monsters` | DM | 从 HTM 目录批量导入怪物数据 |

#### 地图图片上传

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/api/import/map-bg/{campaign_id}/{map_id}` | DM | 上传遭遇战地图背景图（multipart/form-data）|
| `POST` | `/api/import/region-map-bg/{campaign_id}/{map_id}` | DM | 上传区域地图背景图（multipart/form-data）|

> 旧路径 `/api/rules/import/htm` 和 `/api/rules/import/pdf` 保留向后兼容，但不出现在 Swagger 文档中。

---

### 📂 规则书扫描导入（推荐工作流）

DM 首先通过 **browse** 导航到规则书所在目录，确认后用 **scan** 一键导入。

#### 第一步：浏览目录

```
GET /api/import/rules/browse?path=D:/dnd-rules-ai/DND5e_chm-main
```

响应：
```json
{
  "current_path": "D:/dnd-rules-ai/DND5e_chm-main",
  "parent_path": "D:/dnd-rules-ai",
  "entries": [
    { "name": "玩家手册2024", "path": "D:/.../玩家手册2024", "is_dir": true, "htm_count": 42, "pdf_count": 0 },
    { "name": "城主指南2024", "path": "D:/.../城主指南2024", "is_dir": true, "htm_count": 38, "pdf_count": 0 },
    { "name": "自定义规则",   "path": "D:/.../自定义规则",   "is_dir": true, "htm_count": 5,  "pdf_count": 2 }
  ],
  "total_htm": 0,
  "total_pdf": 0
}
```

- `path` 为空时默认返回 `.env` 里 `DND5E_CHM_DIR` 指向的目录
- 前端可用面包屑导航（点 `parent_path` 返回上级）

#### 第二步：预览（dry_run）

```json
POST /api/import/rules/scan
{
  "root_path": "D:/dnd-rules-ai/DND5e_chm-main",
  "dry_run": true
}
```

响应（不写入数据库，仅预览匹配结果）：
```json
{
  "success": true,
  "root_path": "D:/dnd-rules-ai/DND5e_chm-main",
  "books_found": 3,
  "books_imported": 0,
  "total_chunks": 0,
  "dry_run": true,
  "results": [
    { "subdir": "玩家手册2024", "detected_source": "PHB 2024", "detected_name": "玩家手册 2024", "files_found": 42, "skipped": true, "skip_reason": "dry_run 模式，未实际写入" },
    { "subdir": "城主指南2024", "detected_source": "DMG 2024", "detected_name": "城主指南 2024", "files_found": 38, "skipped": true, "skip_reason": "dry_run 模式，未实际写入" },
    { "subdir": "自定义规则",   "detected_source": "Homebrew", "detected_name": "自定义规则",   "files_found": 7,  "skipped": true, "skip_reason": "dry_run 模式，未实际写入" }
  ],
  "message": "扫描完成：发现 3 个目标（dry_run，未写入）"
}
```

#### 第三步：正式导入

```json
POST /api/import/rules/scan
{
  "root_path": "D:/dnd-rules-ai/DND5e_chm-main",
  "check_conflicts": true,
  "dry_run": false
}
```

**自动来源识别规则（按目录名关键词）：**

| 目录名包含 | 自动识别为 |
|---|---|
| 玩家手册 / phb / player | PHB 2024 |
| 城主指南 / dmg / dungeon master | DMG 2024 |
| 怪物图鉴 / mm / monster | MM 2024 |
| 基础规则 / basic rules | Basic Rules 2024 |
| srd | SRD 5.1 (2014) |
| 其他任意名称 | Homebrew |

`source_override` 字段可强制所有子目录使用同一来源（适合整本书是单目录的情况）。

### 📤 文件直传导入（新环境 / 客户端有文件时）

当服务器上没有预置规则资源目录时（例如云部署、新成员的机器），前端可直接上传文件：

```
POST /api/import/rules/upload?source_key=auto
Content-Type: multipart/form-data
X-Role: dm

file=<二进制文件内容>
```

- 支持 `.htm` / `.html` / `.pdf`
- `source_key=auto`（默认）：根据文件名自动识别官方书目，识别不了归入 Homebrew
- 文件处理完成后临时副本自动删除，不占用服务器空间

**C# 示例：**
```csharp
public async Task ImportRuleFile(string filePath, string sourceKey = "auto")
{
    byte[] fileBytes = File.ReadAllBytes(filePath);
    string fileName = Path.GetFileName(filePath);

    var form = new WWWForm();
    form.AddBinaryData("file", fileBytes, fileName, "application/octet-stream");

    string url = $"http://{host}:8000/api/import/rules/upload?source_key={sourceKey}";
    var req = UnityWebRequest.Post(url, form);
    req.SetRequestHeader("X-Role", "dm");

    await req.SendWebRequest();
    var result = JsonConvert.DeserializeObject<UploadImportResponse>(req.downloadHandler.text);
    Debug.Log($"导入完成：{result.message}");
}
```

响应：
```json
{
  "success": true,
  "filename": "玩家手册2024.htm",
  "detected_source": "PHB 2024",
  "detected_name": "玩家手册 2024",
  "chunks_created": 312,
  "conflicts_found": 0,
  "errors": [],
  "message": "成功导入《玩家手册 2024》：312 条规则"
}
```

**两种方式的使用场景对比：**

| 场景 | 推荐方式 |
|---|---|
| 新环境、DM 本地有规则书文件 | `POST /upload`（直接上传）|
| 服务器上已有 CHM 资源目录 | `GET /browse` → `POST /scan` |
| 只想加几条自定义规则 | `POST /rules/custom`（直接写 JSON）|

---

### 📖 规则查询

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/query` | 纯规则查询（`{"question":"战士几级获得额外攻击"}`) |
| `POST` | `/api/character/{id}/ask` | 带角色上下文查询 |
| `POST` | `/api/rules/import` | 导入自定义 homebrew 规则 |

---

### 🗂️ 规则库管理（DM 清理 / 维护）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/api/rules` | 所有人 | 列出规则库内容，支持按来源/状态/关键词过滤 |
| `PATCH` | `/api/rules/{id}/status` | DM | **禁用/恢复**单条规则（不删除，推荐替代删除）|
| `DELETE` | `/api/rules/{id}` | DM | 永久删除单条规则 |
| `DELETE` | `/api/rules/source/{source}` | DM | 删除某个来源的所有规则（批量）|
| `DELETE` | `/api/rules/campaign/{id}` | DM | 删除某战役的所有自定义规则 |

**列表查询参数：**
```
GET /api/rules?source=PHB 2014&status=active&keyword=偷袭&limit=50&offset=0
```

| 参数 | 说明 |
|---|---|
| `source` | 按来源过滤（PHB 2024 / PHB 2014 / Homebrew 等）|
| `status` | active（生效）/ deprecated（已禁用）/ superseded（被取代）|
| `category` | 按规则分类过滤 |
| `keyword` | 在标题和内容中模糊搜索 |

**禁用 vs 删除的区别：**

| 操作 | 是否可恢复 | 规则数据 | 检索行为 |
|---|---|---|---|
| `PATCH .../status` → `deprecated` | ✅ 随时恢复 | 保留在数据库 | 不再被检索到 |
| `DELETE .../rules/{id}` | ❌ 不可撤销 | 永久删除 | 不再被检索到 |

**推荐工作流：**
```
1. GET /api/rules?source=PHB 2014        → 查看哪些是 2014 版规则
2. PATCH /api/rules/{id}/status          → {"status": "deprecated"} 先禁用测试
3. 测试几场后确认没问题
4. DELETE /api/rules/source/PHB%202014   → 确认无误后批量永久删除
```

---

### 💾 会话日志

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/campaign/{id}/sessions/latest` | 最新会话（用于断线重连恢复）|
| `GET` | `/api/session/{sid}/log` | 操作流水（复盘/历史回放）|

---

## 3. 关键数据结构

### `/api/character/{id}/summary` 响应（UI 渲染主要数据源）

```json
{
  "sheet": { /* 完整角色表，字段见下 */ },
  "derived": {
    "total_level": 1,
    "proficiency_bonus": 2,
    "ability_modifiers": {
      "strength": 2, "dexterity": 1, "constitution": 2,
      "intelligence": 0, "wisdom": 1, "charisma": -1
    },
    "ac": 16,
    "initiative": 1,
    "passive_perception": 11,
    "passive_investigation": 10,
    "passive_insight": 11,
    "saving_throws": {
      "strength": 4, "dexterity": 1, "constitution": 4,
      "intelligence": 0, "wisdom": 1, "charisma": -1
    },
    "skills": {
      "acrobatics": 1, "athletics": 4, "perception": 3
      /* 全18项 */
    },
    "spell_save_dc": null,        /* 非施法者为 null；主施法职业 DC（向后兼容） */
    "spell_attack_bonus": null,   /* 主施法职业攻击加值（向后兼容） */
    "spell_stats_by_class": {     /* 多职业施法时按职业分别返回 */
      "Wizard":  { "dc": 15, "attack_bonus": 7, "ability": "intelligence" },
      "Cleric":  { "dc": 14, "attack_bonus": 6, "ability": "wisdom" }
    },
    "carry_capacity": 225,
    "current_load": 0,
    "encumbered": false,
    "exhaustion_penalty": 0,
    "hp_max_effective": 12,
    "speed_effective": 30
  },
  "context_text": "【角色】铁拳·斯通\n物种: Human\n职业: Fighter Lv1..."  /* 纯文本摘要，可直接显示 */
}
```

### 角色表关键字段（`sheet`）

```json
{
  "id": "char-abc123",
  "name": "铁拳·斯通",
  "owner_id": "Player1#0001",
  "campaign_id": "camp-xxx",
  "edition": "2024",
  "species": { "name": "Human" },
  "background": { "name": "Soldier" },
  "class_levels": [
    { "class_name": "Fighter", "level": 1, "hit_die_size": 10, "subclass": null }
  ],
  "ability_scores": {
    "strength": 16, "dexterity": 12, "constitution": 15,
    "intelligence": 10, "wisdom": 13, "charisma": 8
  },
  "hit_points": {
    "current": 12, "maximum": 12,
    "death_saves": { "successes": 0, "failures": 0 }
  },
  "spell_slots": { "1": 2, "2": 0 },
  "spell_slots_used": { "1": 1, "2": 0 },
  "conditions": ["poisoned"],
  "active_effects": [
    {
      "id": "eff-uuid",
      "name": "Bless",
      "source": "spell:Bless",
      "attack_bonus": 2,
      "concentration": true,
      "duration_type": "concentration"
    }
  ],
  "inventory": [
    {
      "id": "item-uuid",
      "name": "Chain Mail",
      "item_type": "armor",
      "equipped": true,
      "quantity": 1,
      "weight": 55.0,
      "cost_gp": 75
    }
  ],
  "currency": { "cp": 0, "sp": 0, "ep": 0, "gp": 50, "pp": 0 },
  "exhaustion_level": 0,
  "dm_approved": true,
  "version": 3
}
```

### 升级请求

```json
POST /api/character/{id}/level-up
{
  "class_name": "Fighter",
  "hp_method": "average",       // "average" | "roll"
  "asi_choice": { "strength": 2 },   // 4/8/12/16/19级时填，否则 null
  "subclass": "Champion"             // 选择子职业时填，否则 null
}
```

### 遭遇战模拟请求（支持精细调整）

```json
POST /api/campaign/{id}/encounter-maps/{mid}/simulate
{
  "player_character_ids": ["char-abc", "char-def"],
  "extra_monsters": [
    {
      "monster_id": "monster-uuid",
      "count": 3,
      "hp_override": null,       // 固定 HP（null = 使用怪物默认）
      "hp_multiplier": 1.5,      // HP 倍率（精英遭遇用）
      "ac_override": null,       // 固定 AC
      "speed_override": null,    // 固定移动速度（英尺）
      "name_prefix": "精英",     // 名称前缀，如"精英地精"
      "is_hidden": false,        // 是否对玩家隐藏
      "conditions": []           // 初始状态异常
    }
  ]
}
```

### 遭遇战棋盘生物（`MapCreature`）

```json
{
  "instance_id": "creature-uuid",
  "name": "精英地精老大",
  "monster_id": "monster-uuid",
  "character_id": null,
  "x": 5, "y": 3,
  "hp_current": 31, "hp_max": 31,
  "conditions": [],
  "is_hidden": false,
  "is_player": false,
  "initiative": 14,
  "speed": 30,
  "movement_used": 0,           // 本回合已消耗移动力（英尺）
  "action_used": false,
  "bonus_action_used": false,
  "reaction_used": false,
  "legendary_actions_max": 3,   // 传奇动作总点数（无传奇动作的怪物为 0）
  "legendary_actions_used": 0   // 本轮已消耗传奇动作点数
}
```

### 区域地图（`RegionMap`）

```json
{
  "id": "rmap-abc1234567",
  "campaign_id": "camp-xxx",
  "name": "幽暗森林",
  "description": "玩家初次进入时的区域",
  "region_type": "forest",
  "area_km": 5.0,
  "image_url": "/static/maps/region_a1b2c3d4.png",  // 直接可用的 HTTP URL
  "image_prompt": "Fantasy RPG forest regional map...",  // DM 可随时修改
  "pois": [
    { "id": "poi-uuid", "name": "古老石圈", "x": 45.0, "y": 30.0, "poi_type": "landmark" }
  ],
  "parent_world_map_id": "wmap-xxx",  // 关联世界地图（可选）
  "parent_poi_id": "poi-yyy"          // 对应世界地图上哪个 POI（可选）
}
```

---

## 4. WebSocket 协议

### 连接

```
ws://<host>:8000/ws/{campaign_id}?owner_id=Player1%230001&role=player
ws://<host>:8000/ws/{campaign_id}?owner_id=DM%23001&role=dm
```

> `#` 在 URL query 中需编码为 `%23`

### 消息格式

所有消息均为 JSON：

```json
{
  "type": "roll",
  "sender": "Player1#0001",
  "data": { /* 消息体，按 type 不同 */ },
  "ts": "2026-04-16T12:00:00",
  "msg_id": "a3f9b2c1"
}
```

### C# 连接示例

```csharp
using NativeWebSocket;  // 推荐: NativeWebSocket 或 WebSocketSharp

public class GameClient : MonoBehaviour
{
    private WebSocket _ws;
    private string _baseUrl = "ws://26.0.0.1:8000";

    async void Connect(string campaignId, string ownerId, bool isDm)
    {
        string role = isDm ? "dm" : "player";
        string encodedId = Uri.EscapeDataString(ownerId);
        string url = $"{_baseUrl}/ws/{campaignId}?owner_id={encodedId}&role={role}";
        
        _ws = new WebSocket(url);
        _ws.OnOpen += () => Debug.Log("WS Connected");
        _ws.OnMessage += (bytes) => OnMessage(Encoding.UTF8.GetString(bytes));
        _ws.OnError += (e) => Debug.LogError($"WS Error: {e}");
        _ws.OnClose += (code) => Debug.Log($"WS Closed: {code}");
        
        await _ws.Connect();
    }

    void OnMessage(string raw)
    {
        var msg = JsonConvert.DeserializeObject<WSMessage>(raw);
        switch (msg.type)
        {
            case "sync":               HandleSync(msg.data); break;
            case "roll_result":        HandleRollResult(msg.data); break;
            case "creature_move":      HandleCreatureMove(msg.data); break;
            case "creature_hp":        HandleCreatureHp(msg.data); break;
            case "character_update":   HandleCharUpdate(msg.data); break;
            case "initiative_update":  HandleInitiative(msg.data); break;
            case "rest_complete":      HandleRest(msg.data); break;
            case "opportunity_attack": HandleOpportunityAttack(msg.data); break;
            case "reaction_used":      HandleReactionUsed(msg.data); break;
        }
    }
}
```

### 重要消息列表

#### 连接成功时服务器推送 `sync`

```json
{
  "type": "sync",
  "data": {
    "members": [{"owner_id":"DM#001","is_dm":true,"display_name":"DM"}],
    "initiative": [
      {"instance_id":"char-abc","name":"铁拳","initiative":18,"is_player":true,"hp_current":12,"hp_max":12}
    ],
    "current_turn": 0,
    "round_number": 1,
    "active_encounter_map_id": "emap-xxx",
    "creature_positions": {
      "char-abc": {"x":1,"y":1,"hp_current":12,"hp_max":12,"is_player":true,"name":"铁拳"}
    },
    "character_snapshot": { /* 玩家自己的完整角色表 */ },
    "all_characters": []    // DM 专属：全部角色摘要
  }
}
```

#### 掷骰

```json
// 客户端 → 服务器
{ "type": "roll", "data": { "notation": "1d20+3", "reason": "攻击检定" } }

// 服务器 → 全房间
{
  "type": "roll_result",
  "data": {
    "notation": "1d20+3", "total": 18,
    "rolls": [15], "kept": [15], "modifier": 3,
    "breakdown": "[15]+3=18", "reason": "攻击检定"
  }
}
```

#### 生物移动（DM 操作）

```json
// DM → 服务器
{ "type": "creature_move", "data": { "instance_id": "creature-uuid", "x": 5, "y": 3 } }
// 服务器写入 DB 后广播，若触发机会攻击则额外广播 opportunity_attack
```

#### 机会攻击触发（服务器 → 全员）

```json
{
  "type": "opportunity_attack",
  "data": {
    "encounter_map_id": "emap-xxx",
    "attacker_instance_id": "goblin-1",
    "attacker_name": "地精",
    "mover_instance_id": "char-abc",
    "mover_name": "铁拳",
    "attacker_is_player": false
  }
}
```

> 前端收到此消息后，应弹出提示让 DM 决定是否发动机会攻击（执行攻击则额外发一次伤害 WS 消息）。

#### 专注法术施放

```json
// 客户端 → 服务器
{
  "type": "cast_concentration_spell",
  "data": {
    "character_id": "char-abc",
    "effect_id": "eff-uuid",     // 必须已存在于 active_effects
    "spell_name": "Bless"
  }
}
// 服务器自动打破旧专注，设置新专注，广播 character_update
```

#### 反应已使用

```json
// 客户端 → 服务器
{ "type": "reaction_used", "data": { "character_id": "char-abc", "reason": "护盾法术" } }
// 服务器设置 reaction_used=true，广播 character_update
```

#### 先攻更新

```json
{
  "type": "initiative_update",
  "data": {
    "entries": [
      {"instance_id":"char-abc","name":"铁拳","initiative":18,"is_player":true},
      {"instance_id":"goblin-1","name":"地精","initiative":12,"is_player":false}
    ],
    "current_turn": 0,
    "round_number": 1
  }
}
```

#### 规则查询（通过 WS）

```json
// 客户端 → 服务器
{ "type": "rule_query", "data": { "question": "暗袭什么时候触发" } }
// 服务器 → 仅发给提问者
{ "type": "rule_result", "data": { "answer": "📜 裁定结论...", "confidence": 0.9 } }
```

#### 一键投先攻（DM → 服务器，服务器广播 initiative_update）

```json
// DM → 服务器
{
  "type": "roll_initiative",
  "data": {
    "encounter_map_id": "emap-xxx",
    "reroll_players": false   // true = 同时重掷已有先攻的玩家角色
  }
}
// 服务器 → 全员（等同于 initiative_update）
{
  "type": "initiative_update",
  "data": {
    "entries": [
      {"id":"char-abc","name":"铁拳","initiative":18,"is_player":true},
      {"id":"goblin-1","name":"地精","initiative":12,"is_player":false}
    ],
    "current_turn": 0,
    "round_number": 1
  }
}
```

#### 通用豁免检定（DM → 服务器，服务器广播 saving_throw_result）

```json
// DM → 服务器（对单个目标）
{
  "type": "saving_throw",
  "data": {
    "encounter_map_id": "emap-xxx",
    "target_instance_id": "goblin-1",   // 或 "target_character_id"
    "ability": "dexterity",              // strength/dexterity/constitution/intelligence/wisdom/charisma
    "dc": 14,
    "damage_dice": "8d6",               // 空字符串 = 仅检定不扣血
    "damage_type": "fire",
    "half_on_success": true,            // 成功减半（火球术）
    "description": "火球术"
  }
}
// 服务器 → 全员
{
  "type": "saving_throw_result",
  "data": {
    "encounter_map_id": "emap-xxx",
    "target_instance_id": "goblin-1",
    "target_name": "地精",
    "ability": "dexterity", "dc": 14,
    "roll": 8, "bonus": 2, "total": 10, "success": false,
    "damage_rolled": 24, "damage_applied": 24,
    "damage_type": "fire",
    "hp_before": 15, "hp_after": 0, "target_is_down": true,
    "description": "火球术",
    "roll_breakdown": "[火球术]\n地精 掷 DEX 豁免（DC 14）\n骰子: 8 +加值+2 = 10 → ❌ 失败\n伤害: 8d6 = 24  HP: 15→0"
  }
}
```

#### AoE 伤害分发（DM → 服务器，服务器广播 aoe_attack_result）

```json
// 典型流程：先 GET /spell-area 获取范围内生物，再发 aoe_attack
// DM → 服务器
{
  "type": "aoe_attack",
  "data": {
    "encounter_map_id": "emap-xxx",
    "target_instance_ids": ["goblin-1", "goblin-2"],   // 从 spell-area 响应的 creatures_in_area 提取
    "target_character_ids": [],                         // 范围内的玩家角色
    "ability": "dexterity",
    "dc": 14,
    "damage_dice": "8d6",
    "damage_type": "fire",
    "half_on_success": true,
    "description": "火球术（3环）"
  }
}
// 服务器 → 全员
{
  "type": "aoe_attack_result",
  "data": {
    "encounter_map_id": "emap-xxx",
    "description": "火球术（3环）",
    "ability": "dexterity", "dc": 14,
    "damage_dice": "8d6", "damage_rolled": 24, "damage_type": "fire",
    "results": [
      {"instance_id":"goblin-1","name":"地精","save_success":false,"damage_applied":24,"hp_before":15,"hp_after":0,"is_down":true},
      {"instance_id":"goblin-2","name":"地精队长","save_success":true,"damage_applied":12,"hp_before":31,"hp_after":19,"is_down":false}
    ],
    "total_targets": 2, "successes": 1, "failures": 1, "total_damage_dealt": 36
  }
}
```

#### 法术命中时自动扣减法术位

```json
// DM/玩家 → 服务器（在 attack 消息中加 spell_slot_level）
{
  "type": "attack",
  "data": {
    "encounter_map_id": "emap-xxx",
    "attacker_character_id": "char-abc",
    "target_instance_id": "goblin-1",
    "attack_type": "spell",
    "damage_dice": "1d10+3",
    "damage_type": "fire",
    "spell_slot_level": 1    // 命中时自动扣减 1 环法术位；0 = 不扣（戏法）
  }
}
// 命中时额外广播 character_update（含 spell_slots 更新）
```

---

## 5. 典型游戏流程

### 流程一：玩家建卡并加入战役

```
1. POST /api/character                    → 创建角色，获得 char_id
2. POST /api/campaign/join/{code}         → 用邀请码加入战役，获得 camp_id
3. POST /api/campaign/{id}/characters/{char_id}  → 绑定角色（DM 操作）
4. GET  /api/character/{char_id}/summary  → 拉取角色派生值，渲染角色卡界面
```

### 流程二：DM 开局 → 遭遇战

```
1. POST /api/campaign/{id}/encounter-maps            → 创建棋盘
2. POST /api/import/map-bg/{campaign_id}/{map_id}    → 上传 DM 准备的地图图片（可选）
   或：POST .../encounter-maps/{mid}/generate-bg     → 让 AI 生成艺术背景图（可选）
3. （在地牢编辑器中标注地形）GET /dungeon-editor/{campaign_id}/{map_id}
4. POST .../encounter-maps/{mid}/simulate            → 放置角色+怪物，掷先攻
5. WS: send initiative_update                        → 把先攻顺序同步给全员
6. WS: send scene_update { encounter_map_id: mid }   → 通知所有人切换到战斗视图
```

### 流程三：一回合战斗

```
玩家行动：
1. WS: send roll  { notation:"1d20+5", reason:"攻击检定" }
   ← WS: roll_result 广播给全房间
2. WS: send creature_hp { instance_id:enemy, delta:-8 }
   ← WS: creature_hp 广播，Unity 更新血条

DM 推进：
3. WS: send turn_advance
   ← 服务器更新 current_turn，广播 initiative_update（同时重置所有角色行动资源）

生物移动（DM 拖拽棋子）：
4. WS: send creature_move { instance_id, x, y }
   ← 服务器写 DB，广播 creature_move
   ← 若触发机会攻击，额外广播 opportunity_attack

查看移动范围：
5. GET .../movement-range?creature_instance_id=xxx
   ← 返回可达格子列表，前端高亮显示

查看寻路路径（可选）：
6. GET .../path?from_x=1&from_y=1&to_x=5&to_y=3
   ← 返回最优路径格子列表
```

### 流程四：战斗结束 → 休息 → 升级

```
1. WS: send combat_end
2. POST /api/character/{id}/short-rest { "hit_dice":["d10"] }
   ← WS: rest_complete 广播给全员（含 hp_gained）
3. POST /api/campaign/{id}/encounter-reward { "xp":300, "character_ids":[...] }
   ← WS: xp_gain 广播
4. （若 XP 足够）POST /api/character/{id}/level-up
   ← 更新后角色表，WS: character_update 广播
```

### 流程五：断线重连

```
1. WS 重连（相同 campaign_id + owner_id）
2. 服务器自动推送 sync（内含先攻、场景、棋盘生物位置、角色数据）
3. Unity 根据 sync.creature_positions 重建棋盘状态
4. 若需要完整历史：GET /api/campaign/{id}/sessions/latest
```

---

## 6. 地图系统设计说明

### 三层地图结构

系统使用三种地图类型，覆盖不同粒度：

```
世界地图（WorldMap）
  └── 区域地图（RegionMap）      ← 新增
        └── 遭遇战棋盘（EncounterMap）
```

| 类型 | 用途 | 典型范围 | 地形数据 |
|---|---|---|---|
| 世界地图 | 大陆/国家级探索，POI 追踪 | 数百 km | 无（仅图片+标注）|
| 区域地图 | 城镇/森林/地牢等局部场景 | 1-50 km | 无（仅图片+标注）|
| 遭遇战棋盘 | 战斗用方格地图 | 5-200 格 | ✅ 有（格子地形数据）|

### AI 艺术图 vs. 实际地图

**AI 生成的图片（`image_url`）仅是视觉背景，不是游戏逻辑地图。**

```
┌─────────────────────────────────────────────┐
│  遭遇战棋盘的构成                             │
│                                             │
│  Layer 0: AI 生成艺术图 / DM 导入底图         │ ← image_url，纯视觉背景
│  Layer 1: 地形标注格子（cells[][]）           │ ← DM 在地牢编辑器中手动标注
│  Layer 2: 生物棋子（creatures[]）            │ ← 逻辑位置（格坐标）
│  Layer 3: 迷雾/视野遮罩                      │ ← is_visible 字段
└─────────────────────────────────────────────┘
```

**前端需理解的核心逻辑：**

1. **AI 生图只是背景贴图**：`generate-bg` 调用 AI 绘制一张艺术风格的场景图，放在画面最底层，没有任何游戏规则含义。

2. **真正的地图是 DM 手工标注的网格**：DM 在地牢编辑器（`/dungeon-editor/{campaign_id}/{map_id}`）中打开棋盘，在 Canvas 上逐格标注地形（墙壁/困难地形/水域/门等）。这些数据存在 `cells[row][col]` 里，是移动力计算、LOS 判断的依据。

3. **两者可以独立存在**：有背景图没有地形数据 → 移动不受限制；有地形数据没有背景图 → 按地形计算但画面简陋。正常流程是先放背景图，再按背景图的内容手工标注地形。

4. **世界地图和区域地图没有格子数据**，只有 POI 标注，不支持战斗逻辑。

### 图片 URL 说明

所有地图图片现在统一存储，`image_url` 字段是**直接可访问的 HTTP 路径**：

```
/static/maps/world_a1b2c3d4.png         ← 世界地图 AI 生成
/static/maps/world_camp001_upload.jpg   ← 世界地图手动上传
/static/maps/region_e5f6g7h8.png        ← 区域地图 AI 生成
/static/maps/encounter_emap001_bg.jpg   ← 遭遇战地图手动上传
```

前端加载图片：
```csharp
string imageUrl = $"http://{host}:8000{encounterMap.image_url}";
// 直接传给 UnityWebRequestTexture 加载
var req = UnityWebRequestTexture.GetTexture(imageUrl);
```

---

## 7. 开发建议

### 架构建议

**数据分层：**
```
GameState（内存）
  ├── RoomState：从 WS sync 初始化，实时消息增量更新
  │     ├── creature_positions（棋盘位置缓存）
  │     ├── initiative（先攻列表）
  │     └── current_turn / round_number
  └── CharacterCache：从 /summary 拉取，character_update 时刷新
```

**不要把 REST 和 WS 混用来做同一件事：**
- 棋盘上的生物移动 → 走 WS（实时性要求高）
- 角色升级、购买物品 → 走 REST（可靠性优先）
- 规则查询 → WS 和 REST 都支持，WS 更方便

---

### 地图渲染建议

**遭遇战棋盘渲染层次（从下到上）：**

```
Layer 0  背景图（image_url）   UnityEngine.UI.RawImage，直接 HTTP 加载
Layer 1  地形格（cells[][]）   按 terrain 类型着色半透明叠加层
Layer 2  格线                  只在有背景图时用白色半透明；无底图时用深色实线
Layer 3  迷雾（is_visible）    未探索格用黑色遮罩覆盖
Layer 4  移动范围高亮          BFS 结果用绿/黄半透明高亮
Layer 5  生物棋子              按 creature_positions 放置 token
Layer 6  UI 标注（HP 条等）
```

**地形颜色约定（建议与地牢编辑器保持一致）：**

| terrain | 无底图颜色 | 有底图叠加色（半透明）|
|---|---|---|
| open | 淡灰 | 无叠加 |
| difficult | 黄褐 | 黄色 40% |
| wall | 深灰 | 深灰 80% |
| water | 蓝色 | 蓝色 50% |
| door | 棕色 | 棕色 60% |
| cover_half | 橄榄绿 | 绿色 40% |
| cover_full | 深绿 | 深绿 60% |

**移动范围可视化：**
```csharp
public async void ShowMovementRange(string creatureInstanceId)
{
    var response = await api.GetMovementRange(campaignId, mapId, creatureInstanceId);
    foreach (var cell in response.reachable_cells)
    {
        Color highlight = cell.terrain == "difficult"
            ? new Color(1f, 0.9f, 0f, 0.5f)   // 黄色：困难地形
            : new Color(0f, 1f, 0.3f, 0.4f);  // 绿色：普通地形
        HighlightCell(cell.row, cell.col, highlight);
    }
}
```

**大地图 / 区域地图：**
- POI 坐标是百分比（0-100），乘以图片宽高得到像素坐标
- `is_hidden=true` 的 POI 只有 DM 显示，通过 `poi_reveal` WS 消息揭示给玩家
- 区域地图可以通过 `parent_world_map_id` + `parent_poi_id` 实现点击世界地图 POI 钻取到区域地图的导航

---

### 地图导入工作流（DM 端）

```
理想流程：
1. DM 在外部工具（Dungeon Scrawl / Inkarnate / 手绘扫描）制作地图图片
2. POST /api/import/map-bg/{campaign_id}/{map_id} 上传图片
   → 后端存入 data/maps/，返回 image_url
3. 打开地牢编辑器 /dungeon-editor/{campaign_id}/{map_id}
   → 图片作为底图显示，DM 在格子上点击标注地形
4. 保存 → cells[][] 写入数据库，战斗逻辑生效

AI 生图备选流程（无准备素材时）：
1. POST .../region-maps（创建区域地图，选类型，自动填预制提示词）
2. DM 可修改 image_prompt（PUT .../prompt）
3. POST .../generate（调用 AI 生图，得到 image_url）
4. 若需要战斗：POST .../encounter-maps，再链接该区域地图的图片
```

---

### C# 数据模型建议

**与 Unity 的 JsonUtility 兼容性：**  
后端返回的 JSON 使用 `snake_case`，Unity 的 `JsonUtility` 不支持自动转换，建议用 `Newtonsoft.Json`（JsonConvert）：

```csharp
var summary = JsonConvert.DeserializeObject<CharacterSummary>(json);
```

**关键 C# 数据类：**

```csharp
[System.Serializable]
public class RegionMap
{
    public string id;
    public string campaign_id;
    public string name;
    public string region_type;   // "town" | "forest" | "dungeon" | ...
    public float area_km;
    public string image_url;     // 直接用于 HTTP 加载
    public string image_prompt;
    public PointOfInterest[] pois;
    public string parent_world_map_id;
    public string parent_poi_id;
}

[System.Serializable]
public class EncounterMap
{
    public string id;
    public string campaign_id;
    public string name;
    public int grid_cols, grid_rows;
    public int cell_size_ft;
    public string image_url;
    public MapCreature[] creatures;
    // cells[][] 是三维结构，建议用 JArray 解析后手动转换
}

[System.Serializable]
public class MapCreature
{
    public string instance_id;
    public string name;
    public int x, y;
    public int hp_current, hp_max;
    public int speed;
    public int movement_used;
    public bool is_player, is_hidden;
    public string[] conditions;
    public int initiative;
}

[System.Serializable]
public class WSMessage
{
    public string type;
    public string sender;
    public string ts;
    public string msg_id;
    // data 用 JObject 按 type 分别解析
}
```

---

### 优先开发顺序建议

| 优先级 | 功能模块 | 依赖接口 | 说明 |
|---|---|---|---|
| P0 | 角色卡查看/编辑 | `GET /summary`, `PATCH /hp` | 玩家核心功能 |
| P0 | WS 基础连接 + 掷骰 | WebSocket `roll` / `roll_result` | 全员可见，自动广播 |
| P0 | 战役大厅（加入/列表） | `GET /campaign`, `POST /join/{code}` | 基础社交 |
| P1 | 遭遇战棋盘渲染 | WS `sync`, `creature_move`, `creature_hp` | 战斗核心 |
| P1 | 先攻追踪器 | WS `initiative_update`, `turn_advance` | 回合管理 |
| P1 | 背包 & 货币 | `POST /inventory`, `POST /currency` | 资源管理 |
| P1 | DM 移动范围显示 | `GET .../movement-range` | 可视化可达格子 |
| P1 | DM 怪物资源面板 | `GET /monsters/{id}` | 动作/传奇/法术位 |
| P2 | 地牢编辑器集成 | `/dungeon-editor/{id}/{mid}` | 嵌入 WebView 或外链浏览器 |
| P2 | 机会攻击提示 | WS `opportunity_attack` | 弹出确认框 |
| P2 | 专注/反应追踪 | WS `reaction_used`, `cast_concentration_spell` | 战斗状态 |
| P2 | 规则查询面板 | `POST /api/query` 或 WS `rule_query` | AI 辅助 |
| P2 | 世界大地图 | `GET /world-map`, WS `poi_reveal` | 探索模式 |
| P3 | 区域地图浏览 | `GET .../region-maps` | 世界 → 区域钻取 |
| P3 | DM 地图管理工具 | `POST .../region-maps`, `/import/map-bg` | DM 工具面板 |
| P3 | 规则书导入面板 | `GET /import/rules/browse`, `POST /import/rules/scan` | DM 工具：浏览目录→一键导入 |
| P3 | 升级向导 | `POST /level-up`, `GET /spells/prepare` | 角色成长 |
| P3 | 休息面板 | `POST /short-rest`, `POST /long-rest` | 资源恢复 |
| P3 | 死亡豁免界面 | WS `death_save`, `PATCH /conditions` | 濒死体验 |

---
