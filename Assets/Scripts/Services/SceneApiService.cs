using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

public class SceneApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<SceneGenerationResult> GenerateSceneAsync(string prompt)
    {
        string lowerPrompt = (prompt ?? string.Empty).ToLowerInvariant();
        SceneGenerationResult result = new SceneGenerationResult
        {
            success = true,
            sceneName = "Custom Scene",
            description = string.IsNullOrWhiteSpace(prompt) ? "No description provided." : prompt.Trim(),
            previewColor = new Color(0.45f, 0.50f, 0.58f, 1f),
            ambientPreset = "neutral",
            source = BackendConfig.UseMockServices ? "Mock Scene Generator" : "Scene API"
        };

        ApplyPromptPreset(lowerPrompt, result);

        if (BackendConfig.UseMockServices)
        {
            await Task.Delay(250);
            return result;
        }

        try
        {
            string targetUrl = BackendConfig.GetSceneGenerateUrl(RoomSessionContext.roomId, BackendConfig.EncounterMapId);
            string payload = "{\"prompt\":\"" + CharacterSheetPayloadBuilder.Escape(prompt ?? string.Empty) + "\",\"cell_px\":48}";

            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, targetUrl))
            {
                request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                request.Headers.TryAddWithoutValidation("X-Owner-Id", BackendConfig.OwnerId);
                request.Headers.TryAddWithoutValidation("X-Role", "dm");

                HttpResponseMessage response = await Http.SendAsync(request);
                string body = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    result.success = false;
                    result.description = JsonRegexUtility.ExtractString(body, "detail");
                    if (string.IsNullOrWhiteSpace(result.description))
                    {
                        result.description = "Scene API failed with HTTP " + (int)response.StatusCode + ".";
                    }
                    return result;
                }

                string sceneName = JsonRegexUtility.ExtractString(body, "name");
                string imagePrompt = JsonRegexUtility.ExtractString(body, "image_prompt");
                string imageUrl = JsonRegexUtility.ExtractString(body, "image_url");

                if (!string.IsNullOrWhiteSpace(sceneName)) result.sceneName = sceneName;
                if (!string.IsNullOrWhiteSpace(imagePrompt)) result.description = imagePrompt;
                result.imageUrl = BackendConfig.ResolveAssetUrl(imageUrl);

                if (!string.IsNullOrWhiteSpace(result.imageUrl))
                {
                    try
                    {
                        result.imageBytes = await Http.GetByteArrayAsync(result.imageUrl);
                    }
                    catch (Exception ex)
                    {
                        Debug.Log("[SceneApiService] Image download failed: " + ex.Message);
                    }
                }

                result.source = "Scene API";
                return result;
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[SceneApiService] Falling back to mock scene: " + ex.Message);
            result.source = "Mock Scene Generator";
            result.description = result.description + "\n(Live scene request failed: " + ex.Message + ")";
            return result;
        }
    }

    private void ApplyPromptPreset(string lowerPrompt, SceneGenerationResult result)
    {
        if (lowerPrompt.Contains("alchemy") || lowerPrompt.Contains("lab") || lowerPrompt.Contains("potion"))
        {
            result.sceneName = "Alchemy Lab";
            result.previewColor = new Color(0.34f, 0.54f, 0.42f, 1f);
            result.ambientPreset = "alchemy";
        }
        else if (lowerPrompt.Contains("cathedral") || lowerPrompt.Contains("ruins") || lowerPrompt.Contains("rain"))
        {
            result.sceneName = "Cathedral Ruins";
            result.previewColor = new Color(0.42f, 0.46f, 0.55f, 1f);
            result.ambientPreset = "rain";
        }
        else if (lowerPrompt.Contains("forest") || lowerPrompt.Contains("tree") || lowerPrompt.Contains("woods"))
        {
            result.sceneName = "Forest Path";
            result.previewColor = new Color(0.30f, 0.45f, 0.28f, 1f);
            result.ambientPreset = "forest";
        }
        else if (lowerPrompt.Contains("cave") || lowerPrompt.Contains("dark") || lowerPrompt.Contains("dungeon"))
        {
            result.sceneName = "Dark Cave";
            result.previewColor = new Color(0.22f, 0.24f, 0.30f, 1f);
            result.ambientPreset = "cave";
        }
        else if (lowerPrompt.Contains("town") || lowerPrompt.Contains("market") || lowerPrompt.Contains("street"))
        {
            result.sceneName = "Town Street";
            result.previewColor = new Color(0.58f, 0.50f, 0.36f, 1f);
            result.ambientPreset = "town";
        }
    }
}
