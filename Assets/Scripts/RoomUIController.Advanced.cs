using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.SceneManagement;

public partial class RoomUIController
{
    private readonly AdvancedBackendApiService advancedBackendApiService = new AdvancedBackendApiService();
    private static readonly HttpClient AdvancedHttp = new HttpClient();

    private Button worldMapButton;
    private Button regionsButton;
    private Button encountersButton;
    private Button sessionLogButton;
    private Button longRestButton;
    private Button hpMinusButton;
    private Button hpPlusButton;
    private Button refreshDataButton;
    private Button simulateEncounterButton;
    private Button rollInitiativeButton;
    private Button createRegionButton;
    private Button generateRegionButton;
    private Button browseRulesButton;
    private Button scanRulesButton;

    private string rulesBrowsePath = string.Empty;
    private string rulesScanRootPath = string.Empty;

    private void BuildAdvancedRuntimeOverlay()
    {
        Canvas canvas = ResolveUiCanvas();
        if (canvas == null)
        {
            Debug.LogWarning("[RoomUIController] Canvas not found for advanced runtime overlay.");
            return;
        }

        Transform oldStrip = canvas.transform.Find("AdvancedRuntimeStrip");
        if (oldStrip != null)
        {
            GameObject.Destroy(oldStrip.gameObject);
        }

        Transform oldPanel = canvas.transform.Find("AdvancedRuntimePanel");
        if (oldPanel != null)
        {
            GameObject.Destroy(oldPanel.gameObject);
        }

        TMP_FontAsset fontAsset = TMP_Settings.defaultFontAsset;
        if (fontAsset == null && chatLogText != null)
        {
            fontAsset = chatLogText.font;
        }

        GameObject panel = CreatePanel(
            "AdvancedRuntimePanel",
            canvas.transform,
            new Vector2(0.5f, 0f),
            new Vector2(0.5f, 0f),
            new Vector2(0.5f, 0f),
            new Vector2(0f, 62f),
            new Vector2(940f, 58f),
            new Color(0.08f, 0.11f, 0.17f, 0.92f));

        VerticalLayoutGroup rootLayout = panel.AddComponent<VerticalLayoutGroup>();
        rootLayout.spacing = 4f;
        rootLayout.padding = new RectOffset(6, 6, 4, 4);
        rootLayout.childForceExpandHeight = false;
        rootLayout.childForceExpandWidth = true;
        rootLayout.childControlHeight = true;
        rootLayout.childControlWidth = true;

        GameObject row1 = new GameObject("Row1", typeof(RectTransform), typeof(LayoutElement));
        row1.transform.SetParent(panel.transform, false);
        LayoutElement row1Element = row1.GetComponent<LayoutElement>();
        row1Element.preferredHeight = 23f;
        row1Element.minHeight = 23f;

        HorizontalLayoutGroup row1Layout = row1.AddComponent<HorizontalLayoutGroup>();
        row1Layout.spacing = 4f;
        row1Layout.padding = new RectOffset(0, 0, 0, 0);
        row1Layout.childForceExpandHeight = true;
        row1Layout.childForceExpandWidth = false;
        row1Layout.childControlWidth = true;
        row1Layout.childControlHeight = true;

        GameObject row2 = new GameObject("Row2", typeof(RectTransform), typeof(LayoutElement));
        row2.transform.SetParent(panel.transform, false);
        LayoutElement row2Element = row2.GetComponent<LayoutElement>();
        row2Element.preferredHeight = 23f;
        row2Element.minHeight = 23f;

        HorizontalLayoutGroup row2Layout = row2.AddComponent<HorizontalLayoutGroup>();
        row2Layout.spacing = 4f;
        row2Layout.padding = new RectOffset(0, 0, 0, 0);
        row2Layout.childForceExpandHeight = true;
        row2Layout.childForceExpandWidth = false;
        row2Layout.childControlWidth = true;
        row2Layout.childControlHeight = true;

        worldMapButton = CreateCompactButton("WorldMapButton", row1.transform, "World Scene", fontAsset, () => RunOverlayAction("Open World Scene", OpenWorldMapSceneFromRoom));
        regionsButton = CreateCompactButton("RegionsButton", row1.transform, "Region Scene", fontAsset, () => RunOverlayAction("Open Region Scene", OpenRegionMapSceneFromRoom));
        encountersButton = CreateCompactButton("EncountersButton", row1.transform, "Encounters", fontAsset, () => RunOverlayAction("Encounters", ShowEncounterMaps));
        sessionLogButton = CreateCompactButton("SessionLogButton", row1.transform, "Session Log", fontAsset, () => RunOverlayAction("Session Log", ShowSessionLog));
        createRegionButton = CreateCompactButton("CreateRegionButton", row1.transform, "Create Region", fontAsset, () => RunOverlayAction("Create Region", QuickCreateRegion));
        generateRegionButton = CreateCompactButton("GenerateRegionButton", row1.transform, "Gen Region", fontAsset, () => RunOverlayAction("Gen Region", QuickGenerateRegion));
        browseRulesButton = CreateCompactButton("BrowseRulesButton", row1.transform, "Browse Rules", fontAsset, () => RunOverlayAction("Browse Rules", BrowseRulesFolder));
        scanRulesButton = CreateCompactButton("ScanRulesButton", row1.transform, "Scan Rules", fontAsset, () => RunOverlayAction("Scan Rules", ScanRulesFolder));

        simulateEncounterButton = CreateCompactButton("SimulateEncounterButton", row2.transform, "Simulate", fontAsset, () => RunOverlayAction("Simulate", SimulateEncounter));
        rollInitiativeButton = CreateCompactButton("RollInitiativeButton", row2.transform, "Init", fontAsset, () => RunOverlayAction("Init", RollInitiative));
        longRestButton = CreateCompactButton("LongRestButton", row2.transform, "Long Rest", fontAsset, () => RunOverlayAction("Long Rest", TriggerLongRest));
        hpMinusButton = CreateCompactButton("HpMinusButton", row2.transform, "HP -5", fontAsset, () => RunOverlayAction("HP -5", () => ChangeSelectedCharacterHp(-5)));
        hpPlusButton = CreateCompactButton("HpPlusButton", row2.transform, "HP +5", fontAsset, () => RunOverlayAction("HP +5", () => ChangeSelectedCharacterHp(5)));
        refreshDataButton = CreateCompactButton("RefreshLiveDataButton", row2.transform, "Refresh", fontAsset, RefreshLiveData);

        bool isDm = RoomSessionContext.IsDM;
        if (simulateEncounterButton != null) simulateEncounterButton.interactable = isDm;
        if (rollInitiativeButton != null) rollInitiativeButton.interactable = isDm;
        if (createRegionButton != null) createRegionButton.interactable = isDm;
        if (generateRegionButton != null) generateRegionButton.interactable = isDm;
        if (browseRulesButton != null) browseRulesButton.interactable = isDm;
        if (scanRulesButton != null) scanRulesButton.interactable = isDm;
    }

    private Button CreateCompactButton(string name, Transform parent, string text, TMP_FontAsset fontAsset, UnityEngine.Events.UnityAction onClick)
    {
        Button button = CreateButton(name, parent, text, fontAsset, onClick);

        RectTransform rect = button.GetComponent<RectTransform>();
        if (rect != null)
        {
            rect.sizeDelta = new Vector2(110f, 22f);
        }

        Image image = button.GetComponent<Image>();
        if (image != null)
        {
            image.color = new Color(0.18f, 0.31f, 0.52f, 0.96f);
        }

        TextMeshProUGUI label = button.GetComponentInChildren<TextMeshProUGUI>();
        if (label != null)
        {
            label.fontSize = 10.5f;
            label.enableWordWrapping = false;
            label.overflowMode = TextOverflowModes.Ellipsis;
            label.alignment = TextAlignmentOptions.Center;
        }

        LayoutElement layout = button.GetComponent<LayoutElement>();
        if (layout == null)
        {
            layout = button.gameObject.AddComponent<LayoutElement>();
        }

        layout.preferredWidth = 110f;
        layout.preferredHeight = 22f;
        layout.minWidth = 96f;
        layout.minHeight = 22f;
        layout.flexibleWidth = 0f;
        return button;
    }

    private void RunOverlayAction(string actionName, Action action)
    {
        Debug.Log("[RoomUIController.Advanced] Clicked: " + actionName);
        AppendSystemMessage("Clicked: " + actionName + ".");
        action?.Invoke();
    }

    private bool HandleAdvancedLocalCommand(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return false;
        }

        if (message.Equals("/help", StringComparison.OrdinalIgnoreCase))
        {
            AppendSystemMessage("Commands: /help, /status, /rule <question>, /roll <dice>, /d20, /scene <prompt>, /load <path>, /audit, /reconnect, /backend host:port, /ws host:port, /owner <id>, /map <id>, /mock on|off, /home, /world, /regions, /region <id>, /encounters, /simulate, /init, /sessionlog [count], /monsters <query>, /monster <name>, /hp <delta>, /cond <add|remove|set> <cond1,cond2>, /shortrest [d10,d8], /longrest, /xp <amount> [note], /prepare <spell>, /prepared, /cast <slot> <spell>, /createregion, /genregion, /browse [path], /scan, /scanroot <path>.");
            return true;
        }

        if (message.Equals("/world", StringComparison.OrdinalIgnoreCase))
        {
            ShowWorldMap();
            return true;
        }

        if (message.Equals("/regions", StringComparison.OrdinalIgnoreCase))
        {
            ShowRegions();
            return true;
        }

        if (message.Equals("/encounters", StringComparison.OrdinalIgnoreCase))
        {
            ShowEncounterMaps();
            return true;
        }

        if (message.StartsWith("/region ", StringComparison.OrdinalIgnoreCase))
        {
            string regionId = message.Substring(8).Trim();
            if (string.IsNullOrWhiteSpace(regionId))
            {
                AppendSystemMessage("Use /region <region_map_id>.");
            }
            else
            {
                _ = ShowRegionMapAsync(regionId);
            }
            return true;
        }

        if (message.Equals("/simulate", StringComparison.OrdinalIgnoreCase))
        {
            SimulateEncounter();
            return true;
        }

        if (message.Equals("/init", StringComparison.OrdinalIgnoreCase))
        {
            RollInitiative();
            return true;
        }

        if (message.Equals("/createregion", StringComparison.OrdinalIgnoreCase))
        {
            QuickCreateRegion();
            return true;
        }

        if (message.Equals("/genregion", StringComparison.OrdinalIgnoreCase))
        {
            QuickGenerateRegion();
            return true;
        }

        if (message.StartsWith("/browse", StringComparison.OrdinalIgnoreCase))
        {
            string path = message.Length > 7 ? message.Substring(7).Trim() : string.Empty;
            if (!string.IsNullOrWhiteSpace(path))
            {
                rulesBrowsePath = path;
            }
            BrowseRulesFolder();
            return true;
        }

        if (message.Equals("/scan", StringComparison.OrdinalIgnoreCase))
        {
            ScanRulesFolder();
            return true;
        }

        if (message.StartsWith("/scanroot ", StringComparison.OrdinalIgnoreCase))
        {
            rulesScanRootPath = message.Substring(10).Trim();
            AppendSystemMessage("Rules scan root set to " + rulesScanRootPath);
            return true;
        }

        if (message.StartsWith("/sessionlog", StringComparison.OrdinalIgnoreCase))
        {
            int count = 8;
            string[] parts = message.Split(new char[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 2)
            {
                int.TryParse(parts[1].Trim(), out count);
                if (count <= 0) count = 8;
            }
            _ = ShowSessionLogAsync(count);
            return true;
        }

        if (message.StartsWith("/monsters ", StringComparison.OrdinalIgnoreCase))
        {
            string query = message.Substring(10).Trim();
            _ = SearchMonstersAsync(query);
            return true;
        }

        if (message.StartsWith("/monster ", StringComparison.OrdinalIgnoreCase))
        {
            string name = message.Substring(9).Trim();
            _ = ShowMonsterByNameAsync(name);
            return true;
        }

        if (message.StartsWith("/hp ", StringComparison.OrdinalIgnoreCase))
        {
            string value = message.Substring(4).Trim();
            int delta;
            if (int.TryParse(value, out delta))
            {
                _ = ChangeSelectedCharacterHpAsync(delta);
            }
            else
            {
                AppendSystemMessage("Use /hp <delta>, for example /hp -8 or /hp 5.");
            }
            return true;
        }

        if (message.StartsWith("/cond ", StringComparison.OrdinalIgnoreCase))
        {
            string body = message.Substring(6).Trim();
            string[] parts = body.Split(new char[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2)
            {
                AppendSystemMessage("Use /cond <add|remove|set> <cond1,cond2>.");
            }
            else
            {
                string action = parts[0].Trim().ToLowerInvariant();
                List<string> conditions = SplitCsv(parts[1]);
                _ = UpdateConditionsAsync(action, conditions);
            }
            return true;
        }

        if (message.StartsWith("/shortrest", StringComparison.OrdinalIgnoreCase))
        {
            string dicePart = message.Length > 10 ? message.Substring(10).Trim() : string.Empty;
            List<string> dice = string.IsNullOrWhiteSpace(dicePart) ? new List<string>() : SplitCsv(dicePart);
            _ = ShortRestAsync(dice);
            return true;
        }

        if (message.Equals("/longrest", StringComparison.OrdinalIgnoreCase))
        {
            TriggerLongRest();
            return true;
        }

        if (message.StartsWith("/xp ", StringComparison.OrdinalIgnoreCase))
        {
            string body = message.Substring(4).Trim();
            string[] parts = body.Split(new char[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
            int xpAmount;
            if (parts.Length >= 1 && int.TryParse(parts[0], out xpAmount))
            {
                string note = parts.Length > 1 ? parts[1] : "manual grant from Unity client";
                _ = GrantXpAsync(xpAmount, note);
            }
            else
            {
                AppendSystemMessage("Use /xp <amount> [note].");
            }
            return true;
        }

        if (message.StartsWith("/prepare ", StringComparison.OrdinalIgnoreCase))
        {
            string spell = message.Substring(9).Trim();
            _ = PrepareSpellAsync(spell);
            return true;
        }

        if (message.Equals("/prepared", StringComparison.OrdinalIgnoreCase))
        {
            _ = ShowPreparedSpellsAsync();
            return true;
        }

        if (message.StartsWith("/cast ", StringComparison.OrdinalIgnoreCase))
        {
            string body = message.Substring(6).Trim();
            string[] parts = body.Split(new char[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
            int slotLevel;
            if (parts.Length >= 1 && int.TryParse(parts[0], out slotLevel))
            {
                string spell = parts.Length > 1 ? parts[1].Trim() : string.Empty;
                _ = CastSpellAsync(slotLevel, spell);
            }
            else
            {
                AppendSystemMessage("Use /cast <slot-level> <spell-name>.");
            }
            return true;
        }

        return false;
    }

    private bool HandleAdvancedRealtimeMessage(RoomMessage message, string payload)
    {
        if (message == null)
        {
            return false;
        }

        switch (message.type)
        {
            case "scene_update":
                AppendSystemMessage("Scene update received.");
                string sceneImage = JsonRegexUtility.ExtractString(payload, "image_url");
                if (!string.IsNullOrWhiteSpace(sceneImage))
                {
                    _ = ApplyPreviewFromUrlAsync(
                        BackendConfig.ResolveAssetUrl(sceneImage),
                        "Scene Update",
                        JsonRegexUtility.ExtractString(payload, "description"),
                        string.IsNullOrWhiteSpace(JsonRegexUtility.ExtractString(payload, "name")) ? "Scene Update" : JsonRegexUtility.ExtractString(payload, "name"));
                }
                return true;
            case "character_update":
                AppendSystemMessage("Character update received.");
                _ = LoadLiveRoomDataAsync();
                _ = RefreshSelectedCharacterDetailsAsync();
                _ = RefreshAuditPanelAsync();
                return true;
            case "rest_complete":
                AppendSystemMessage("Rest complete: " + BuildRealtimeSummary(payload, message.content, "rest_complete"));
                _ = RefreshSelectedCharacterDetailsAsync();
                return true;
            case "condition_update":
                AppendSystemMessage("Condition update: " + BuildRealtimeSummary(payload, message.content, "condition_update"));
                _ = RefreshSelectedCharacterDetailsAsync();
                return true;
            case "map_update":
            case "fog_update":
            case "poi_reveal":
                AppendSystemMessage("Map update: " + BuildRealtimeSummary(payload, message.content, message.type));
                if (EncounterBoardController.Instance != null)
                {
                    _ = EncounterBoardController.Instance.LoadFromBackendAsync(RoomSessionContext.roomId, BackendConfig.EncounterMapId, RoomSessionContext.IsDM);
                }
                return true;
            case "turn_advance":
            case "death_save":
            case "loot_grant":
            case "xp_gain":
            case "reaction_used":
            case "opportunity_attack":
            case "creature_action":
            case "legendary_action":
            case "attack_result":
            case "saving_throw_result":
            case "aoe_attack_result":
            case "rule_result":
            case "npc_response":
                AppendSystemMessage(BuildRealtimeSummary(payload, message.content, message.type));
                if (message.type == "xp_gain" || message.type == "loot_grant")
                {
                    _ = RefreshSelectedCharacterDetailsAsync();
                }
                return true;
        }

        return false;
    }

    private void OpenWorldMapSceneFromRoom()
    {
        MapNavigationContext.SelectedRegionMapId = string.Empty;
        SceneManager.LoadScene("WorldMapScene");
    }

    private async void OpenRegionMapSceneFromRoom()
    {
        if (!string.IsNullOrWhiteSpace(MapNavigationContext.SelectedRegionMapId))
        {
            SceneManager.LoadScene("RegionMapScene");
            return;
        }

        List<RegionMapSummaryLite> regions = await advancedBackendApiService.GetRegionMapsAsync(RoomSessionContext.roomId);
        if (regions == null || regions.Count == 0)
        {
            AppendSystemMessage("No region maps available to open.");
            return;
        }

        string regionId = regions[0].id;
        if (string.IsNullOrWhiteSpace(regionId))
        {
            AppendSystemMessage("Region map id is empty.");
            return;
        }

        MapNavigationContext.SelectedRegionMapId = regionId;
        AppendSystemMessage("Opening RegionMapScene for " + regionId + ".");
        SceneManager.LoadScene("RegionMapScene");
    }

    private async void ShowWorldMap()
    {
        WorldMapLite worldMap = await advancedBackendApiService.GetWorldMapAsync(RoomSessionContext.roomId);
        if (worldMap == null || !worldMap.success)
        {
            AppendSystemMessage(worldMap != null ? worldMap.summary : "World map unavailable.");
            return;
        }

        AppendSystemMessage(worldMap.summary);
        if (!string.IsNullOrWhiteSpace(worldMap.imageUrl))
        {
            await ApplyPreviewFromUrlAsync(worldMap.imageUrl, worldMap.name, worldMap.description, "World Map");
        }
    }

    private async void ShowRegions()
    {
        List<RegionMapSummaryLite> regions = await advancedBackendApiService.GetRegionMapsAsync(RoomSessionContext.roomId);
        if (regions == null || regions.Count == 0)
        {
            AppendSystemMessage("No region maps were returned by backend.");
            return;
        }

        AppendSystemMessage("Region maps: " + regions.Count + ".");
        for (int i = 0; i < regions.Count && i < 6; i++)
        {
            RegionMapSummaryLite item = regions[i];
            AppendSystemMessage("- " + item.id + " | " + item.name + " | " + item.regionType + (item.poiCount > 0 ? " | POIs " + item.poiCount : string.Empty));
        }

        if (!string.IsNullOrWhiteSpace(regions[0].id))
        {
            MapNavigationContext.SelectedRegionMapId = regions[0].id;
            await ShowRegionMapAsync(regions[0].id);
        }
    }



    private async void ShowEncounterMaps()
    {
        List<EncounterMapSummaryLite> maps = await advancedBackendApiService.GetEncounterMapsAsync(RoomSessionContext.roomId);
        if (maps == null || maps.Count == 0)
        {
            AppendSystemMessage("No encounter maps found.");
            return;
        }

        AppendSystemMessage("Encounter maps: " + maps.Count + ".");
        for (int i = 0; i < maps.Count && i < 8; i++)
        {
            string marker = string.Equals(maps[i].id, BackendConfig.EncounterMapId, StringComparison.OrdinalIgnoreCase) ? " *current*" : string.Empty;
            AppendSystemMessage("- " + maps[i].summary + marker);
        }

        if (string.IsNullOrWhiteSpace(BackendConfig.EncounterMapId) && !string.IsNullOrWhiteSpace(maps[0].id))
        {
            BackendConfig.EncounterMapId = maps[0].id;
            AppendSystemMessage("Encounter map id auto-set to " + BackendConfig.EncounterMapId);
        }
    }

    private async void SimulateEncounter()
    {
        string mapId = BackendConfig.EncounterMapId;
        if (string.IsNullOrWhiteSpace(mapId))
        {
            AppendSystemMessage("EncounterMapId is empty. Use /map <id> first.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.SimulateEncounterAsync(RoomSessionContext.roomId, mapId);
        AppendSystemMessage(result.summary);

        if (result.success && EncounterBoardController.Instance != null)
        {
            await EncounterBoardController.Instance.LoadFromBackendAsync(RoomSessionContext.roomId, mapId, RoomSessionContext.IsDM);
        }
    }

    private async void RollInitiative()
    {
        string mapId = BackendConfig.EncounterMapId;
        if (string.IsNullOrWhiteSpace(mapId))
        {
            AppendSystemMessage("EncounterMapId is empty. Use /map <id> first.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.RollInitiativeAsync(RoomSessionContext.roomId, mapId);
        AppendSystemMessage(result.summary);

        if (result.success && EncounterBoardController.Instance != null)
        {
            await EncounterBoardController.Instance.LoadFromBackendAsync(RoomSessionContext.roomId, mapId, RoomSessionContext.IsDM);
        }
    }

    private async void QuickCreateRegion()
    {
        string regionName = "New Region " + DateTime.Now.ToString("HHmmss");
        RegionMapLite result = await advancedBackendApiService.CreateRegionMapAsync(
            RoomSessionContext.roomId,
            regionName,
            "Created from Unity RoomScene",
            "forest");

        AppendSystemMessage(result.summary);

        if (result.success && !string.IsNullOrWhiteSpace(result.id))
        {
            MapNavigationContext.SelectedRegionMapId = result.id;
        }
    }

    private async void QuickGenerateRegion()
    {
        string regionId = MapNavigationContext.SelectedRegionMapId;

        if (string.IsNullOrWhiteSpace(regionId))
        {
            List<RegionMapSummaryLite> regions = await advancedBackendApiService.GetRegionMapsAsync(RoomSessionContext.roomId);
            if (regions == null || regions.Count == 0)
            {
                AppendSystemMessage("No region map available.");
                return;
            }

            regionId = regions[0].id;
        }

        RegionMapLite result = await advancedBackendApiService.GenerateRegionMapAsync(
            RoomSessionContext.roomId,
            regionId,
            "fantasy forest region map, top-down, detailed terrain, rivers, roads, ruins");

        AppendSystemMessage(result.summary);

        if (result.success)
        {
            MapNavigationContext.SelectedRegionMapId = result.id;
            if (!string.IsNullOrWhiteSpace(result.imageUrl))
            {
                await ApplyPreviewFromUrlAsync(
                    result.imageUrl,
                    result.name,
                    result.description,
                    string.IsNullOrWhiteSpace(result.regionType) ? "Region Map" : result.regionType);
            }
        }
    }

    private async void BrowseRulesFolder()
    {
        BrowseResultLite result = await advancedBackendApiService.BrowseRulesAsync(rulesBrowsePath);
        if (result == null || !result.success)
        {
            AppendSystemMessage(result != null ? result.summary : "Rules browse failed.");
            return;
        }

        rulesBrowsePath = result.currentPath;
        if (string.IsNullOrWhiteSpace(rulesScanRootPath))
        {
            rulesScanRootPath = result.currentPath;
        }

        AppendSystemMessage(result.summary);
        if (result.entries != null)
        {
            for (int i = 0; i < result.entries.Length && i < 10; i++)
            {
                BrowseEntryLite entry = result.entries[i];
                if (entry.isDir)
                {
                    AppendSystemMessage("[DIR] " + entry.name + " | htm=" + entry.htmCount + " | pdf=" + entry.pdfCount);
                }
                else
                {
                    AppendSystemMessage("[FILE] " + entry.name);
                }
            }
        }
    }

    private async void ScanRulesFolder()
    {
        string root = !string.IsNullOrWhiteSpace(rulesScanRootPath) ? rulesScanRootPath : rulesBrowsePath;
        if (string.IsNullOrWhiteSpace(root))
        {
            AppendSystemMessage("Rules scan root is empty. Use Browse Rules first, or /scanroot <path>.");
            return;
        }

        ScanImportResultLite result = await advancedBackendApiService.ScanRulesAsync(root, false);
        if (result == null || !result.success)
        {
            AppendSystemMessage(result != null ? result.message : "Rules scan failed.");
            return;
        }

        AppendSystemMessage(result.message + " | books=" + result.booksImported + "/" + result.booksFound + " | chunks=" + result.totalChunks + " | conflicts=" + result.totalConflicts);

        if (result.results != null)
        {
            for (int i = 0; i < result.results.Length && i < 8; i++)
            {
                ScanBookResultLite item = result.results[i];
                string summary = item.detectedName + " | source=" + item.detectedSource + " | files=" + item.filesFound + " | chunks=" + item.chunksCreated;
                if (item.skipped)
                {
                    summary += " | skipped=" + item.skipReason;
                }
                AppendSystemMessage("- " + summary);
            }
        }
    }

    private async Task ShowRegionMapAsync(string regionMapId)
    {
        MapNavigationContext.SelectedRegionMapId = regionMapId;

        RegionMapLite region = await advancedBackendApiService.GetRegionMapAsync(RoomSessionContext.roomId, regionMapId);
        if (region == null || !region.success)
        {
            AppendSystemMessage(region != null ? region.summary : "Region map unavailable.");
            return;
        }

        AppendSystemMessage(region.summary);
        if (!string.IsNullOrWhiteSpace(region.imageUrl))
        {
            await ApplyPreviewFromUrlAsync(region.imageUrl, region.name, region.description, string.IsNullOrWhiteSpace(region.regionType) ? "Region Map" : region.regionType);
        }
    }

    private async void ShowSessionLog()
    {
        await ShowSessionLogAsync(8);
    }

    private async Task ShowSessionLogAsync(int limit)
    {
        SessionSnapshotLite latestSession = await campaignApiService.GetLatestSessionAsync(RoomSessionContext.roomId);
        if (latestSession == null || !latestSession.success || string.IsNullOrWhiteSpace(latestSession.sessionId))
        {
            AppendSystemMessage("No latest session available for session log.");
            return;
        }

        List<SessionLogEntryLite> logs = await advancedBackendApiService.GetSessionLogAsync(latestSession.sessionId, limit);
        if (logs == null || logs.Count == 0)
        {
            AppendSystemMessage("Session log is empty or unavailable.");
            return;
        }

        AppendSystemMessage("Session log: " + latestSession.sessionId + " | showing " + logs.Count + " entries.");
        for (int i = 0; i < logs.Count; i++)
        {
            AppendSystemMessage("- " + logs[i].summary);
        }
    }

    private async Task SearchMonstersAsync(string query)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            AppendSystemMessage("Use /monsters <query>.");
            return;
        }

        List<MonsterSummaryLite> monsters = await advancedBackendApiService.SearchMonstersAsync(query, 6);
        if (monsters == null || monsters.Count == 0)
        {
            AppendSystemMessage("No monsters matched query: " + query + ".");
            return;
        }

        AppendSystemMessage("Monster search: " + query + " -> " + monsters.Count + " result(s).");
        for (int i = 0; i < monsters.Count; i++)
        {
            AppendSystemMessage("- " + monsters[i].summary + " | id=" + monsters[i].id);
        }
    }

    private async Task ShowMonsterByNameAsync(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            AppendSystemMessage("Use /monster <name>.");
            return;
        }

        MonsterSummaryLite monster = await advancedBackendApiService.GetMonsterByNameAsync(name);
        if (monster == null)
        {
            AppendSystemMessage("Monster not found: " + name + ".");
            return;
        }

        AppendSystemMessage("Monster: " + monster.summary + " | id=" + monster.id);
    }

    private async void TriggerLongRest()
    {
        await LongRestAsync();
    }

    private async Task LongRestAsync()
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for long rest.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.LongRestAsync(characterId);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async void ChangeSelectedCharacterHp(int delta)
    {
        await ChangeSelectedCharacterHpAsync(delta);
    }

    private async Task ChangeSelectedCharacterHpAsync(int delta)
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for HP update.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.ApplyHpDeltaAsync(characterId, delta);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async Task UpdateConditionsAsync(string action, List<string> conditions)
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for condition update.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.PatchConditionsAsync(characterId, action, conditions);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async Task ShortRestAsync(List<string> hitDice)
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for short rest.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.ShortRestAsync(characterId, hitDice);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async Task GrantXpAsync(int xpAmount, string note)
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for XP update.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.GrantXpAsync(characterId, xpAmount, note);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async Task PrepareSpellAsync(string spellName)
    {
        if (string.IsNullOrWhiteSpace(spellName))
        {
            AppendSystemMessage("Use /prepare <spell-name>.");
            return;
        }

        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for spell preparation.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.PrepareSpellAsync(characterId, spellName);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async Task ShowPreparedSpellsAsync()
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for spell list.");
            return;
        }

        PreparedSpellListLite result = await advancedBackendApiService.GetPreparedSpellsAsync(characterId);
        if (result == null || !result.success)
        {
            AppendSystemMessage(result != null ? result.summary : "Prepared spell list unavailable.");
            return;
        }

        AppendSystemMessage(result.summary);
        if (result.spells != null)
        {
            for (int i = 0; i < result.spells.Length; i++)
            {
                PreparedSpellInfoLite spell = result.spells[i];
                AppendSystemMessage("- Lv" + spell.level + " " + spell.name + (string.IsNullOrWhiteSpace(spell.sourceClass) ? string.Empty : " [" + spell.sourceClass + "]") + (spell.alwaysPrepared ? " (always)" : string.Empty));
            }
        }
    }

    private async Task CastSpellAsync(int slotLevel, string spellName)
    {
        string characterId = GetActiveCharacterId();
        if (string.IsNullOrWhiteSpace(characterId))
        {
            AppendSystemMessage("No selected character for spell cast.");
            return;
        }

        CharacterActionResultLite result = await advancedBackendApiService.CastSpellAsync(characterId, slotLevel, spellName);
        AppendSystemMessage(result.summary);
        if (result.success)
        {
            await RefreshSelectedCharacterDetailsAsync();
        }
    }

    private async void RefreshLiveData()
    {
        AppendSystemMessage("Refreshing live room data...");
        await LoadLiveRoomDataAsync();
        await RefreshSelectedCharacterDetailsAsync();
        await RefreshAuditPanelAsync();
        if (EncounterBoardController.Instance != null)
        {
            await EncounterBoardController.Instance.LoadFromBackendAsync(RoomSessionContext.roomId, BackendConfig.EncounterMapId, RoomSessionContext.IsDM);
        }
        AppendSystemMessage("Live room data refreshed.");
    }

    private string GetActiveCharacterId()
    {
        CharacterData character = GetUploadedOrSelectedCharacter();
        if (character != null && !string.IsNullOrWhiteSpace(character.id))
        {
            return character.id;
        }
        return RoomSessionContext.currentCharacterId;
    }

    private List<string> SplitCsv(string csv)
    {
        List<string> values = new List<string>();
        if (string.IsNullOrWhiteSpace(csv))
        {
            return values;
        }

        string[] parts = csv.Split(new char[] { ',', '|' }, StringSplitOptions.RemoveEmptyEntries);
        for (int i = 0; i < parts.Length; i++)
        {
            string item = parts[i].Trim();
            if (!string.IsNullOrWhiteSpace(item))
            {
                values.Add(item);
            }
        }
        return values;
    }

    private string BuildRealtimeSummary(string payload, string fallback, string messageType)
    {
        string actor = JsonRegexUtility.ExtractString(payload, "owner_id");
        if (string.IsNullOrWhiteSpace(actor)) actor = JsonRegexUtility.ExtractString(payload, "actor_id");
        string name = JsonRegexUtility.ExtractString(payload, "name");
        string reason = JsonRegexUtility.ExtractString(payload, "reason");
        string effect = JsonRegexUtility.ExtractString(payload, "effect_name");
        string detail = JsonRegexUtility.ExtractString(payload, "detail");
        string response = JsonRegexUtility.ExtractString(payload, "response");
        int? total = JsonRegexUtility.ExtractInt(payload, "total");
        int? xpAfter = JsonRegexUtility.ExtractInt(payload, "xp_after");
        int? xpGained = JsonRegexUtility.ExtractInt(payload, "xp_gained");

        string summary = string.IsNullOrWhiteSpace(fallback) ? messageType : fallback;
        if (!string.IsNullOrWhiteSpace(response)) summary = response;
        else if (!string.IsNullOrWhiteSpace(detail)) summary = detail;
        else if (!string.IsNullOrWhiteSpace(effect)) summary = effect;
        else if (!string.IsNullOrWhiteSpace(reason)) summary = reason;
        else if (!string.IsNullOrWhiteSpace(name)) summary = name;

        if ((messageType == "xp_gain" || messageType == "loot_grant") && (xpGained.HasValue || xpAfter.HasValue))
        {
            summary = "XP update" + (xpGained.HasValue ? " +" + xpGained.Value : string.Empty) + (xpAfter.HasValue ? " -> " + xpAfter.Value : string.Empty);
        }

        if (total.HasValue && (messageType == "attack_result" || messageType == "saving_throw_result" || messageType == "death_save"))
        {
            summary += " | total=" + total.Value;
        }

        if (!string.IsNullOrWhiteSpace(actor))
        {
            summary = actor + ": " + summary;
        }

        return summary;
    }

    private async Task ApplyPreviewFromUrlAsync(string imageUrl, string title, string description, string label)
    {
        if (string.IsNullOrWhiteSpace(imageUrl))
        {
            return;
        }

        try
        {
            byte[] bytes = await AdvancedHttp.GetByteArrayAsync(imageUrl);
            SceneGenerationResult result = new SceneGenerationResult
            {
                success = bytes != null && bytes.Length > 0,
                sceneName = string.IsNullOrWhiteSpace(label) ? title : label,
                description = string.IsNullOrWhiteSpace(description) ? title : description,
                previewColor = new Color(0.35f, 0.42f, 0.50f, 1f),
                ambientPreset = "neutral",
                source = "backend",
                imageUrl = imageUrl,
                imageBytes = bytes
            };
            ApplySceneResult(result);
            if (sceneTitleText != null && !string.IsNullOrWhiteSpace(title))
            {
                sceneTitleText.text = title;
            }
        }
        catch (Exception ex)
        {
            AppendSystemMessage("Preview image load failed: " + ex.Message);
        }
    }
}
