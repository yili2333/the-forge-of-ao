using System;
using UnityEngine;

[Serializable]
public class RoomMessage
{
    public string type = "chat";
    public string sender = "";
    public string content = "";
    public string dataJson = "";
    public string ts = "";
    public string msg_id = "";
}

[Serializable]
public class SceneGenerationResult
{
    public bool success;
    public string sceneName;
    public string description;
    public Color previewColor;
    public string ambientPreset;
    public string source;
    public string imageUrl;
    public byte[] imageBytes;
}

[Serializable]
public class CharacterAuditResult
{
    public bool success;
    public string status;
    public string summary;
    public string issues;
    public string contextText;
    public string derivedSummary;
}

[Serializable]
public class CharacterUploadResult
{
    public bool success;
    public string status;
    public string summary;
    public string characterId;
}

[Serializable]
public class BackendProbeResult
{
    public bool reachable;
    public string summary;
    public int httpStatus;
}

[Serializable]
public class CampaignOverviewLite
{
    public bool success;
    public string campaignName;
    public string activeEncounterMapId;
    public int characterCount;
    public int encounterMapCount;
    public int monsterInPlayCount;
    public string summary;
}

[Serializable]
public class SessionSnapshotLite
{
    public bool success;
    public string sessionId;
    public string activeEncounterMapId;
    public int roundNumber;
    public int currentTurn;
    public string summary;
}


[Serializable]
public class WorldMapLite
{
    public bool success;
    public string id;
    public string name;
    public string description;
    public string imageUrl;
    public int poiCount;
    public string summary;
}

[Serializable]
public class RegionMapSummaryLite
{
    public string id;
    public string name;
    public string description;
    public string regionType;
    public string imageUrl;
    public int poiCount;
}

[Serializable]
public class RegionMapLite
{
    public bool success;
    public string id;
    public string name;
    public string description;
    public string regionType;
    public string imageUrl;
    public int poiCount;
    public string summary;
}

[Serializable]
public class MonsterSummaryLite
{
    public string id;
    public string name;
    public string subtitle;
    public string crText;
    public string summary;
}

[Serializable]
public class SessionLogEntryLite
{
    public string opType;
    public string actorId;
    public int roundNumber;
    public string timestamp;
    public string summary;
}

[Serializable]
public class CharacterActionResultLite
{
    public bool success;
    public string summary;
    public string detail;
    public string rawJson;
}

[Serializable]
public class PreparedSpellInfoLite
{
    public string name;
    public string sourceClass;
    public int level;
    public bool prepared;
    public bool alwaysPrepared;
}

[Serializable]
public class PreparedSpellListLite
{
    public bool success;
    public string summary;
    public PreparedSpellInfoLite[] spells;
}
[Serializable]
public class EncounterMapSummaryLite
{
    public string id;
    public string name;
    public int gridCols;
    public int gridRows;
    public int creatureCount;
    public bool isActive;
    public string imageUrl;
    public string summary;
}

[Serializable]
public class BrowseEntryLite
{
    public string name;
    public string path;
    public bool isDir;
    public int htmCount;
    public int pdfCount;
}

[Serializable]
public class BrowseResultLite
{
    public bool success;
    public string currentPath;
    public string parentPath;
    public int totalHtm;
    public int totalPdf;
    public string summary;
    public BrowseEntryLite[] entries;
}

[Serializable]
public class ScanBookResultLite
{
    public string subdir;
    public string fullPath;
    public string detectedSource;
    public string detectedName;
    public int filesFound;
    public int chunksCreated;
    public int conflictsFound;
    public bool skipped;
    public string skipReason;
    public string[] errors;
}

[Serializable]
public class ScanImportResultLite
{
    public bool success;
    public string rootPath;
    public int booksFound;
    public int booksImported;
    public int totalChunks;
    public int totalConflicts;
    public bool dryRun;
    public string message;
    public ScanBookResultLite[] results;
}
