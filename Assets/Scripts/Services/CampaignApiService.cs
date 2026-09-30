using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using UnityEngine;

public class CampaignApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<CampaignOverviewLite> GetCampaignOverviewAsync(string campaignId)
    {
        CampaignOverviewLite result = new CampaignOverviewLite
        {
            success = false,
            campaignName = campaignId,
            activeEncounterMapId = string.Empty,
            summary = "Campaign overview unavailable."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetCampaignOverviewUrl(campaignId)))
            {
                AddCommonHeaders(request, true);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = JsonRegexUtility.ExtractString(body, "detail");
                    if (string.IsNullOrWhiteSpace(result.summary))
                    {
                        result.summary = "Campaign overview failed with HTTP " + (int)response.StatusCode + ".";
                    }
                    return result;
                }

                string campaignObject = JsonRegexUtility.ExtractObject(body, "campaign");
                result.success = true;
                result.campaignName = JsonRegexUtility.ExtractString(campaignObject, "name");
                result.characterCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "characters")).Count;
                result.encounterMapCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "encounter_maps")).Count;
                result.monsterInPlayCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "monsters_in_play")).Count;

                List<string> encounterMaps = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "encounter_maps"));
                foreach (string item in encounterMaps)
                {
                    bool isActive = JsonRegexUtility.ExtractBool(item, "is_active") ?? false;
                    string id = JsonRegexUtility.ExtractString(item, "id");
                    if (isActive && !string.IsNullOrWhiteSpace(id))
                    {
                        result.activeEncounterMapId = id;
                        break;
                    }
                }

                if (string.IsNullOrWhiteSpace(result.activeEncounterMapId) && encounterMaps.Count > 0)
                {
                    result.activeEncounterMapId = JsonRegexUtility.ExtractString(encounterMaps[0], "id");
                }

                result.summary = string.IsNullOrWhiteSpace(result.campaignName)
                    ? "Campaign overview loaded."
                    : "Campaign " + result.campaignName + " loaded. Characters: " + result.characterCount + ", encounter maps: " + result.encounterMapCount + ", monsters in play: " + result.monsterInPlayCount + ".";
                return result;
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CampaignApiService] Overview failed: " + ex.Message);
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<SessionSnapshotLite> GetLatestSessionAsync(string campaignId)
    {
        SessionSnapshotLite result = new SessionSnapshotLite
        {
            success = false,
            sessionId = string.Empty,
            activeEncounterMapId = string.Empty,
            summary = "No latest session data."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetCampaignLatestSessionUrl(campaignId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = JsonRegexUtility.ExtractString(body, "detail");
                    if (string.IsNullOrWhiteSpace(result.summary))
                    {
                        result.summary = "Latest session request failed with HTTP " + (int)response.StatusCode + ".";
                    }
                    return result;
                }

                result.success = true;
                result.sessionId = JsonRegexUtility.ExtractString(body, "id");
                result.activeEncounterMapId = JsonRegexUtility.ExtractString(body, "active_encounter_map_id");
                result.roundNumber = JsonRegexUtility.ExtractInt(body, "round_number") ?? 0;
                result.currentTurn = JsonRegexUtility.ExtractInt(body, "current_turn_index") ?? 0;
                result.summary = string.IsNullOrWhiteSpace(result.sessionId)
                    ? "Latest session restored."
                    : "Session " + result.sessionId + " restored. Round " + result.roundNumber + ".";
                return result;
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CampaignApiService] Latest session failed: " + ex.Message);
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<int?> GetMonsterCountAsync()
    {
        if (BackendConfig.UseMockServices)
        {
            return null;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetMonstersCountUrl()))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    return null;
                }
                return JsonRegexUtility.ExtractInt(body, "count");
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CampaignApiService] Monster count failed: " + ex.Message);
            return null;
        }
    }

    public async Task<EncounterMapData> GetEncounterMapAsync(string campaignId, string encounterMapId, bool dmView)
    {
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId) || string.IsNullOrWhiteSpace(encounterMapId))
        {
            return null;
        }

        try
        {
            string url = dmView
                ? BackendConfig.GetEncounterMapDmViewUrl(campaignId, encounterMapId)
                : BackendConfig.GetEncounterMapUrl(campaignId, encounterMapId);

            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, url))
            {
                AddCommonHeaders(request, dmView);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[CampaignApiService] Encounter map load failed: HTTP " + (int)response.StatusCode + " body=" + body);
                    return null;
                }
                return ParseEncounterMap(body);
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CampaignApiService] Encounter map failed: " + ex.Message);
            return null;
        }
    }

    private EncounterMapData ParseEncounterMap(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
        {
            return null;
        }

        EncounterMapData map = new EncounterMapData();
        map.id = JsonRegexUtility.ExtractString(body, "id");
        map.campaign_id = JsonRegexUtility.ExtractString(body, "campaign_id");
        map.name = JsonRegexUtility.ExtractString(body, "name");
        map.grid_cols = JsonRegexUtility.ExtractInt(body, "grid_cols") ?? 20;
        map.grid_rows = JsonRegexUtility.ExtractInt(body, "grid_rows") ?? 20;
        map.cell_size_ft = JsonRegexUtility.ExtractInt(body, "cell_size_ft") ?? 5;
        map.image_url = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(body, "image_url"));
        map.cells = ParseCells(JsonRegexUtility.ExtractArray(body, "cells"), map.grid_rows, map.grid_cols);
        map.creatures = ParseCreatures(JsonRegexUtility.ExtractArray(body, "creatures"));
        return map;
    }

    private List<List<string>> ParseCells(string cellsJson, int rows, int cols)
    {
        List<List<string>> cells = new List<List<string>>();
        List<string> rowArrays = JsonRegexUtility.SplitTopLevelArrays(cellsJson);

        if (rowArrays.Count == 0)
        {
            for (int r = 0; r < rows; r++)
            {
                List<string> row = new List<string>();
                for (int c = 0; c < cols; c++) row.Add(TerrainType.Open);
                cells.Add(row);
            }
            return cells;
        }

        foreach (string rowJson in rowArrays)
        {
            List<string> row = new List<string>();
            List<string> cellObjects = JsonRegexUtility.SplitTopLevelObjects(rowJson);
            foreach (string cellJson in cellObjects)
            {
                string terrain = JsonRegexUtility.ExtractString(cellJson, "terrain");
                row.Add(string.IsNullOrWhiteSpace(terrain) ? TerrainType.Open : terrain);
            }
            cells.Add(row);
        }

        return cells;
    }

    private List<MapCreatureData> ParseCreatures(string creaturesJson)
    {
        List<MapCreatureData> creatures = new List<MapCreatureData>();
        List<string> objects = JsonRegexUtility.SplitTopLevelObjects(creaturesJson);
        for (int i = 0; i < objects.Count; i++)
        {
            string item = objects[i];
            MapCreatureData creature = new MapCreatureData();
            creature.instance_id = JsonRegexUtility.ExtractString(item, "instance_id");
            creature.name = JsonRegexUtility.ExtractString(item, "name");
            creature.monster_id = JsonRegexUtility.ExtractString(item, "monster_id");
            creature.character_id = JsonRegexUtility.ExtractString(item, "character_id");
            creature.x = JsonRegexUtility.ExtractInt(item, "x") ?? 0;
            creature.y = JsonRegexUtility.ExtractInt(item, "y") ?? 0;
            creature.hp_current = JsonRegexUtility.ExtractInt(item, "hp_current") ?? 0;
            creature.hp_max = JsonRegexUtility.ExtractInt(item, "hp_max") ?? 0;
            creature.speed = JsonRegexUtility.ExtractInt(item, "speed") ?? 30;
            creature.movement_used = JsonRegexUtility.ExtractInt(item, "movement_used") ?? 0;
            creature.is_player = JsonRegexUtility.ExtractBool(item, "is_player") ?? false;
            creature.is_hidden = JsonRegexUtility.ExtractBool(item, "is_hidden") ?? false;
            creature.initiative = JsonRegexUtility.ExtractInt(item, "initiative") ?? 0;
            creature.action_used = JsonRegexUtility.ExtractBool(item, "action_used") ?? false;
            creature.bonus_action_used = JsonRegexUtility.ExtractBool(item, "bonus_action_used") ?? false;
            creature.reaction_used = JsonRegexUtility.ExtractBool(item, "reaction_used") ?? false;
            creature.conditions = JsonRegexUtility.ExtractStringArray(item, "conditions");
            if (!string.IsNullOrWhiteSpace(creature.instance_id))
            {
                creatures.Add(creature);
            }
        }
        return creatures;
    }

    private void AddCommonHeaders(HttpRequestMessage request, bool dm)
    {
        request.Headers.TryAddWithoutValidation("X-Owner-Id", BackendConfig.OwnerId);
        if (dm)
        {
            request.Headers.TryAddWithoutValidation("X-Role", "dm");
        }
    }
}
