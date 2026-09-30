using System;
using UnityEngine;

public static class BackendConfig
{
    private const string HttpHostKey = "forge.backend.http.host";
    private const string HttpPortKey = "forge.backend.http.port";
    private const string WsHostKey = "forge.backend.ws.host";
    private const string WsPortKey = "forge.backend.ws.port";
    private const string OwnerIdKey = "forge.backend.owner_id";
    private const string EncounterMapIdKey = "forge.backend.encounter_map_id";
    private const string UseMocksKey = "forge.backend.use_mocks";
    private const string BgmEnabledKey = "forge.audio.enabled";
    private const string BgmVolumeKey = "forge.audio.volume";

    public static string HttpHost
    {
        get { return PlayerPrefs.GetString(HttpHostKey, "127.0.0.1"); }
        set { PlayerPrefs.SetString(HttpHostKey, string.IsNullOrWhiteSpace(value) ? "127.0.0.1" : value.Trim()); }
    }

    public static int HttpPort
    {
        get { return Mathf.Clamp(PlayerPrefs.GetInt(HttpPortKey, 8000), 1, 65535); }
        set { PlayerPrefs.SetInt(HttpPortKey, Mathf.Clamp(value, 1, 65535)); }
    }

    public static string WsHost
    {
        get { return PlayerPrefs.GetString(WsHostKey, HttpHost); }
        set { PlayerPrefs.SetString(WsHostKey, string.IsNullOrWhiteSpace(value) ? HttpHost : value.Trim()); }
    }

    public static int WsPort
    {
        get { return Mathf.Clamp(PlayerPrefs.GetInt(WsPortKey, 8000), 1, 65535); }
        set { PlayerPrefs.SetInt(WsPortKey, Mathf.Clamp(value, 1, 65535)); }
    }

    public static string OwnerId
    {
        get { return PlayerPrefs.GetString(OwnerIdKey, "player-001"); }
        set { PlayerPrefs.SetString(OwnerIdKey, string.IsNullOrWhiteSpace(value) ? "player-001" : value.Trim()); }
    }

    public static string EncounterMapId
    {
        get { return PlayerPrefs.GetString(EncounterMapIdKey, "main"); }
        set { PlayerPrefs.SetString(EncounterMapIdKey, string.IsNullOrWhiteSpace(value) ? "main" : value.Trim()); }
    }

    public static bool UseMockServices
    {
        get { return PlayerPrefs.GetInt(UseMocksKey, 0) == 1; }
        set { PlayerPrefs.SetInt(UseMocksKey, value ? 1 : 0); }
    }

    public static bool BgmEnabled
    {
        get { return PlayerPrefs.GetInt(BgmEnabledKey, 1) == 1; }
        set { PlayerPrefs.SetInt(BgmEnabledKey, value ? 1 : 0); }
    }

    public static float BgmVolume
    {
        get { return Mathf.Clamp01(PlayerPrefs.GetFloat(BgmVolumeKey, 0.35f)); }
        set { PlayerPrefs.SetFloat(BgmVolumeKey, Mathf.Clamp01(value)); }
    }

    public static string BaseHttpUrl
    {
        get { return "http://" + HttpHost + ":" + HttpPort; }
    }

    public static string BaseWsUrl
    {
        get { return "ws://" + WsHost + ":" + WsPort; }
    }

    public static string QueryUrl
    {
        get { return BuildHttpUrl("/api/query"); }
    }

    public static string CharacterCreateUrl
    {
        get { return BuildHttpUrl("/api/character"); }
    }

    public static string CharacterImportUrl
    {
        get { return BuildHttpUrl("/api/character/import"); }
    }

    public static string HealthUrl
    {
        get { return BuildHttpUrl("/api/health"); }
    }

    public static string BuildHttpUrl(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return BaseHttpUrl;
        }

        return path.StartsWith("http", StringComparison.OrdinalIgnoreCase) ? path : BaseHttpUrl + (path.StartsWith("/") ? path : "/" + path);
    }

    public static string GetCharacterUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty));
    }

    public static string GetCharacterSummaryUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/summary");
    }

    public static string GetCharacterApproveUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/approve");
    }

    public static string GetCharacterAskUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/ask");
    }

    public static string GetSceneGenerateUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps/" + Uri.EscapeDataString(mapId ?? string.Empty) + "/generate-bg");
    }

    public static string GetListCharactersMineUrl()
    {
        return BuildHttpUrl("/api/character?scope=mine");
    }

    public static string GetListCharactersCampaignUrl(string campaignId)
    {
        return BuildHttpUrl("/api/character?scope=campaign&campaign_id=" + Uri.EscapeDataString(campaignId ?? string.Empty));
    }

    public static string GetCampaignOverviewUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/overview");
    }

    public static string GetCampaignLatestSessionUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/sessions/latest");
    }

    public static string GetEncounterMapUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps/" + Uri.EscapeDataString(mapId ?? string.Empty));
    }

    public static string GetEncounterMapDmViewUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps/" + Uri.EscapeDataString(mapId ?? string.Empty) + "/dm-view");
    }

    public static string GetMonstersCountUrl()
    {
        return BuildHttpUrl("/api/monsters/count");
    }


    public static string GetWorldMapUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/world-map");
    }

    public static string GetRegionMapsUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/region-maps");
    }

    public static string GetRegionMapUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/region-maps/" + Uri.EscapeDataString(mapId ?? string.Empty));
    }

    public static string GetCreateRegionMapUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/region-maps");
    }

    public static string GetGenerateRegionMapUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/region-maps/" + Uri.EscapeDataString(mapId ?? string.Empty) + "/generate");
    }

    public static string GetEncounterMapsUrl(string campaignId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps");
    }

    public static string GetEncounterSimulateUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps/" + Uri.EscapeDataString(mapId ?? string.Empty) + "/simulate");
    }

    public static string GetEncounterRollInitiativeUrl(string campaignId, string mapId)
    {
        return BuildHttpUrl("/api/campaign/" + Uri.EscapeDataString(campaignId ?? string.Empty) + "/encounter-maps/" + Uri.EscapeDataString(mapId ?? string.Empty) + "/roll-initiative");
    }

    public static string GetRulesBrowseUrl(string path)
    {
        return BuildHttpUrl("/api/import/rules/browse?path=" + Uri.EscapeDataString(path ?? string.Empty));
    }

    public static string GetRulesScanUrl()
    {
        return BuildHttpUrl("/api/import/rules/scan");
    }

    public static string GetSessionLogUrl(string sessionId, int limit)
    {
        return BuildHttpUrl("/api/session/" + Uri.EscapeDataString(sessionId ?? string.Empty) + "/log?limit=" + Mathf.Clamp(limit, 1, 200));
    }

    public static string GetMonstersSearchUrl(string query, int limit)
    {
        return BuildHttpUrl("/api/monsters?q=" + Uri.EscapeDataString(query ?? string.Empty) + "&limit=" + Mathf.Clamp(limit, 1, 50));
    }

    public static string GetMonsterByNameUrl(string name)
    {
        return BuildHttpUrl("/api/monsters/by-name/" + Uri.EscapeDataString(name ?? string.Empty));
    }

    public static string GetCharacterHpUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/hp");
    }

    public static string GetCharacterConditionsUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/conditions");
    }

    public static string GetCharacterShortRestUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/short-rest");
    }

    public static string GetCharacterLongRestUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/long-rest");
    }

    public static string GetCharacterXpUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/xp");
    }

    public static string GetCharacterPrepareSpellUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/spells/prepare");
    }

    public static string GetCharacterCastSpellUrl(string characterId)
    {
        return BuildHttpUrl("/api/character/" + Uri.EscapeDataString(characterId ?? string.Empty) + "/cast-spell");
    }

    public static string GetSessionWebSocketUrl(string campaignId, string ownerId, string role, string characterId)
    {
        string safeCampaign = string.IsNullOrWhiteSpace(campaignId) ? "ROOM-001" : campaignId.Trim();
        string safeOwner = string.IsNullOrWhiteSpace(ownerId) ? OwnerId : ownerId.Trim();
        string safeRole = string.IsNullOrWhiteSpace(role) ? "player" : role.Trim().ToLowerInvariant();
        string displayName = safeOwner.Contains("#") ? safeOwner.Split('#')[0] : safeOwner;

        string url = BaseWsUrl + "/ws/" + Uri.EscapeDataString(safeCampaign) +
                     "?owner_id=" + Uri.EscapeDataString(safeOwner) +
                     "&role=" + Uri.EscapeDataString(safeRole) +
                     "&display_name=" + Uri.EscapeDataString(displayName);

        if (!string.IsNullOrWhiteSpace(characterId))
        {
            url += "&character_id=" + Uri.EscapeDataString(characterId.Trim());
        }

        return url;
    }

    public static string ResolveAssetUrl(string maybeRelative)
    {
        if (string.IsNullOrWhiteSpace(maybeRelative))
        {
            return string.Empty;
        }

        if (maybeRelative.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || maybeRelative.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            return maybeRelative;
        }

        return BuildHttpUrl(maybeRelative);
    }

    public static void ResetDefaults()
    {
        HttpHost = "127.0.0.1";
        HttpPort = 8000;
        WsHost = "127.0.0.1";
        WsPort = 8000;
        OwnerId = "player-001";
        EncounterMapId = "main";
        UseMockServices = false;
    }
}
