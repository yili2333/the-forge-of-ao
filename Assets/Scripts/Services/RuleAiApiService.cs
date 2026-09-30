using System;
using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

public class RuleAiApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<string> AskRuleAsync(string question, string characterId = null)
    {
        if (string.IsNullOrWhiteSpace(question))
        {
            return "Please enter a rules question.";
        }

        if (!BackendConfig.UseMockServices)
        {
            try
            {
                string payload = BuildRulePayload(question);
                string targetUrl = !string.IsNullOrWhiteSpace(characterId) && characterId.StartsWith("char-")
                    ? BackendConfig.GetCharacterAskUrl(characterId)
                    : BackendConfig.QueryUrl;

                using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, targetUrl))
                {
                    request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                    request.Headers.TryAddWithoutValidation("X-Owner-Id", BackendConfig.OwnerId);

                    HttpResponseMessage response = await Http.SendAsync(request);
                    string body = await response.Content.ReadAsStringAsync();

                    if (response.IsSuccessStatusCode && !string.IsNullOrWhiteSpace(body))
                    {
                        string answer = JsonRegexUtility.ExtractString(body, "answer");
                        if (string.IsNullOrWhiteSpace(answer))
                        {
                            answer = JsonRegexUtility.ExtractString(body, "detail");
                        }

                        float? confidence = JsonRegexUtility.ExtractFloat(body, "confidence");
                        int? chunks = JsonRegexUtility.ExtractInt(body, "chunks_used");
                        string versionNote = JsonRegexUtility.ExtractString(body, "version_note");

                        StringBuilder formatted = new StringBuilder();
                        formatted.Append(string.IsNullOrWhiteSpace(answer) ? body.Trim() : answer.Trim());

                        if (confidence.HasValue || chunks.HasValue || !string.IsNullOrWhiteSpace(versionNote))
                        {
                            formatted.Append("\n\n[");
                            bool needSep = false;
                            if (confidence.HasValue)
                            {
                                formatted.Append("confidence ")
                                    .Append(confidence.Value.ToString("0.00", CultureInfo.InvariantCulture));
                                needSep = true;
                            }
                            if (chunks.HasValue)
                            {
                                if (needSep) formatted.Append(" | ");
                                formatted.Append("chunks ").Append(chunks.Value);
                                needSep = true;
                            }
                            if (!string.IsNullOrWhiteSpace(versionNote))
                            {
                                if (needSep) formatted.Append(" | ");
                                formatted.Append(versionNote.Trim());
                            }
                            formatted.Append(']');
                        }

                        return formatted.ToString();
                    }

                    string detail = JsonRegexUtility.ExtractString(body, "detail");
                    if (!string.IsNullOrWhiteSpace(detail))
                    {
                        return "Rule API failed: " + detail;
                    }

                    return "Rule API failed with HTTP " + (int)response.StatusCode + ".";
                }
            }
            catch (Exception ex)
            {
                Debug.Log("[RuleAiApiService] Falling back to mock answer: " + ex.Message);
            }
        }

        await Task.Delay(250);
        return BuildMockAnswer(question);
    }

    private string BuildRulePayload(string question)
    {
        string safeQuestion = CharacterSheetPayloadBuilder.Escape(question.Trim());
        string safeCampaign = CharacterSheetPayloadBuilder.Escape(RoomSessionContext.roomId);
        return "{\"question\":\"" + safeQuestion + "\",\"campaign_id\":\"" + safeCampaign + "\",\"conversation_history\":[]}";
    }

    private string BuildMockAnswer(string question)
    {
        string lower = question.ToLowerInvariant();

        if (lower.Contains("偷袭") || lower.Contains("sneak attack"))
        {
            return "Mock Rule AI: Sneak Attack usually needs a finesse or ranged weapon and either advantage or an ally threatening the target.";
        }

        if (lower.Contains("initiative"))
        {
            return "Mock Rule AI: Initiative is usually a Dexterity check. Higher result acts earlier in combat order.";
        }

        if (lower.Contains("advantage"))
        {
            return "Mock Rule AI: With advantage, roll two d20s and use the higher result. With disadvantage, use the lower result.";
        }

        if (lower.Contains("spell slot"))
        {
            return "Mock Rule AI: Spell slots are consumed when a spell is cast unless the feature says otherwise. They are usually restored after a long rest, depending on the ruleset.";
        }

        return "Mock Rule AI: Backend answer unavailable, but the UI successfully captured your question: \"" + question.Trim() + "\".";
    }
}
