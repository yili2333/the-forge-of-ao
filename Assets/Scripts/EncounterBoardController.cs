using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class EncounterBoardController : MonoBehaviour
{
    [Header("棋盘尺寸")]
    public float cellPixelSize = 40f;

    [Header("棋盘的3个层")]
    public RectTransform terrainLayer;
    public RectTransform highlightLayer;
    public RectTransform creatureLayer;

    [Header("调试")]
    public bool useMockData = true;

    public static EncounterBoardController Instance;

    public WebSocketSessionClient WsClient;

    private readonly CampaignApiService campaignApiService = new CampaignApiService();
    private EncounterMapData currentMap;
    private readonly Dictionary<string, GameObject> creatureTokens = new Dictionary<string, GameObject>();
    private readonly List<GameObject> terrainCells = new List<GameObject>();
    private readonly List<GameObject> highlightCells = new List<GameObject>();
    private int currentTurnIndex = -1;
    private readonly List<string> initiativeOrder = new List<string>();

    void Start()
    {
        Instance = this;
        if (useMockData || BackendConfig.UseMockServices)
        {
            LoadMockBoard();
            RenderBoard();
        }
        else
        {
            _ = TryLoadLiveBoardAtStartupAsync();
        }
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    public async Task LoadFromBackendAsync(string campaignId, string encounterMapId, bool isDm)
    {
        if (string.IsNullOrWhiteSpace(encounterMapId))
        {
            Debug.Log("[Board] No encounter map id available. Keeping current board.");
            return;
        }

        EncounterMapData loaded = await campaignApiService.GetEncounterMapAsync(campaignId, encounterMapId, isDm);
        if (loaded == null)
        {
            Debug.Log("[Board] Live encounter map load failed for " + encounterMapId + ".");
            if (currentMap == null)
            {
                LoadMockBoard();
                RenderBoard();
            }
            return;
        }

        useMockData = false;
        BackendConfig.EncounterMapId = encounterMapId;
        ApplyLoadedMap(loaded);
        Debug.Log("[Board] Live map loaded: " + loaded.id + " creatures=" + loaded.creatures.Count);
    }

    private async Task TryLoadLiveBoardAtStartupAsync()
    {
        string mapId = BackendConfig.EncounterMapId;
        if (string.IsNullOrWhiteSpace(mapId))
        {
            return;
        }

        await LoadFromBackendAsync(RoomSessionContext.roomId, mapId, RoomSessionContext.IsDM);
    }

    private void ApplyLoadedMap(EncounterMapData loaded)
    {
        currentMap = loaded;
        EnsureCellsInitialized();
        RenderBoard();
    }

    private void EnsureCellsInitialized()
    {
        if (currentMap == null)
        {
            return;
        }

        if (currentMap.cells == null)
        {
            currentMap.cells = new List<List<string>>();
        }

        while (currentMap.cells.Count < currentMap.grid_rows)
        {
            currentMap.cells.Add(new List<string>());
        }

        for (int r = 0; r < currentMap.grid_rows; r++)
        {
            if (currentMap.cells[r] == null)
            {
                currentMap.cells[r] = new List<string>();
            }
            while (currentMap.cells[r].Count < currentMap.grid_cols)
            {
                currentMap.cells[r].Add(TerrainType.Open);
            }
        }
    }

    private void LoadMockBoard()
    {
        currentMap = new EncounterMapData();
        currentMap.id = "mock-emap-001";
        currentMap.campaign_id = RoomSessionContext.roomId;
        currentMap.name = "测试棋盘";
        currentMap.grid_cols = 20;
        currentMap.grid_rows = 15;

        currentMap.cells = new List<List<string>>();
        for (int r = 0; r < currentMap.grid_rows; r++)
        {
            List<string> row = new List<string>();
            for (int c = 0; c < currentMap.grid_cols; c++) row.Add(TerrainType.Open);
            currentMap.cells.Add(row);
        }

        currentMap.cells[5][5] = TerrainType.Wall;
        currentMap.cells[5][6] = TerrainType.Wall;
        currentMap.cells[5][7] = TerrainType.Wall;
        currentMap.cells[6][5] = TerrainType.Wall;

        currentMap.cells[8][10] = TerrainType.Difficult;
        currentMap.cells[8][11] = TerrainType.Difficult;
        currentMap.cells[9][10] = TerrainType.Difficult;

        currentMap.cells[3][15] = TerrainType.Water;
        currentMap.cells[3][16] = TerrainType.Water;
        currentMap.cells[4][15] = TerrainType.Water;

        currentMap.creatures = new List<MapCreatureData>();

        MapCreatureData hero = new MapCreatureData();
        hero.instance_id = "hero-1";
        hero.name = "Hero";
        hero.x = 2;
        hero.y = 2;
        hero.hp_current = 12;
        hero.hp_max = 12;
        hero.is_player = true;
        hero.initiative = 18;
        currentMap.creatures.Add(hero);

        MapCreatureData goblin = new MapCreatureData();
        goblin.instance_id = "goblin-1";
        goblin.name = "Goblin";
        goblin.x = 10;
        goblin.y = 8;
        goblin.hp_current = 7;
        goblin.hp_max = 7;
        goblin.is_player = false;
        goblin.initiative = 12;
        currentMap.creatures.Add(goblin);

        Debug.Log("[Board] Mock加载完成。IsDM=" + RoomSessionContext.IsDM);
    }

    private void RenderBoard()
    {
        if (currentMap == null) return;
        EnsureCellsInitialized();

        float totalWidth = currentMap.grid_cols * cellPixelSize;
        float totalHeight = currentMap.grid_rows * cellPixelSize;
        SetLayerSize(terrainLayer, totalWidth, totalHeight);
        SetLayerSize(highlightLayer, totalWidth, totalHeight);
        SetLayerSize(creatureLayer, totalWidth, totalHeight);

        RenderTerrain();
        RenderGridLines();
        RenderCreatures();
    }

    private void SetLayerSize(RectTransform layer, float width, float height)
    {
        if (layer == null) return;
        layer.sizeDelta = new Vector2(width, height);
    }

    private void RenderTerrain()
    {
        foreach (var cell in terrainCells) if (cell != null) Destroy(cell);
        terrainCells.Clear();
        if (terrainLayer == null || currentMap == null) return;

        for (int r = 0; r < currentMap.grid_rows; r++)
        {
            for (int c = 0; c < currentMap.grid_cols; c++)
            {
                string terrain = currentMap.cells[r][c];
                GameObject cell = CreateCellQuad(terrainLayer, c, r, GetTerrainColor(terrain), "Cell_" + r + "_" + c);
                terrainCells.Add(cell);
            }
        }
    }

    private void RenderGridLines()
    {
        if (terrainLayer == null || currentMap == null) return;

        Color lineColor = new Color(0.3f, 0.3f, 0.3f, 0.8f);
        float lineThickness = 1.5f;
        float layerWidth = currentMap.grid_cols * cellPixelSize;
        float layerHeight = currentMap.grid_rows * cellPixelSize;

        for (int c = 0; c <= currentMap.grid_cols; c++)
        {
            GameObject line = new GameObject("VLine_" + c, typeof(RectTransform), typeof(Image));
            line.transform.SetParent(terrainLayer, false);
            RectTransform rt = line.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f);
            rt.anchorMax = new Vector2(0.5f, 0.5f);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = new Vector2(lineThickness, layerHeight);
            rt.anchoredPosition = new Vector2(c * cellPixelSize - layerWidth * 0.5f, 0f);
            line.GetComponent<Image>().color = lineColor;
            line.GetComponent<Image>().raycastTarget = false;
            terrainCells.Add(line);
        }

        for (int r = 0; r <= currentMap.grid_rows; r++)
        {
            GameObject line = new GameObject("HLine_" + r, typeof(RectTransform), typeof(Image));
            line.transform.SetParent(terrainLayer, false);
            RectTransform rt = line.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f);
            rt.anchorMax = new Vector2(0.5f, 0.5f);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = new Vector2(layerWidth, lineThickness);
            rt.anchoredPosition = new Vector2(0f, layerHeight * 0.5f - r * cellPixelSize);
            line.GetComponent<Image>().color = lineColor;
            line.GetComponent<Image>().raycastTarget = false;
            terrainCells.Add(line);
        }
    }

    private void RenderCreatures()
    {
        foreach (var kv in creatureTokens) if (kv.Value != null) Destroy(kv.Value);
        creatureTokens.Clear();
        if (creatureLayer == null || currentMap == null) return;

        foreach (var creature in currentMap.creatures)
        {
            GameObject token = CreateCreatureToken(creature);
            creatureTokens[creature.instance_id] = token;
        }
    }

    private GameObject CreateCreatureToken(MapCreatureData creature)
    {
        Color bodyColor = creature.is_player
            ? new Color(0.2f, 0.5f, 1f, 1f)
            : new Color(1f, 0.3f, 0.3f, 1f);

        GameObject token = new GameObject("Token_" + creature.instance_id, typeof(RectTransform), typeof(Image));
        token.transform.SetParent(creatureLayer, false);

        RectTransform rt = token.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(0.5f, 0.5f);
        rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = new Vector2(cellPixelSize * 0.8f, cellPixelSize * 0.8f);
        rt.anchoredPosition = GridToLocalPoint(creature.x, creature.y);

        Image bodyImg = token.GetComponent<Image>();
        bodyImg.color = bodyColor;
        bodyImg.raycastTarget = true;

        GameObject nameGo = new GameObject("Name", typeof(RectTransform));
        nameGo.transform.SetParent(token.transform, false);
        TextMeshProUGUI nameText = nameGo.AddComponent<TextMeshProUGUI>();
        nameText.text = creature.name;
        nameText.fontSize = 12;
        nameText.color = Color.white;
        nameText.alignment = TextAlignmentOptions.Center;
        nameText.fontStyle = FontStyles.Bold;
        nameText.raycastTarget = false;
        RectTransform nameRt = nameGo.GetComponent<RectTransform>();
        nameRt.anchorMin = Vector2.zero;
        nameRt.anchorMax = Vector2.one;
        nameRt.offsetMin = Vector2.zero;
        nameRt.offsetMax = Vector2.zero;

        GameObject hpBg = new GameObject("HpBg", typeof(RectTransform), typeof(Image));
        hpBg.transform.SetParent(token.transform, false);
        RectTransform hpBgRt = hpBg.GetComponent<RectTransform>();
        hpBgRt.anchorMin = new Vector2(0f, 0f);
        hpBgRt.anchorMax = new Vector2(1f, 0f);
        hpBgRt.pivot = new Vector2(0.5f, 0f);
        hpBgRt.sizeDelta = new Vector2(0f, 5f);
        hpBgRt.anchoredPosition = new Vector2(0f, -7f);
        hpBg.GetComponent<Image>().color = new Color(0.6f, 0.1f, 0.1f, 1f);
        hpBg.GetComponent<Image>().raycastTarget = false;

        GameObject hpFill = new GameObject("HpFill", typeof(RectTransform), typeof(Image));
        hpFill.transform.SetParent(hpBg.transform, false);
        RectTransform hpFillRt = hpFill.GetComponent<RectTransform>();
        float hpRatio = creature.hp_max > 0 ? (float)creature.hp_current / creature.hp_max : 0f;
        hpFillRt.anchorMin = new Vector2(0f, 0f);
        hpFillRt.anchorMax = new Vector2(Mathf.Clamp01(hpRatio), 1f);
        hpFillRt.offsetMin = Vector2.zero;
        hpFillRt.offsetMax = Vector2.zero;
        hpFill.GetComponent<Image>().color = new Color(0.2f, 0.8f, 0.2f, 1f);
        hpFill.GetComponent<Image>().raycastTarget = false;

        CreatureTokenView view = token.AddComponent<CreatureTokenView>();
        view.Initialize(creature, this);

        return token;
    }

    private GameObject CreateCellQuad(RectTransform parent, int col, int row, Color color, string name)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);

        RectTransform rt = go.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(0.5f, 0.5f);
        rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = new Vector2(cellPixelSize, cellPixelSize);
        rt.anchoredPosition = GridToLocalPoint(col, row);

        Image img = go.GetComponent<Image>();
        img.color = color;
        img.raycastTarget = false;

        return go;
    }

    private Color GetTerrainColor(string terrain)
    {
        switch (terrain)
        {
            case TerrainType.Open:       return new Color(0.85f, 0.85f, 0.85f, 1f);
            case TerrainType.Difficult:  return new Color(0.75f, 0.55f, 0.2f, 1f);
            case TerrainType.Wall:       return new Color(0.25f, 0.25f, 0.25f, 1f);
            case TerrainType.Water:      return new Color(0.3f, 0.5f, 0.9f, 1f);
            case TerrainType.Door:       return new Color(0.6f, 0.4f, 0.2f, 1f);
            case TerrainType.CoverHalf:  return new Color(0.5f, 0.6f, 0.3f, 1f);
            case TerrainType.CoverFull:  return new Color(0.2f, 0.5f, 0.2f, 1f);
            default:                     return Color.magenta;
        }
    }

    public Vector2 GridToLocalPoint(int col, int row)
    {
        if (currentMap == null) return Vector2.zero;
        float layerWidth = currentMap.grid_cols * cellPixelSize;
        float layerHeight = currentMap.grid_rows * cellPixelSize;
        float x = col * cellPixelSize + cellPixelSize * 0.5f - layerWidth * 0.5f;
        float y = layerHeight * 0.5f - (row * cellPixelSize + cellPixelSize * 0.5f);
        return new Vector2(x, y);
    }

    public void LocalPointToGrid(Vector2 localPoint, out int col, out int row)
    {
        if (currentMap == null)
        {
            col = 0;
            row = 0;
            return;
        }

        float layerWidth = currentMap.grid_cols * cellPixelSize;
        float layerHeight = currentMap.grid_rows * cellPixelSize;
        float shiftedX = localPoint.x + layerWidth * 0.5f;
        float shiftedY = layerHeight * 0.5f - localPoint.y;
        col = Mathf.FloorToInt(shiftedX / cellPixelSize);
        row = Mathf.FloorToInt(shiftedY / cellPixelSize);
    }

    public bool IsValidGrid(int col, int row)
    {
        if (currentMap == null) return false;
        return col >= 0 && col < currentMap.grid_cols && row >= 0 && row < currentMap.grid_rows;
    }

    public bool IsWall(int col, int row)
    {
        if (!IsValidGrid(col, row)) return true;
        return currentMap.cells[row][col] == TerrainType.Wall;
    }

    public async void MoveCreature(string instanceId, int newCol, int newRow)
    {
        MapCreatureData creature = currentMap != null ? currentMap.creatures.Find(c => c.instance_id == instanceId) : null;
        if (creature == null) return;

        creature.x = newCol;
        creature.y = newRow;

        if (creatureTokens.TryGetValue(instanceId, out GameObject token) && token != null)
        {
            RectTransform rt = token.GetComponent<RectTransform>();
            rt.anchoredPosition = GridToLocalPoint(newCol, newRow);
        }

        Debug.Log("[Board] " + creature.name + " 移动到 (" + newCol + ", " + newRow + ")");
        await SendCreatureMoveAsync(instanceId, newCol, newRow);
    }

    private async Task SendCreatureMoveAsync(string instanceId, int x, int y)
    {
        if (WsClient == null || !WsClient.IsConnected)
        {
            Debug.Log("[Board] WS未连接，跳过发送creature_move");
            return;
        }

        string encounterMapId = currentMap != null ? currentMap.id : BackendConfig.EncounterMapId;
        string dataJson = "{\"encounter_map_id\":\"" + CharacterSheetPayloadBuilder.Escape(encounterMapId) +
                          "\",\"instance_id\":\"" + CharacterSheetPayloadBuilder.Escape(instanceId) +
                          "\",\"x\":" + x + ",\"y\":" + y + ",\"reason\":\"drag\"}";
        RoomMessage msg = new RoomMessage
        {
            type = "creature_move",
            sender = BackendConfig.OwnerId,
            dataJson = dataJson,
            content = "",
            ts = "",
            msg_id = ""
        };
        await WsClient.SendMessageAsync(msg);
        Debug.Log("[Board] 发送WS消息：creature_move -> (" + x + ", " + y + ") on map " + encounterMapId);
    }

    public void ShowMovementRange(string instanceId)
    {
        ClearHighlights();
        if (currentMap == null) return;

        MapCreatureData creature = currentMap.creatures.Find(c => c.instance_id == instanceId);
        if (creature == null) return;

        int maxSteps = creature.speed / 5;
        if (maxSteps <= 0) maxSteps = 6;

        int[,] cost = new int[currentMap.grid_rows, currentMap.grid_cols];
        for (int r = 0; r < currentMap.grid_rows; r++)
            for (int c = 0; c < currentMap.grid_cols; c++)
                cost[r, c] = int.MaxValue;

        Queue<Vector2Int> queue = new Queue<Vector2Int>();
        Vector2Int start = new Vector2Int(creature.x, creature.y);
        cost[start.y, start.x] = 0;
        queue.Enqueue(start);

        int[] dx = { 1, -1, 0, 0 };
        int[] dy = { 0, 0, 1, -1 };

        List<Vector2Int> reachable = new List<Vector2Int>();

        while (queue.Count > 0)
        {
            Vector2Int cur = queue.Dequeue();
            if (cur != start) reachable.Add(cur);

            for (int i = 0; i < 4; i++)
            {
                int nx = cur.x + dx[i];
                int ny = cur.y + dy[i];
                if (!IsValidGrid(nx, ny)) continue;
                if (IsWall(nx, ny)) continue;

                string terrain = currentMap.cells[ny][nx];
                int moveCost = (terrain == TerrainType.Difficult) ? 2 : 1;
                int newCost = cost[cur.y, cur.x] + moveCost;
                if (newCost > maxSteps) continue;

                if (newCost < cost[ny, nx])
                {
                    cost[ny, nx] = newCost;
                    queue.Enqueue(new Vector2Int(nx, ny));
                }
            }
        }

        foreach (var pos in reachable)
        {
            string terrain = currentMap.cells[pos.y][pos.x];
            Color color = terrain == TerrainType.Difficult
                ? new Color(1f, 0.9f, 0f, 0.5f)
                : new Color(0f, 1f, 0.3f, 0.4f);

            GameObject hi = CreateCellQuad(highlightLayer, pos.x, pos.y, color, "HI_" + pos.x + "_" + pos.y);
            highlightCells.Add(hi);
        }

        Debug.Log("[Board] " + creature.name + " 移动范围：" + reachable.Count + " 格");
    }

    public void ClearHighlights()
    {
        foreach (var h in highlightCells) if (h != null) Destroy(h);
        highlightCells.Clear();
    }

    public void OnWebSocketMessage(string messageType, string dataJson)
    {
        if (string.IsNullOrEmpty(messageType)) return;

        switch (messageType)
        {
            case "sync":
                HandleSync(dataJson);
                break;
            case "creature_move":
                HandleCreatureMove(dataJson);
                break;
            case "creature_hp":
                HandleCreatureHp(dataJson);
                break;
            case "initiative_update":
                HandleInitiative(dataJson);
                break;
        }
    }

    private void HandleSync(string dataJson)
    {
        string syncJson = NormalizePayload(dataJson);

        string activeMapId = JsonRegexUtility.ExtractString(syncJson, "active_encounter_map_id");
        if (!string.IsNullOrWhiteSpace(activeMapId))
        {
            BackendConfig.EncounterMapId = activeMapId;
            if (currentMap == null || currentMap.id != activeMapId)
            {
                _ = LoadFromBackendAsync(RoomSessionContext.roomId, activeMapId, RoomSessionContext.IsDM);
            }
        }

        string creaturePositions = JsonRegexUtility.ExtractObject(syncJson, "creature_positions");
        if (!string.IsNullOrWhiteSpace(creaturePositions))
        {
            ApplyCreaturePositionsSnapshot(creaturePositions);
        }

        ApplyInitiativeSnapshot(syncJson);
    }

    private void ApplyCreaturePositionsSnapshot(string creaturePositionsJson)
    {
        if (currentMap == null) return;

        List<KeyValuePair<string, string>> entries = JsonRegexUtility.ExtractTopLevelObjectEntries(creaturePositionsJson);
        for (int i = 0; i < entries.Count; i++)
        {
            string instanceId = entries[i].Key;
            string creatureJson = entries[i].Value;
            MapCreatureData creature = GetOrCreateCreature(instanceId, creatureJson);
            if (creature == null)
            {
                continue;
            }

            creature.x = JsonRegexUtility.ExtractInt(creatureJson, "x") ?? creature.x;
            creature.y = JsonRegexUtility.ExtractInt(creatureJson, "y") ?? creature.y;
            creature.hp_current = JsonRegexUtility.ExtractInt(creatureJson, "hp_current") ?? creature.hp_current;
            creature.hp_max = JsonRegexUtility.ExtractInt(creatureJson, "hp_max") ?? creature.hp_max;
            creature.is_player = JsonRegexUtility.ExtractBool(creatureJson, "is_player") ?? creature.is_player;
            string name = JsonRegexUtility.ExtractString(creatureJson, "name");
            if (!string.IsNullOrWhiteSpace(name)) creature.name = name;
        }

        RenderCreatures();
    }

    private void HandleCreatureMove(string dataJson)
    {
        if (currentMap == null) return;

        string payload = NormalizePayload(dataJson);
        string iid = JsonRegexUtility.ExtractString(payload, "instance_id");
        int? xValue = JsonRegexUtility.ExtractInt(payload, "x");
        int? yValue = JsonRegexUtility.ExtractInt(payload, "y");

        if (string.IsNullOrEmpty(iid) || !xValue.HasValue || !yValue.HasValue) return;

        MapCreatureData creature = GetOrCreateCreature(iid, payload);
        if (creature == null) return;

        creature.x = xValue.Value;
        creature.y = yValue.Value;
        UpdateCreatureToken(creature);
    }

    private void HandleCreatureHp(string dataJson)
    {
        if (currentMap == null) return;

        string payload = NormalizePayload(dataJson);
        string iid = JsonRegexUtility.ExtractString(payload, "instance_id");

        if (string.IsNullOrEmpty(iid)) return;

        MapCreatureData creature = GetOrCreateCreature(iid, payload);
        if (creature == null) return;

        int? hpCurrent = JsonRegexUtility.ExtractInt(payload, "hp_current");
        int? hpMax = JsonRegexUtility.ExtractInt(payload, "hp_max");
        if (hpCurrent.HasValue) creature.hp_current = hpCurrent.Value;
        if (hpMax.HasValue) creature.hp_max = hpMax.Value;

        UpdateCreatureToken(creature);
    }

    private void HandleInitiative(string dataJson)
    {
        if (currentMap == null) return;

        string payload = NormalizePayload(dataJson);
        ApplyInitiativeSnapshot(payload);
    }

    private void ApplyInitiativeSnapshot(string json)
    {
        string initiativeJson = JsonRegexUtility.ExtractArray(json, "entries");
        if (string.IsNullOrWhiteSpace(initiativeJson))
        {
            initiativeJson = JsonRegexUtility.ExtractArray(json, "initiative");
        }

        if (!string.IsNullOrWhiteSpace(initiativeJson))
        {
            initiativeOrder.Clear();
            List<string> entries = JsonRegexUtility.SplitTopLevelObjects(initiativeJson);
            for (int i = 0; i < entries.Count; i++)
            {
                string entry = entries[i];
                string charId = JsonRegexUtility.ExtractString(entry, "character_id");
                string entryId = JsonRegexUtility.ExtractString(entry, "id");
                string stableId = !string.IsNullOrWhiteSpace(entryId) ? entryId : charId;
                if (!string.IsNullOrWhiteSpace(stableId))
                {
                    initiativeOrder.Add(stableId);
                }

                MapCreatureData creature = currentMap.creatures.Find(c => (!string.IsNullOrWhiteSpace(charId) && c.character_id == charId) || c.instance_id == entryId);
                if (creature != null)
                {
                    creature.initiative = JsonRegexUtility.ExtractInt(entry, "initiative") ?? creature.initiative;
                    UpdateCreatureToken(creature);
                }
            }
        }

        currentTurnIndex = JsonRegexUtility.ExtractInt(json, "current_turn") ?? currentTurnIndex;
    }

    private string NormalizePayload(string dataJson)
    {
        string nested = JsonRegexUtility.ExtractObject(dataJson, "data");
        return !string.IsNullOrWhiteSpace(nested) ? nested : dataJson;
    }

    private MapCreatureData GetOrCreateCreature(string instanceId, string creatureJson)
    {
        if (currentMap == null || string.IsNullOrWhiteSpace(instanceId)) return null;

        MapCreatureData creature = currentMap.creatures.Find(c => c.instance_id == instanceId);
        if (creature != null)
        {
            return creature;
        }

        creature = new MapCreatureData();
        creature.instance_id = instanceId;
        creature.name = JsonRegexUtility.ExtractString(creatureJson, "name");
        if (string.IsNullOrWhiteSpace(creature.name))
        {
            creature.name = instanceId;
        }
        creature.character_id = JsonRegexUtility.ExtractString(creatureJson, "character_id");
        creature.is_player = JsonRegexUtility.ExtractBool(creatureJson, "is_player") ?? false;
        creature.hp_current = JsonRegexUtility.ExtractInt(creatureJson, "hp_current") ?? 0;
        creature.hp_max = JsonRegexUtility.ExtractInt(creatureJson, "hp_max") ?? creature.hp_current;
        creature.x = JsonRegexUtility.ExtractInt(creatureJson, "x") ?? 0;
        creature.y = JsonRegexUtility.ExtractInt(creatureJson, "y") ?? 0;
        currentMap.creatures.Add(creature);
        return creature;
    }

    private void UpdateCreatureToken(MapCreatureData creature)
    {
        if (creature == null || creatureLayer == null)
        {
            return;
        }

        if (creatureTokens.TryGetValue(creature.instance_id, out GameObject token) && token != null)
        {
            Destroy(token);
        }

        GameObject newToken = CreateCreatureToken(creature);
        creatureTokens[creature.instance_id] = newToken;
    }
}
