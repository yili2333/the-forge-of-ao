using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

public class AdvancedBackendApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<WorldMapLite> GetWorldMapAsync(string campaignId)
    {
        WorldMapLite result = new WorldMapLite
        {
            success = false,
            id = string.Empty,
            name = string.Empty,
            description = string.Empty,
            imageUrl = string.Empty,
            poiCount = 0,
            summary = "World map unavailable."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetWorldMapUrl(campaignId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "World map request failed.");
                    return result;
                }

                result.success = true;
                result.id = JsonRegexUtility.ExtractString(body, "id");
                result.name = JsonRegexUtility.ExtractString(body, "name");
                result.description = JsonRegexUtility.ExtractString(body, "description");
                result.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(body, "image_url"));
                result.poiCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "pois")).Count;
                result.summary = string.IsNullOrWhiteSpace(result.name)
                    ? "World map loaded."
                    : "World map: " + result.name + " | POIs: " + result.poiCount + ".";
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<List<RegionMapSummaryLite>> GetRegionMapsAsync(string campaignId)
    {
        List<RegionMapSummaryLite> results = new List<RegionMapSummaryLite>();
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return results;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetRegionMapsUrl(campaignId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[AdvancedBackendApiService] Region list failed: " + ExtractDetailOrFallback(body, response, "Region list failed."));
                    return results;
                }

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(body);
                for (int i = 0; i < items.Count; i++)
                {
                    RegionMapSummaryLite entry = ParseRegionSummary(items[i]);
                    if (entry != null)
                    {
                        results.Add(entry);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[AdvancedBackendApiService] GetRegionMapsAsync failed: " + ex.Message);
        }

        return results;
    }

    public async Task<RegionMapLite> GetRegionMapAsync(string campaignId, string regionMapId)
    {
        RegionMapLite result = new RegionMapLite
        {
            success = false,
            id = string.Empty,
            name = string.Empty,
            description = string.Empty,
            regionType = string.Empty,
            imageUrl = string.Empty,
            poiCount = 0,
            summary = "Region map unavailable."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId) || string.IsNullOrWhiteSpace(regionMapId))
        {
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetRegionMapUrl(campaignId, regionMapId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Region map request failed.");
                    return result;
                }

                result.success = true;
                result.id = JsonRegexUtility.ExtractString(body, "id");
                result.name = JsonRegexUtility.ExtractString(body, "name");
                result.description = JsonRegexUtility.ExtractString(body, "description");
                result.regionType = JsonRegexUtility.ExtractString(body, "region_type");
                result.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(body, "image_url"));
                result.poiCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "pois")).Count;
                result.summary = string.IsNullOrWhiteSpace(result.name)
                    ? "Region map loaded."
                    : "Region map: " + result.name + " (" + result.regionType + ") | POIs: " + result.poiCount + ".";
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<List<MonsterSummaryLite>> SearchMonstersAsync(string query, int limit)
    {
        List<MonsterSummaryLite> results = new List<MonsterSummaryLite>();
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(query))
        {
            return results;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetMonstersSearchUrl(query, limit)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[AdvancedBackendApiService] Monster search failed: " + ExtractDetailOrFallback(body, response, "Monster search failed."));
                    return results;
                }

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "monsters"));
                for (int i = 0; i < items.Count; i++)
                {
                    MonsterSummaryLite monster = ParseMonsterSummary(items[i]);
                    if (monster != null)
                    {
                        results.Add(monster);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[AdvancedBackendApiService] SearchMonstersAsync failed: " + ex.Message);
        }

        return results;
    }

    public async Task<MonsterSummaryLite> GetMonsterByNameAsync(string name)
    {
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(name))
        {
            return null;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetMonsterByNameUrl(name)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    return null;
                }
                return ParseMonsterSummary(body);
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[AdvancedBackendApiService] GetMonsterByNameAsync failed: " + ex.Message);
            return null;
        }
    }

    public async Task<List<SessionLogEntryLite>> GetSessionLogAsync(string sessionId, int limit)
    {
        List<SessionLogEntryLite> results = new List<SessionLogEntryLite>();
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(sessionId))
        {
            return results;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetSessionLogUrl(sessionId, limit)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[AdvancedBackendApiService] Session log failed: " + ExtractDetailOrFallback(body, response, "Session log failed."));
                    return results;
                }

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(body);
                for (int i = 0; i < items.Count; i++)
                {
                    SessionLogEntryLite entry = new SessionLogEntryLite();
                    entry.opType = JsonRegexUtility.ExtractString(items[i], "op_type");
                    entry.actorId = JsonRegexUtility.ExtractString(items[i], "actor_id");
                    entry.roundNumber = JsonRegexUtility.ExtractInt(items[i], "round_number") ?? 0;
                    entry.timestamp = JsonRegexUtility.ExtractString(items[i], "ts");
                    string payload = JsonRegexUtility.ExtractObject(items[i], "payload");
                    entry.summary = BuildSessionLogSummary(entry.opType, entry.actorId, entry.roundNumber, payload);
                    results.Add(entry);
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[AdvancedBackendApiService] GetSessionLogAsync failed: " + ex.Message);
        }

        return results;
    }

    public async Task<CharacterActionResultLite> ApplyHpDeltaAsync(string characterId, int delta)
    {
        string payload = "{\"delta\":" + delta + "}";
        return await SendJsonAsync(new HttpMethod("PATCH"), BackendConfig.GetCharacterHpUrl(characterId), payload, false, "HP update sent.");
    }

    public async Task<CharacterActionResultLite> PatchConditionsAsync(string characterId, string action, List<string> conditions)
    {
        List<string> safeConditions = conditions ?? new List<string>();
        string conditionsJson = "[";
        for (int i = 0; i < safeConditions.Count; i++)
        {
            if (i > 0) conditionsJson += ",";
            conditionsJson += "\"" + CharacterSheetPayloadBuilder.Escape(safeConditions[i]) + "\"";
        }
        conditionsJson += "]";

        string payload = "{\"action\":\"" + CharacterSheetPayloadBuilder.Escape(action) + "\",\"conditions\":" + conditionsJson + "}";
        return await SendJsonAsync(new HttpMethod("PATCH"), BackendConfig.GetCharacterConditionsUrl(characterId), payload, false, "Conditions updated.");
    }

    public async Task<CharacterActionResultLite> ShortRestAsync(string characterId, List<string> hitDice)
    {
        List<string> safeDice = hitDice ?? new List<string>();
        string diceJson = "[";
        for (int i = 0; i < safeDice.Count; i++)
        {
            if (i > 0) diceJson += ",";
            diceJson += "\"" + CharacterSheetPayloadBuilder.Escape(safeDice[i]) + "\"";
        }
        diceJson += "]";

        string payload = "{\"hit_dice\":" + diceJson + "}";
        return await SendJsonAsync(HttpMethod.Post, BackendConfig.GetCharacterShortRestUrl(characterId), payload, false, "Short rest completed.");
    }

    public async Task<CharacterActionResultLite> LongRestAsync(string characterId)
    {
        return await SendJsonAsync(HttpMethod.Post, BackendConfig.GetCharacterLongRestUrl(characterId), "{}", false, "Long rest completed.");
    }

    public async Task<CharacterActionResultLite> GrantXpAsync(string characterId, int xpAmount, string note)
    {
        string payload = "{\"xp_amount\":" + xpAmount + ",\"note\":\"" + CharacterSheetPayloadBuilder.Escape(note ?? string.Empty) + "\"}";
        return await SendJsonAsync(HttpMethod.Post, BackendConfig.GetCharacterXpUrl(characterId), payload, RoomSessionContext.IsDM, "XP granted.");
    }

    public async Task<CharacterActionResultLite> PrepareSpellAsync(string characterId, string spellName)
    {
        string payload = "{\"spell_name\":\"" + CharacterSheetPayloadBuilder.Escape(spellName ?? string.Empty) + "\",\"class_name\":\"\"}";
        return await SendJsonAsync(HttpMethod.Post, BackendConfig.GetCharacterPrepareSpellUrl(characterId), payload, false, "Spell prepared.");
    }

    public async Task<PreparedSpellListLite> GetPreparedSpellsAsync(string characterId)
    {
        PreparedSpellListLite result = new PreparedSpellListLite
        {
            success = false,
            summary = "Prepared spell list unavailable.",
            spells = new PreparedSpellInfoLite[0]
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(characterId))
        {
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetCharacterPrepareSpellUrl(characterId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Prepared spell request failed.");
                    return result;
                }

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "prepared_spells"));
                List<PreparedSpellInfoLite> spells = new List<PreparedSpellInfoLite>();
                for (int i = 0; i < items.Count; i++)
                {
                    PreparedSpellInfoLite spell = new PreparedSpellInfoLite();
                    spell.name = JsonRegexUtility.ExtractString(items[i], "name");
                    spell.sourceClass = JsonRegexUtility.ExtractString(items[i], "source_class");
                    spell.level = JsonRegexUtility.ExtractInt(items[i], "level") ?? 0;
                    spell.prepared = JsonRegexUtility.ExtractBool(items[i], "prepared") ?? false;
                    spell.alwaysPrepared = JsonRegexUtility.ExtractBool(items[i], "always_prepared") ?? false;
                    spells.Add(spell);
                }

                result.success = true;
                result.spells = spells.ToArray();
                result.summary = "Prepared spells loaded: " + spells.Count + ".";
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<CharacterActionResultLite> CastSpellAsync(string characterId, int slotLevel, string spellName)
    {
        string payload = "{\"spell_name\":\"" + CharacterSheetPayloadBuilder.Escape(spellName ?? string.Empty) + "\",\"slot_level\":" + Mathf.Clamp(slotLevel, 1, 9) + ",\"is_pact_slot\":false,\"requires_concentration\":false,\"concentration_effect_id\":\"\"}";
        return await SendJsonAsync(HttpMethod.Post, BackendConfig.GetCharacterCastSpellUrl(characterId), payload, false, "Spell cast registered.");
    }


    public async Task<RegionMapLite> CreateRegionMapAsync(string campaignId, string name, string description, string regionType)
    {
        RegionMapLite result = new RegionMapLite
        {
            success = false,
            id = string.Empty,
            name = string.Empty,
            description = string.Empty,
            regionType = string.Empty,
            imageUrl = string.Empty,
            poiCount = 0,
            summary = "Create region map failed."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return result;
        }

        string payload =
            "{\"name\":\"" + CharacterSheetPayloadBuilder.Escape(name ?? "") + "\"," +
            "\"description\":\"" + CharacterSheetPayloadBuilder.Escape(description ?? "") + "\"," +
            "\"region_type\":\"" + CharacterSheetPayloadBuilder.Escape(string.IsNullOrWhiteSpace(regionType) ? "other" : regionType) + "\"," +
            "\"area_km\":10.0}";

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, BackendConfig.GetCreateRegionMapUrl(campaignId)))
            {
                AddCommonHeaders(request, true);
                request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Create region map failed.");
                    return result;
                }

                result.success = true;
                result.id = JsonRegexUtility.ExtractString(body, "id");
                result.name = JsonRegexUtility.ExtractString(body, "name");
                result.description = JsonRegexUtility.ExtractString(body, "description");
                result.regionType = JsonRegexUtility.ExtractString(body, "region_type");
                result.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(body, "image_url"));
                result.poiCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "pois")).Count;
                result.summary = "Region map created: " + result.name + " | id=" + result.id;
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<RegionMapLite> GenerateRegionMapAsync(string campaignId, string regionMapId, string prompt)
    {
        RegionMapLite result = new RegionMapLite
        {
            success = false,
            id = regionMapId ?? string.Empty,
            name = string.Empty,
            description = string.Empty,
            regionType = string.Empty,
            imageUrl = string.Empty,
            poiCount = 0,
            summary = "Region map generate failed."
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId) || string.IsNullOrWhiteSpace(regionMapId))
        {
            return result;
        }

        string payload =
            "{\"prompt\":\"" + CharacterSheetPayloadBuilder.Escape(prompt ?? "") + "\"," +
            "\"width_px\":1024," +
            "\"height_px\":1024," +
            "\"save_prompt\":true}";

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, BackendConfig.GetGenerateRegionMapUrl(campaignId, regionMapId)))
            {
                AddCommonHeaders(request, true);
                request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Region map generate failed.");
                    return result;
                }

                result.success = true;
                result.id = JsonRegexUtility.ExtractString(body, "id");
                result.name = JsonRegexUtility.ExtractString(body, "name");
                result.description = JsonRegexUtility.ExtractString(body, "description");
                result.regionType = JsonRegexUtility.ExtractString(body, "region_type");
                result.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(body, "image_url"));
                result.poiCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "pois")).Count;
                result.summary = "Region map generated: " + result.name + " | id=" + result.id;
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<List<EncounterMapSummaryLite>> GetEncounterMapsAsync(string campaignId)
    {
        List<EncounterMapSummaryLite> results = new List<EncounterMapSummaryLite>();
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return results;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetEncounterMapsUrl(campaignId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[AdvancedBackendApiService] Encounter map list failed: " + ExtractDetailOrFallback(body, response, "Encounter map list failed."));
                    return results;
                }

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(body);
                for (int i = 0; i < items.Count; i++)
                {
                    EncounterMapSummaryLite entry = ParseEncounterMapSummary(items[i]);
                    if (entry != null)
                    {
                        results.Add(entry);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[AdvancedBackendApiService] GetEncounterMapsAsync failed: " + ex.Message);
        }

        return results;
    }

    public async Task<CharacterActionResultLite> SimulateEncounterAsync(string campaignId, string mapId)
    {
        return await SendJsonAsync(
            HttpMethod.Post,
            BackendConfig.GetEncounterSimulateUrl(campaignId, mapId),
            "{}",
            true,
            "Encounter simulated.");
    }

    public async Task<CharacterActionResultLite> RollInitiativeAsync(string campaignId, string mapId)
    {
        return await SendJsonAsync(
            HttpMethod.Post,
            BackendConfig.GetEncounterRollInitiativeUrl(campaignId, mapId),
            "{}",
            true,
            "Initiative rolled.");
    }

    public async Task<BrowseResultLite> BrowseRulesAsync(string path)
    {
        BrowseResultLite result = new BrowseResultLite
        {
            success = false,
            currentPath = string.Empty,
            parentPath = string.Empty,
            totalHtm = 0,
            totalPdf = 0,
            summary = "Rules browse failed.",
            entries = new BrowseEntryLite[0]
        };

        if (BackendConfig.UseMockServices)
        {
            result.summary = "Backend unavailable in mock mode.";
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetRulesBrowseUrl(path)))
            {
                AddCommonHeaders(request, true);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Rules browse failed.");
                    return result;
                }

                result.success = true;
                result.currentPath = JsonRegexUtility.ExtractString(body, "current_path");
                result.parentPath = JsonRegexUtility.ExtractString(body, "parent_path");
                result.totalHtm = JsonRegexUtility.ExtractInt(body, "total_htm") ?? 0;
                result.totalPdf = JsonRegexUtility.ExtractInt(body, "total_pdf") ?? 0;

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "entries"));
                List<BrowseEntryLite> entries = new List<BrowseEntryLite>();
                for (int i = 0; i < items.Count; i++)
                {
                    BrowseEntryLite entry = ParseBrowseEntry(items[i]);
                    if (entry != null)
                    {
                        entries.Add(entry);
                    }
                }

                result.entries = entries.ToArray();
                result.summary = "Browse: " + result.currentPath + " | entries=" + result.entries.Length + " | htm=" + result.totalHtm + " | pdf=" + result.totalPdf;
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    public async Task<ScanImportResultLite> ScanRulesAsync(string rootPath, bool dryRun = false)
    {
        ScanImportResultLite result = new ScanImportResultLite
        {
            success = false,
            rootPath = rootPath ?? string.Empty,
            booksFound = 0,
            booksImported = 0,
            totalChunks = 0,
            totalConflicts = 0,
            dryRun = dryRun,
            message = "Rules scan failed.",
            results = new ScanBookResultLite[0]
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(rootPath))
        {
            result.message = "Rules scan path is empty or backend is in mock mode.";
            return result;
        }

        string payload =
            "{\"root_path\":\"" + CharacterSheetPayloadBuilder.Escape(rootPath) + "\"," +
            "\"check_conflicts\":true," +
            "\"dry_run\":" + (dryRun ? "true" : "false") + "," +
            "\"max_chunk_chars\":2500," +
            "\"source_override\":\"\"}";

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, BackendConfig.GetRulesScanUrl()))
            {
                AddCommonHeaders(request, true);
                request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    result.message = ExtractDetailOrFallback(body, response, "Rules scan failed.");
                    return result;
                }

                result.success = JsonRegexUtility.ExtractBool(body, "success") ?? true;
                result.rootPath = JsonRegexUtility.ExtractString(body, "root_path");
                result.booksFound = JsonRegexUtility.ExtractInt(body, "books_found") ?? 0;
                result.booksImported = JsonRegexUtility.ExtractInt(body, "books_imported") ?? 0;
                result.totalChunks = JsonRegexUtility.ExtractInt(body, "total_chunks") ?? 0;
                result.totalConflicts = JsonRegexUtility.ExtractInt(body, "total_conflicts") ?? 0;
                result.dryRun = JsonRegexUtility.ExtractBool(body, "dry_run") ?? dryRun;
                result.message = JsonRegexUtility.ExtractString(body, "message");

                List<string> items = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(body, "results"));
                List<ScanBookResultLite> parsed = new List<ScanBookResultLite>();
                for (int i = 0; i < items.Count; i++)
                {
                    ScanBookResultLite item = ParseScanBookResult(items[i]);
                    if (item != null)
                    {
                        parsed.Add(item);
                    }
                }

                result.results = parsed.ToArray();
                if (string.IsNullOrWhiteSpace(result.message))
                {
                    result.message = "Rules scan completed.";
                }

                return result;
            }
        }
        catch (Exception ex)
        {
            result.message = ex.Message;
            return result;
        }
    }

    private async Task<CharacterActionResultLite> SendJsonAsync(HttpMethod method, string url, string payload, bool dm, string successFallback)
    {
        CharacterActionResultLite result = new CharacterActionResultLite
        {
            success = false,
            summary = "Action not sent.",
            detail = string.Empty,
            rawJson = string.Empty
        };

        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(url))
        {
            result.summary = "Backend unavailable in mock mode.";
            return result;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(method, url))
            {
                AddCommonHeaders(request, dm);
                request.Content = new StringContent(payload ?? "{}", Encoding.UTF8, "application/json");
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                result.rawJson = body;
                if (!response.IsSuccessStatusCode)
                {
                    result.summary = ExtractDetailOrFallback(body, response, "Action failed.");
                    return result;
                }

                result.success = true;
                result.summary = BuildActionSuccessSummary(body, successFallback);
                result.detail = body;
                return result;
            }
        }
        catch (Exception ex)
        {
            result.summary = ex.Message;
            return result;
        }
    }

    private string BuildActionSuccessSummary(string body, string fallback)
    {
        string hp = JsonRegexUtility.ExtractObject(body, "hit_points");
        if (!string.IsNullOrWhiteSpace(hp))
        {
            int? current = JsonRegexUtility.ExtractInt(hp, "current");
            int? maximum = JsonRegexUtility.ExtractInt(hp, "maximum");
            if (current.HasValue || maximum.HasValue)
            {
                return fallback + " HP " + (current.HasValue ? current.Value.ToString() : "?") + "/" + (maximum.HasValue ? maximum.Value.ToString() : "?") + ".";
            }
        }

        string resultObject = JsonRegexUtility.ExtractObject(body, "result");
        if (!string.IsNullOrWhiteSpace(resultObject))
        {
            int? hpGained = JsonRegexUtility.ExtractInt(resultObject, "hp_gained");
            if (hpGained.HasValue)
            {
                return fallback + " HP gained: " + hpGained.Value + ".";
            }
        }

        string detail = JsonRegexUtility.ExtractString(body, "detail");
        return string.IsNullOrWhiteSpace(detail) ? fallback : detail;
    }


    private EncounterMapSummaryLite ParseEncounterMapSummary(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        EncounterMapSummaryLite entry = new EncounterMapSummaryLite();
        entry.id = JsonRegexUtility.ExtractString(json, "id");
        if (string.IsNullOrWhiteSpace(entry.id))
        {
            return null;
        }

        entry.name = JsonRegexUtility.ExtractString(json, "name");
        entry.gridCols = JsonRegexUtility.ExtractInt(json, "grid_cols") ?? 0;
        entry.gridRows = JsonRegexUtility.ExtractInt(json, "grid_rows") ?? 0;
        entry.creatureCount = JsonRegexUtility.ExtractInt(json, "creature_count") ?? 0;
        entry.isActive = JsonRegexUtility.ExtractBool(json, "is_active") ?? false;
        entry.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(json, "image_url"));
        entry.summary = entry.id + " | " + entry.name + " | " + entry.gridCols + "x" + entry.gridRows + " | creatures=" + entry.creatureCount + (entry.isActive ? " | active" : string.Empty);
        return entry;
    }

    private BrowseEntryLite ParseBrowseEntry(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        BrowseEntryLite entry = new BrowseEntryLite();
        entry.name = JsonRegexUtility.ExtractString(json, "name");
        entry.path = JsonRegexUtility.ExtractString(json, "path");
        entry.isDir = JsonRegexUtility.ExtractBool(json, "is_dir") ?? false;
        entry.htmCount = JsonRegexUtility.ExtractInt(json, "htm_count") ?? 0;
        entry.pdfCount = JsonRegexUtility.ExtractInt(json, "pdf_count") ?? 0;
        return entry;
    }

    private ScanBookResultLite ParseScanBookResult(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        ScanBookResultLite entry = new ScanBookResultLite();
        entry.subdir = JsonRegexUtility.ExtractString(json, "subdir");
        entry.fullPath = JsonRegexUtility.ExtractString(json, "full_path");
        entry.detectedSource = JsonRegexUtility.ExtractString(json, "detected_source");
        entry.detectedName = JsonRegexUtility.ExtractString(json, "detected_name");
        entry.filesFound = JsonRegexUtility.ExtractInt(json, "files_found") ?? 0;
        entry.chunksCreated = JsonRegexUtility.ExtractInt(json, "chunks_created") ?? 0;
        entry.conflictsFound = JsonRegexUtility.ExtractInt(json, "conflicts_found") ?? 0;
        entry.skipped = JsonRegexUtility.ExtractBool(json, "skipped") ?? false;
        entry.skipReason = JsonRegexUtility.ExtractString(json, "skip_reason");
        entry.errors = JsonRegexUtility.ExtractStringArray(json, "errors").ToArray();
        return entry;
    }

    private RegionMapSummaryLite ParseRegionSummary(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        RegionMapSummaryLite entry = new RegionMapSummaryLite();
        entry.id = JsonRegexUtility.ExtractString(json, "id");
        if (string.IsNullOrWhiteSpace(entry.id))
        {
            return null;
        }
        entry.name = JsonRegexUtility.ExtractString(json, "name");
        entry.description = JsonRegexUtility.ExtractString(json, "description");
        entry.regionType = JsonRegexUtility.ExtractString(json, "region_type");
        entry.imageUrl = BackendConfig.ResolveAssetUrl(JsonRegexUtility.ExtractString(json, "image_url"));
        entry.poiCount = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(json, "pois")).Count;
        return entry;
    }

    private MonsterSummaryLite ParseMonsterSummary(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        MonsterSummaryLite monster = new MonsterSummaryLite();
        monster.id = JsonRegexUtility.ExtractString(json, "id");
        monster.name = JsonRegexUtility.ExtractString(json, "name_cn");
        if (string.IsNullOrWhiteSpace(monster.name)) monster.name = JsonRegexUtility.ExtractString(json, "name");
        string englishName = JsonRegexUtility.ExtractString(json, "name_en");
        string creatureType = JsonRegexUtility.ExtractString(json, "creature_type");
        string size = JsonRegexUtility.ExtractString(json, "size");
        monster.subtitle = string.IsNullOrWhiteSpace(creatureType) ? englishName : creatureType + (string.IsNullOrWhiteSpace(size) ? string.Empty : " / " + size);
        string cr = JsonRegexUtility.ExtractString(json, "cr");
        if (string.IsNullOrWhiteSpace(cr))
        {
            int? crInt = JsonRegexUtility.ExtractInt(json, "cr");
            if (crInt.HasValue) cr = crInt.Value.ToString();
        }
        monster.crText = string.IsNullOrWhiteSpace(cr) ? string.Empty : "CR " + cr;
        monster.summary = monster.name + (string.IsNullOrWhiteSpace(monster.crText) ? string.Empty : " | " + monster.crText) + (string.IsNullOrWhiteSpace(monster.subtitle) ? string.Empty : " | " + monster.subtitle);
        return monster;
    }

    private string BuildSessionLogSummary(string opType, string actorId, int roundNumber, string payload)
    {
        string prefix = string.IsNullOrWhiteSpace(actorId) ? opType : actorId + " -> " + opType;
        if (roundNumber > 0)
        {
            prefix += " (R" + roundNumber + ")";
        }

        if (string.IsNullOrWhiteSpace(payload))
        {
            return prefix;
        }

        string text = JsonRegexUtility.ExtractString(payload, "text");
        if (!string.IsNullOrWhiteSpace(text)) return prefix + ": " + text;
        string reason = JsonRegexUtility.ExtractString(payload, "reason");
        if (!string.IsNullOrWhiteSpace(reason)) return prefix + ": " + reason;
        string name = JsonRegexUtility.ExtractString(payload, "name");
        if (!string.IsNullOrWhiteSpace(name)) return prefix + ": " + name;
        string instanceId = JsonRegexUtility.ExtractString(payload, "instance_id");
        int? x = JsonRegexUtility.ExtractInt(payload, "x");
        int? y = JsonRegexUtility.ExtractInt(payload, "y");
        if (!string.IsNullOrWhiteSpace(instanceId) && x.HasValue && y.HasValue)
        {
            return prefix + ": " + instanceId + " -> (" + x.Value + "," + y.Value + ")";
        }

        return prefix;
    }

    private string ExtractDetailOrFallback(string body, HttpResponseMessage response, string fallback)
    {
        string detail = JsonRegexUtility.ExtractString(body, "detail");
        if (!string.IsNullOrWhiteSpace(detail))
        {
            return detail;
        }
        return fallback + " HTTP " + (int)response.StatusCode + ".";
    }

    private void AddCommonHeaders(HttpRequestMessage request, bool dm)
    {
        request.Headers.Remove("X-Owner-Id");
        request.Headers.Remove("X-Owner-Display");
        request.Headers.Remove("X-Role");
        request.Headers.TryAddWithoutValidation("X-Owner-Id", BackendConfig.OwnerId);
        request.Headers.TryAddWithoutValidation("X-Owner-Display", BackendConfig.OwnerId);
        if (dm || RoomSessionContext.IsDM)
        {
            request.Headers.TryAddWithoutValidation("X-Role", "dm");
        }
    }
}
