# 战斗棋盘交互 - 前端交付说明

> 作者：[你的名字]
> 日期：2026-04-21
> 目标：在 `RoomScene` 中实现遭遇战棋盘（EncounterMap）的前端渲染与交互
> 状态：**本地功能完整，等待后端联调**

---

## 一、任务概述

本次我负责实现战斗棋盘的前端部分。按照 `front.md` 的规范，棋盘交互涉及：

- 棋盘渲染（格子 + 地形 + 格线）
- 生物棋子（显示名字 + HP 条）
- DM 拖拽棋子移动（带格子吸附、墙壁阻挡、越界回退）
- 点击棋子显示移动范围（BFS 计算，困难地形消耗 2 格）
- WebSocket 消息的发送与接收（`creature_move` / `creature_hp` / `sync`）

**开发策略**：由于后端暂未在本地运行，全部功能在 **Mock 数据** 模式下开发和测试。
WS 代码已就位，后端一启动即可联调，无需修改棋盘逻辑。

---

## 二、新增文件

以下文件是本次新建的，都在 `Assets/Scripts/` 下：

| 文件 | 行数 | 作用 |
|---|---|---|
| `EncounterBoardData.cs` | ~60 | 棋盘数据模型（`EncounterMapData` / `MapCreatureData` / `TerrainType`） |
| `EncounterBoardController.cs` | ~490 | 棋盘主控制器：渲染、坐标转换、BFS、WS 收发 |
| `CreatureTokenView.cs` | ~90 | 单个棋子的视图与交互（`IBeginDragHandler` 等接口实现） |

---

## 三、修改的已有文件

### `RoomUIController.cs`（组员已有文件）

**改动点 1 —— `PumpWebSocketMessages()` 方法**
增加了棋盘消息的转发逻辑，把 `creature_move` / `creature_hp` / `sync`
这三类消息转发给 `EncounterBoardController.Instance.OnWebSocketMessage()`。

**改动点 2 —— `InitializeRoomConnectionAsync()` 方法**
WS 连接成功时，把 `webSocketClient` 注入到 `EncounterBoardController.Instance.WsClient`
这样棋盘就能通过已有 WS 客户端发送消息，**不需要自己维护连接**。

> ⚠️ **给组员的提醒**：如果你之前对 `RoomUIController.cs` 有其他改动，合并时注意不要丢失这两处。

### `RoomSessionContext.cs`

临时把默认 role 从 `"Player"` 改成了 `"dm"` 用于测试拖拽。**正式联调前需要改回来**，或者由登录流程动态设置。

---

## 四、场景变更（RoomScene.unity）

### 层级结构

在 `CenterPanel` 下新增以下层级：

```
CenterPanel（已有）
  └── EncounterBoard（新增，Rect 撑满父物体）
        ├── TerrainLayer（中心锚点，800×600）
        ├── HighlightLayer（中心锚点，800×600）
        └── CreatureLayer（中心锚点，800×600）
```

### 组件配置

- `EncounterBoard` 上挂了 `EncounterBoardController` 组件
- Inspector 中已绑定三个 Layer 的引用
- `Use Mock Data` 默认勾选（无后端时使用假数据）
- `Cell Pixel Size` = 40

---

## 五、核心设计说明

### 5.1 坐标系统

棋盘用 **Layer 中心坐标系**：

- 所有格子、棋子、高亮元素的锚点都设为 `(0.5, 0.5)`（中心）
- `GridToLocalPoint(col, row)` 把格子坐标转成中心坐标系的本地坐标
- `LocalPointToGrid(localPoint, out col, out row)` 反向转换

**这样做的原因**：Unity 的拖拽事件（`ScreenPointToLocalPointInRectangle`）返回的
本地坐标是基于父物体的 pivot，而 Layer 的 pivot 是中心。统一成中心坐标系后，
拖拽代码和渲染代码用同一个坐标系，不用任何位移换算。

### 5.2 渲染层次（按 front.md 的 6 层规范）

| Layer | 对应 GameObject | 作用 |
|---|---|---|
| 0 背景图 | （未实现，预留） | 未来放 `image_url` 的背景贴图 |
| 1 地形 | `TerrainLayer` 下的 `Cell_r_c` | 按地形着色 |
| 2 格线 | `TerrainLayer` 下的 `VLine_*` / `HLine_*` | 深灰半透明 |
| 3 迷雾 | （未实现） | 预留 |
| 4 移动范围 | `HighlightLayer` 下的 `HI_x_y` | 绿色/黄色半透明 |
| 5 棋子 | `CreatureLayer` 下的 `Token_*` | 方块 + 名字 + HP 条 |

### 5.3 拖拽逻辑（`CreatureTokenView.cs`）

关键设计点：

1. **权限检查**：`OnBeginDrag` 里先判断 `RoomSessionContext.IsDM`，不是 DM 直接 return
2. **鼠标偏移**：记录鼠标按下时与棋子中心的偏移 `dragPointerOffset`，拖动时保持这个偏移 → 鼠标不会瞬移到棋子中心
3. **吸附计算**：`OnEndDrag` 里用棋子当前 `anchoredPosition`（不是鼠标位置）转为格子坐标，这样吸附到的是棋子中心所在的格子
4. **墙壁/越界检查**：检查通过才调用 `boardController.MoveCreature()`，否则弹回原位

### 5.4 移动范围 BFS（`ShowMovementRange`）

- `maxSteps = creature.speed / 5`（D&D 标准：每格 5ft）
- 普通地形消耗 1 格，困难地形消耗 2 格
- 墙壁完全阻挡
- 输出的可达格子按地形上色：绿色（普通）/ 黄色（困难）

> 注：这是本地简化版。后端有 `GET .../movement-range` 端点会返回更准确的结果
> （考虑反应、环境效果等），后端到位后应改为调用该接口。

### 5.5 WebSocket 协议

**发送（DM 拖动棋子）：**
```json
{
  "type": "creature_move",
  "sender": "<owner_id>",
  "data": { "instance_id": "hero-1", "x": 5, "y": 3 }
}
```

**接收（所有人）：**
- `creature_move` → 更新对应棋子位置
- `creature_hp` → 更新对应棋子 HP 条（简化实现：重建整个棋子）
- `sync` → 目前只记 log，未来实现完整重建棋盘状态

> 注：WS 客户端（`WebSocketSessionClient`）由 `RoomUIController` 管理，
> 棋盘只是借用，不重复造轮子。

---

## 六、如何测试

### 单机 Mock 测试（当前状态）

1. 确保 `RoomSessionContext.role = "dm"`
2. 确保 `EncounterBoard` 的 Inspector 中 `Use Mock Data` 已勾选
3. 运行 `RoomScene`
4. 预期看到 20×15 棋盘，包含：
   - L 形墙壁（5,5 / 5,6 / 5,7 / 6,5）
   - 黄褐色困难地形（8,10 / 8,11 / 9,10）
   - 蓝色水域（3,15 / 3,16 / 4,15）
   - 蓝色玩家棋子 `Hero`（2,2）
   - 红色怪物棋子 `Goblin`（10,8）
5. 交互测试：
   - **拖动棋子** → 鼠标跟随棋子 → 松手吸附
   - **拖到墙壁** → 弹回原位，Console 打印"目标是墙壁，回退"
   - **拖到棋盘外** → 弹回原位，Console 打印"拖到棋盘外，回退"
   - **单击棋子** → 显示绿/黄色高亮可达格子
   - **点另一个棋子** → 高亮切换

### 联调测试（后端启动后）

1. 启动后端（`http://localhost:8000/api/health` 应返回 `{"status":"ok"}`）
2. 确保 `BackendConfig` 里的地址和端口正确
3. 运行两个实例（一个 DM + 一个 Player）
4. DM 拖棋子 → Player 画面应实时同步
5. 观察 Console：
   - `[Board] 发送WS消息：creature_move -> (X, Y)`（DM 端）
   - `[Board] 收到creature_move：Hero -> (X, Y)`（Player 端）

---

## 七、已知限制 / TODO

| 项 | 说明 |
|---|---|
| 中文字体 | Unity 默认字体不支持中文，棋子名字目前用英文。需配置 TMP 中文字体 |
| 背景图 | 暂未接入 `image_url`，只有纯色格子 |
| 迷雾 / 视野 | 未实现 `is_visible` 遮罩 |
| 机会攻击提示 | `opportunity_attack` WS 消息未处理 |
| 真实移动范围 API | 当前用本地 BFS，未来应改为 `GET .../movement-range` |
| 棋盘切换 | 当前 Mock 数据是硬编码的，真实场景需响应 `scene_update` 消息加载新棋盘 |
| 先攻顺序 UI | 棋盘只画了棋子，先攻追踪器的 UI 还没做 |
| JSON 解析 | 目前用简单正则解析，复杂场景建议引入 `Newtonsoft.Json` |

---

## 八、文件清单（提交时请一起合并）

**新增：**
- `Assets/Scripts/EncounterBoardData.cs`
- `Assets/Scripts/EncounterBoardController.cs`
- `Assets/Scripts/CreatureTokenView.cs`

**修改：**
- `Assets/Scripts/RoomUIController.cs`
- `Assets/Scripts/RoomSessionContext.cs`（临时改动，联调前恢复）
- `Assets/Scenes/RoomScene.unity`（新增了 `EncounterBoard` 层级）

---

## 九、联调时需要后端确认的事

1. WS 连接 URL 格式：`ws://<host>:8000/ws/{campaign_id}?owner_id=...&role=...`
2. `creature_move` 消息格式是否完全匹配 `front.md` 约定
3. 棋盘 id（`encounter_map_id`）如何在 Mock 模式切到真实模式时传入
4. 后端返回的 `cells[][]` 如果是 JSON 三维数组，解析方式需要沟通

---

有问题直接问我，或者在群里 @ 我。
