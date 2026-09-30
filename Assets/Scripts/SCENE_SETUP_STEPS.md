# WorldMapScene / RegionMapScene 快速接入步骤

这 3 个脚本默认基于 **我之前给你的 patched 版本** 使用：
- AdvancedBackendApiService.cs
- 扩展后的 BackendConfig.cs
- 扩展后的 ServiceModels.cs

如果你还在原版项目里，请先把 patched 版本解压打开。

## 1. 复制脚本
把这 3 个脚本放进：
`Assets/Scripts/`

- MapNavigationContext.cs
- WorldMapSceneController.cs
- RegionMapSceneController.cs

## 2. 新建场景
在 `Assets/Scenes/` 下新建两个场景：
- `WorldMapScene.unity`
- `RegionMapScene.unity`

## 3. 给每个场景挂控制器
### WorldMapScene
- 打开 `WorldMapScene`
- Hierarchy 右键 -> Create Empty
- 命名 `WorldMapRoot`
- 挂 `WorldMapSceneController`

### RegionMapScene
- 打开 `RegionMapScene`
- Hierarchy 右键 -> Create Empty
- 命名 `RegionMapRoot`
- 挂 `RegionMapSceneController`

这两个脚本会自动生成 Canvas/UI，所以场景里不用手工搭复杂界面。

## 4. 加入 Build Settings
`File -> Build Settings...`
把两个新场景加进去，建议顺序：
- HomeScene
- RoomScene
- CharacterVaultScene
- CharacterEditorScene
- WorldMapScene
- RegionMapScene

## 5. 最快测试方式
先进入 `RoomScene`，如果你用的是 patched 版本，直接试：
- 点底部 `World Map`
- 或在聊天框输入 `/world`
- 输入 `/regions`

如果你只是想单独测试新场景，也可以在 Play 前先手动打开 `WorldMapScene`。

## 6. 从 RoomScene 跳到 WorldMapScene（最省事）
如果你想要真正切场景，而不是只在 Room 里预览：
- 在 `RoomScene` 手工放一个按钮，文本写 `World Map`
- OnClick 绑定一个很小的跳转脚本，或者你自己在现有按钮逻辑里写：
  `SceneManager.LoadScene("WorldMapScene");`

## 7. 注意
- `RoomSessionContext.roomId` 被当作 campaign id 使用，所以你进房间时填的 room id 要和后端 campaign id 对得上。
- 这两个场景默认只做“查看世界地图 / 区域地图”的展示，不会一次性把 POI 编辑、上传、生成按钮全做完。
- 时间紧的话，先保证能加载图片、能显示 region 列表、能从 world 进入 region，就已经很够演示了。
