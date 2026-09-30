using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

public class CharacterApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<List<CharacterData>> LoadCampaignCharactersAsync(string campaignId)
    {
        List<CharacterData> characters = new List<CharacterData>();
        if (BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(campaignId))
        {
            return characters;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetListCharactersCampaignUrl(campaignId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[CharacterApiService] Campaign list failed: HTTP " + (int)response.StatusCode + " body=" + body);
                    return characters;
                }

                List<string> objects = JsonRegexUtility.SplitTopLevelObjects(body);
                for (int i = 0; i < objects.Count; i++)
                {
                    CharacterData item = ParseCharacterListItem(objects[i]);
                    if (item != null)
                    {
                        characters.Add(item);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CharacterApiService] LoadCampaignCharacters failed: " + ex.Message);
        }

        return characters;
    }

    public async Task<CharacterData> RefreshCharacterDetailAsync(CharacterData character)
    {
        if (character == null || BackendConfig.UseMockServices || string.IsNullOrWhiteSpace(character.id))
        {
            return character;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetCharacterSummaryUrl(character.id)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    Debug.Log("[CharacterApiService] Summary load failed for " + character.id + ": HTTP " + (int)response.StatusCode + " body=" + body);
                    return character;
                }

                ApplySummaryToCharacter(character, body);
                return character;
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[CharacterApiService] RefreshCharacterDetail failed: " + ex.Message);
            return character;
        }
    }

    public async Task<CharacterAuditResult> AuditCharacterAsync(CharacterData character)
    {
        if (character == null)
        {
            return new CharacterAuditResult
            {
                success = false,
                status = "Unavailable",
                summary = "No uploaded character found for audit.",
                issues = "Upload a character from the vault first."
            };
        }

        if (!BackendConfig.UseMockServices && !string.IsNullOrWhiteSpace(character.id))
        {
            try
            {
                character = await RefreshCharacterDetailAsync(character);
                List<string> issues = new List<string>();
                if (character.armorClass > 0) issues.Add("AC " + character.armorClass);
                if (character.passivePerception > 0) issues.Add("Passive Perception " + character.passivePerception);
                if (!string.IsNullOrWhiteSpace(character.conditions)) issues.Add("Conditions: " + character.conditions);
                if (!string.IsNullOrWhiteSpace(character.spellStatsByClass)) issues.Add(character.spellStatsByClass);

                return new CharacterAuditResult
                {
                    success = true,
                    status = character.dmApproved ? "Approved" : "Loaded",
                    summary = string.IsNullOrWhiteSpace(character.contextText) ? "Character summary loaded from backend." : character.contextText,
                    contextText = character.contextText,
                    derivedSummary = string.IsNullOrWhiteSpace(character.derivedSummary) ? string.Join(" | ", issues.ToArray()) : character.derivedSummary,
                    issues = issues.Count > 0 ? string.Join("\n", issues.ToArray()) : "No derived warnings from backend summary."
                };
            }
            catch (Exception ex)
            {
                Debug.Log("[CharacterApiService] Audit summary failed: " + ex.Message);
            }
        }

        await Task.Delay(150);
        return BuildLocalAudit(character);
    }

    public async Task<CharacterUploadResult> UploadCharacterAsync(CharacterData character)
    {
        if (character == null)
        {
            CharacterUploadResult missing = new CharacterUploadResult { success = false, status = "Upload Failed", summary = "No character selected for upload." };
            UploadWorkflowContext.SetUpload(null, null, missing);
            return missing;
        }

        if (BackendConfig.UseMockServices)
        {
            CharacterAuditResult mockAudit = await AuditCharacterAsync(character);
            CharacterUploadResult mockResult = new CharacterUploadResult
            {
                success = true,
                status = mockAudit != null ? mockAudit.status : "Unavailable",
                summary = "Uploaded \"" + character.characterName + "\" for room " + RoomSessionContext.roomId + ".",
                characterId = character.id
            };
            CharacterUploadContext.uploadedCharacterId = character.id;
            RoomSessionContext.SetCharacter(character.id);
            UploadWorkflowContext.SetUpload(character.id, mockAudit, mockResult);
            return mockResult;
        }

        try
        {
            bool usePut = await CharacterExistsAsync(character.id);
            HttpMethod method = usePut ? HttpMethod.Put : HttpMethod.Post;
            string url = usePut ? BackendConfig.GetCharacterUrl(character.id) : BackendConfig.CharacterCreateUrl;
            string payload = CharacterSheetPayloadBuilder.Build(character, RoomSessionContext.roomId, BackendConfig.OwnerId);

            HttpResponseMessage response = await SendJsonAsync(method, url, payload);
            string body = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode && response.StatusCode == HttpStatusCode.Conflict && !string.IsNullOrWhiteSpace(character.id))
            {
                response = await SendJsonAsync(HttpMethod.Put, BackendConfig.GetCharacterUrl(character.id), payload);
                body = await response.Content.ReadAsStringAsync();
            }

            if (response.IsSuccessStatusCode)
            {
                string remoteId = JsonRegexUtility.ExtractString(body, "id");
                if (!string.IsNullOrWhiteSpace(remoteId))
                {
                    character.id = remoteId;
                }

                await RefreshCharacterDetailAsync(character);
                CharacterAuditResult audit = await AuditCharacterAsync(character);
                CharacterUploadResult success = new CharacterUploadResult
                {
                    success = true,
                    status = usePut ? "Updated" : "Uploaded",
                    summary = (usePut ? "Updated " : "Uploaded ") + "\"" + character.characterName + "\" to campaign " + RoomSessionContext.roomId + ".",
                    characterId = character.id
                };

                CharacterUploadContext.uploadedCharacterId = character.id;
                RoomSessionContext.SetCharacter(character.id);
                UploadWorkflowContext.SetUpload(character.id, audit, success);
                return success;
            }

            string detail = JsonRegexUtility.ExtractString(body, "detail");
            CharacterUploadResult failed = new CharacterUploadResult
            {
                success = false,
                status = "Upload Failed",
                summary = string.IsNullOrWhiteSpace(detail) ? "HTTP " + (int)response.StatusCode : detail,
                characterId = character.id
            };
            UploadWorkflowContext.SetUpload(character.id, null, failed);
            return failed;
        }
        catch (Exception ex)
        {
            CharacterUploadResult failed = new CharacterUploadResult
            {
                success = false,
                status = "Upload Failed",
                summary = ex.Message,
                characterId = character.id
            };
            UploadWorkflowContext.SetUpload(character.id, null, failed);
            return failed;
        }
    }

    public async Task<CharacterAuditResult> SubmitDecisionAsync(CharacterData character, string decision)
    {
        if (character == null)
        {
            return new CharacterAuditResult
            {
                success = false,
                status = "Unavailable",
                summary = "No character selected.",
                issues = "Pick a character before sending a DM decision."
            };
        }

        if (!BackendConfig.UseMockServices && !string.IsNullOrWhiteSpace(character.id))
        {
            try
            {
                bool approved = decision.Equals("Approved", StringComparison.OrdinalIgnoreCase);
                string note = approved ? "Character approved by DM." : decision.Equals("Rejected", StringComparison.OrdinalIgnoreCase) ? "Character rejected by DM." : "Please revise the character sheet and upload again.";
                string payload = "{\"approved\":" + (approved ? "true" : "false") + ",\"note\":\"" + CharacterSheetPayloadBuilder.Escape(note) + "\"}";

                using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, BackendConfig.GetCharacterApproveUrl(character.id)))
                {
                    AddCommonHeaders(request, true);
                    request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                    HttpResponseMessage response = await Http.SendAsync(request);
                    string body = await response.Content.ReadAsStringAsync();

                    if (response.IsSuccessStatusCode)
                    {
                        character.dmApproved = approved;
                        character.approvalNote = note;
                        CharacterAuditResult result = new CharacterAuditResult
                        {
                            success = true,
                            status = decision,
                            summary = "DM decision submitted to backend.",
                            issues = string.IsNullOrWhiteSpace(note) ? JsonRegexUtility.ExtractString(body, "detail") : note,
                            contextText = character.contextText,
                            derivedSummary = character.derivedSummary
                        };
                        UploadWorkflowContext.LastAuditResult = result;
                        UploadWorkflowContext.SetDecision(decision);
                        return result;
                    }

                    string detail = JsonRegexUtility.ExtractString(body, "detail");
                    return new CharacterAuditResult
                    {
                        success = false,
                        status = "Failed",
                        summary = string.IsNullOrWhiteSpace(detail) ? "Approve API failed with HTTP " + (int)response.StatusCode + "." : detail,
                        issues = "Check DM role header and backend logs."
                    };
                }
            }
            catch (Exception ex)
            {
                return new CharacterAuditResult
                {
                    success = false,
                    status = "Failed",
                    summary = ex.Message,
                    issues = "Decision was not sent to backend."
                };
            }
        }

        await Task.Delay(100);
        CharacterAuditResult mock = new CharacterAuditResult
        {
            success = true,
            status = decision,
            summary = "DM marked \"" + character.characterName + "\" as \"" + decision + "\".",
            issues = decision == "Request Changes" ? "Player should update the sheet and upload again." : "Decision stored locally until backend workflow is connected.",
            contextText = character.contextText,
            derivedSummary = character.derivedSummary
        };
        UploadWorkflowContext.LastAuditResult = mock;
        UploadWorkflowContext.SetDecision(decision);
        return mock;
    }

    private async Task<bool> CharacterExistsAsync(string characterId)
    {
        if (string.IsNullOrWhiteSpace(characterId))
        {
            return false;
        }

        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.GetCharacterSummaryUrl(characterId)))
            {
                AddCommonHeaders(request, false);
                HttpResponseMessage response = await Http.SendAsync(request);
                return response.IsSuccessStatusCode;
            }
        }
        catch
        {
            return false;
        }
    }

    private async Task<HttpResponseMessage> SendJsonAsync(HttpMethod method, string url, string payload)
    {
        HttpRequestMessage request = new HttpRequestMessage(method, url);
        AddCommonHeaders(request, false);
        request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
        return await Http.SendAsync(request);
    }

    private CharacterData ParseCharacterListItem(string json)
    {
        string id = JsonRegexUtility.ExtractString(json, "id");
        if (string.IsNullOrWhiteSpace(id)) return null;

        CharacterData character = new CharacterData();
        character.id = id;
        character.characterName = JsonRegexUtility.ExtractString(json, "name");
        character.ownerId = JsonRegexUtility.ExtractString(json, "owner_id");
        character.ownerDisplay = JsonRegexUtility.ExtractString(json, "owner_display");
        character.campaignId = JsonRegexUtility.ExtractString(json, "campaign_id");
        character.characterClass = "Loading...";
        character.level = JsonRegexUtility.ExtractInt(json, "total_level") ?? 1;
        character.dmApproved = JsonRegexUtility.ExtractBool(json, "dm_approved") ?? false;
        character.nonStandard = JsonRegexUtility.ExtractBool(json, "non_standard") ?? false;
        character.updatedAt = JsonRegexUtility.ExtractString(json, "updated_at");
        character.edition = JsonRegexUtility.ExtractString(json, "edition");
        character.hp = 0;
        return character;
    }

    private void ApplySummaryToCharacter(CharacterData character, string body)
    {
        if (character == null || string.IsNullOrWhiteSpace(body)) return;

        string sheetJson = JsonRegexUtility.ExtractObject(body, "sheet");
        string derivedJson = JsonRegexUtility.ExtractObject(body, "derived");

        string name = JsonRegexUtility.ExtractString(sheetJson, "name");
        if (!string.IsNullOrWhiteSpace(name)) character.characterName = name;
        character.ownerId = Prefer(JsonRegexUtility.ExtractString(sheetJson, "owner_id"), character.ownerId);
        character.campaignId = Prefer(JsonRegexUtility.ExtractString(sheetJson, "campaign_id"), character.campaignId);
        character.ownerDisplay = Prefer(JsonRegexUtility.ExtractString(sheetJson, "owner_display"), character.ownerDisplay);
        character.edition = Prefer(JsonRegexUtility.ExtractString(sheetJson, "edition"), character.edition);
        character.dmApproved = JsonRegexUtility.ExtractBool(sheetJson, "dm_approved") ?? character.dmApproved;
        character.nonStandard = JsonRegexUtility.ExtractBool(sheetJson, "non_standard") ?? character.nonStandard;
        character.updatedAt = Prefer(JsonRegexUtility.ExtractString(sheetJson, "updated_at"), character.updatedAt);
        character.alignment = Prefer(JsonRegexUtility.ExtractString(sheetJson, "alignment"), character.alignment);
        character.spellcastingAbility = Prefer(JsonRegexUtility.ExtractString(sheetJson, "spellcasting_ability"), character.spellcastingAbility);

        string speciesJson = JsonRegexUtility.ExtractObject(sheetJson, "species");
        character.species = Prefer(JsonRegexUtility.ExtractString(speciesJson, "name"), character.species);

        string backgroundJson = JsonRegexUtility.ExtractObject(sheetJson, "background");
        character.backgroundName = Prefer(JsonRegexUtility.ExtractString(backgroundJson, "name"), character.backgroundName);

        string classLevelsJson = JsonRegexUtility.ExtractArray(sheetJson, "class_levels");
        List<string> classItems = JsonRegexUtility.SplitTopLevelObjects(classLevelsJson);
        if (classItems.Count > 0)
        {
            string className = JsonRegexUtility.ExtractString(classItems[0], "class_name");
            if (!string.IsNullOrWhiteSpace(className)) character.characterClass = className;
            character.subclass = Prefer(JsonRegexUtility.ExtractString(classItems[0], "subclass"), character.subclass);
        }

        string hpJson = JsonRegexUtility.ExtractObject(sheetJson, "hit_points");
        character.hp = JsonRegexUtility.ExtractInt(hpJson, "current") ?? character.hp;
        character.maxHp = JsonRegexUtility.ExtractInt(hpJson, "maximum") ?? character.EffectiveMaxHp;
        character.mp = character.maxHp;

        string abilityJson = JsonRegexUtility.ExtractObject(sheetJson, "ability_scores");
        character.strength = JsonRegexUtility.ExtractInt(abilityJson, "strength") ?? character.strength;
        character.dexterity = JsonRegexUtility.ExtractInt(abilityJson, "dexterity") ?? character.dexterity;
        character.constitution = JsonRegexUtility.ExtractInt(abilityJson, "constitution") ?? character.constitution;
        character.intelligence = JsonRegexUtility.ExtractInt(abilityJson, "intelligence") ?? character.intelligence;
        character.wisdom = JsonRegexUtility.ExtractInt(abilityJson, "wisdom") ?? character.wisdom;
        character.charisma = JsonRegexUtility.ExtractInt(abilityJson, "charisma") ?? character.charisma;

        string speedJson = JsonRegexUtility.ExtractObject(sheetJson, "speed");
        character.walkSpeed = JsonRegexUtility.ExtractInt(speedJson, "walk") ?? character.walkSpeed;

        List<string> inventoryItems = JsonRegexUtility.SplitTopLevelObjects(JsonRegexUtility.ExtractArray(sheetJson, "inventory"));
        List<string> inventoryNames = new List<string>();
        for (int i = 0; i < inventoryItems.Count; i++)
        {
            string itemName = JsonRegexUtility.ExtractString(inventoryItems[i], "name");
            if (!string.IsNullOrWhiteSpace(itemName)) inventoryNames.Add(itemName);
        }
        if (inventoryNames.Count > 0) character.inventory = string.Join(", ", inventoryNames.ToArray());

        List<string> conditions = JsonRegexUtility.ExtractStringArray(sheetJson, "conditions");
        if (conditions.Count > 0) character.conditions = string.Join(", ", conditions.ToArray());

        List<string> preparedSpells = JsonRegexUtility.ExtractStringArray(sheetJson, "prepared_spells");
        if (preparedSpells.Count > 0) character.preparedSpells = string.Join(", ", preparedSpells.ToArray());

        string currencyJson = JsonRegexUtility.ExtractObject(sheetJson, "currency");
        character.currencySummary = BuildCurrencySummary(currencyJson);

        character.level = JsonRegexUtility.ExtractInt(derivedJson, "total_level") ?? character.level;
        character.armorClass = JsonRegexUtility.ExtractInt(derivedJson, "ac") ?? character.armorClass;
        character.passivePerception = JsonRegexUtility.ExtractInt(derivedJson, "passive_perception") ?? character.passivePerception;
        character.initiativeBonus = JsonRegexUtility.ExtractInt(derivedJson, "initiative") ?? character.initiativeBonus;
        character.speedEffective = JsonRegexUtility.ExtractInt(derivedJson, "speed_effective") ?? character.speedEffective;
        character.contextText = JsonRegexUtility.ExtractString(body, "context_text");
        character.spellStatsByClass = BuildSpellStatsSummary(JsonRegexUtility.ExtractObject(derivedJson, "spell_stats_by_class"));
        character.derivedSummary = BuildDerivedSummary(character);
    }

    private string BuildSpellStatsSummary(string spellStatsObject)
    {
        if (string.IsNullOrWhiteSpace(spellStatsObject)) return string.Empty;

        List<KeyValuePair<string, string>> entries = JsonRegexUtility.ExtractTopLevelObjectEntries(spellStatsObject);
        List<string> parts = new List<string>();
        for (int i = 0; i < entries.Count; i++)
        {
            string className = entries[i].Key;
            string statsJson = entries[i].Value;
            int dc = JsonRegexUtility.ExtractInt(statsJson, "dc") ?? 0;
            int attackBonus = JsonRegexUtility.ExtractInt(statsJson, "attack_bonus") ?? 0;
            string ability = JsonRegexUtility.ExtractString(statsJson, "ability");
            List<string> piece = new List<string>();
            if (dc > 0) piece.Add("DC " + dc);
            if (attackBonus != 0) piece.Add("Atk " + (attackBonus > 0 ? "+" : string.Empty) + attackBonus);
            if (!string.IsNullOrWhiteSpace(ability)) piece.Add(ability);
            if (piece.Count > 0) parts.Add(className + " (" + string.Join(", ", piece.ToArray()) + ")");
        }
        return string.Join("; ", parts.ToArray());
    }

    private string BuildCurrencySummary(string currencyJson)
    {
        if (string.IsNullOrWhiteSpace(currencyJson)) return string.Empty;

        List<string> parts = new List<string>();
        AddCurrencyPart(parts, JsonRegexUtility.ExtractFloat(currencyJson, "gold"), "gp");
        AddCurrencyPart(parts, JsonRegexUtility.ExtractFloat(currencyJson, "silver"), "sp");
        AddCurrencyPart(parts, JsonRegexUtility.ExtractFloat(currencyJson, "copper"), "cp");
        AddCurrencyPart(parts, JsonRegexUtility.ExtractFloat(currencyJson, "platinum"), "pp");
        AddCurrencyPart(parts, JsonRegexUtility.ExtractFloat(currencyJson, "electrum"), "ep");
        return string.Join(", ", parts.ToArray());
    }

    private void AddCurrencyPart(List<string> parts, float? value, string suffix)
    {
        if (!value.HasValue || Math.Abs(value.Value) < 0.001f) return;
        parts.Add(value.Value.ToString("0.##") + suffix);
    }

    private string BuildDerivedSummary(CharacterData character)
    {
        List<string> parts = new List<string>();
        if (character.armorClass > 0) parts.Add("AC " + character.armorClass);
        parts.Add("Init " + (character.initiativeBonus > 0 ? "+" : string.Empty) + character.initiativeBonus);
        if (character.passivePerception > 0) parts.Add("Passive Perception " + character.passivePerception);
        if (character.speedEffective > 0) parts.Add("Speed " + character.speedEffective + " ft");
        if (!string.IsNullOrWhiteSpace(character.conditions)) parts.Add("Conditions " + character.conditions);
        if (!string.IsNullOrWhiteSpace(character.spellStatsByClass)) parts.Add(character.spellStatsByClass);
        return string.Join(" | ", parts.ToArray());
    }

    private void AddCommonHeaders(HttpRequestMessage request, bool dm)
    {
        request.Headers.TryAddWithoutValidation("X-Owner-Id", BackendConfig.OwnerId);
        if (dm)
        {
            request.Headers.TryAddWithoutValidation("X-Role", "dm");
        }
    }

    private CharacterAuditResult BuildLocalAudit(CharacterData character)
    {
        CharacterAuditResult result = new CharacterAuditResult
        {
            success = true,
            status = "Approved",
            summary = "Character passed the local mock audit.",
            issues = "No critical issues found.",
            contextText = character != null ? character.contextText : string.Empty,
            derivedSummary = character != null ? character.derivedSummary : string.Empty
        };

        List<string> issues = new List<string>();
        if (character == null || string.IsNullOrWhiteSpace(character.characterName)) issues.Add("Missing character name.");
        if (character == null || string.IsNullOrWhiteSpace(character.characterClass)) issues.Add("Missing class information.");
        if (character != null && (character.level < 1 || character.level > 20)) issues.Add("Level should usually stay within 1-20.");
        if (character != null && (character.strength > 18 || character.dexterity > 18 || character.intelligence > 18 || character.constitution > 18)) issues.Add("One or more ability scores are unusually high for a normal starting character.");
        if (character != null && character.hp <= 0) issues.Add("HP must be greater than 0.");
        if (character != null && character.EffectiveMaxHp < character.hp) issues.Add("Current HP is above maximum HP.");

        if (issues.Count > 0)
        {
            result.status = "Review Required";
            result.summary = "The uploaded character needs DM review before approval.";
            result.issues = string.Join("\n", issues.ToArray());
        }
        else if (character != null && character.level >= 8)
        {
            result.status = "DM Review";
            result.summary = "Higher-level characters should be checked against campaign balance.";
            result.issues = "No blocking issue found, but DM confirmation is recommended.";
        }

        return result;
    }

    private string Prefer(string incoming, string fallback)
    {
        return string.IsNullOrWhiteSpace(incoming) ? fallback : incoming;
    }
}
