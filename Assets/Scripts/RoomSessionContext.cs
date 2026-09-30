using System;

public static class RoomSessionContext
{
    public static string roomId = "ROOM-001";
    public static string role = "dm";
    public static string ownerId = "player-001";
    public static string clientId = "player-001";
    public static string currentCharacterId = string.Empty;

    public static bool IsDM
    {
        get { return RoleParam == "dm"; }
    }

    public static string RoleParam
    {
        get
        {
            string normalized = string.IsNullOrWhiteSpace(role) ? "player" : role.Trim().ToLowerInvariant();
            return normalized.StartsWith("d") ? "dm" : "player";
        }
    }

    public static void SetSession(string newRoomId, string newRole)
    {
        roomId = string.IsNullOrWhiteSpace(newRoomId) ? "ROOM-001" : newRoomId.Trim();
        role = string.IsNullOrWhiteSpace(newRole) ? "Player" : newRole.Trim();
        ownerId = string.IsNullOrWhiteSpace(BackendConfig.OwnerId) ? (RoleParam + "_local") : BackendConfig.OwnerId.Trim();
        clientId = ownerId;
    }

    public static void SetCharacter(string characterId)
    {
        currentCharacterId = string.IsNullOrWhiteSpace(characterId) ? string.Empty : characterId.Trim();
    }
}
