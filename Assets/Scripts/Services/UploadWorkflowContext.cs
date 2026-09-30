public static class UploadWorkflowContext
{
    public static string UploadedCharacterId;
    public static CharacterAuditResult LastAuditResult;
    public static CharacterUploadResult LastUploadResult;
    public static string LastDecision;

    public static void SetUpload(string characterId, CharacterAuditResult auditResult, CharacterUploadResult uploadResult)
    {
        UploadedCharacterId = characterId;
        LastAuditResult = auditResult;
        LastUploadResult = uploadResult;
        LastDecision = null;
    }

    public static void SetDecision(string decision)
    {
        LastDecision = decision;
        if (LastAuditResult != null)
        {
            LastAuditResult.status = decision;
            LastAuditResult.summary = "Latest DM decision: " + decision + ".";
            LastAuditResult.issues = decision == "Request Changes"
                ? "Player should update the sheet and upload again."
                : "Decision stored locally until backend workflow is connected.";
        }
    }

    public static void Clear()
    {
        UploadedCharacterId = null;
        LastAuditResult = null;
        LastUploadResult = null;
        LastDecision = null;
    }
}
