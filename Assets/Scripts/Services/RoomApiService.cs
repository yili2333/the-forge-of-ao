using System;
using System.Net.Http;
using System.Threading.Tasks;
using UnityEngine;

public class RoomApiService
{
    private static readonly HttpClient Http = new HttpClient();

    public async Task<bool> CheckServerAsync()
    {
        BackendProbeResult probe = await ProbeBackendAsync();
        return probe.reachable;
    }

    public async Task<BackendProbeResult> ProbeBackendAsync()
    {
        try
        {
            using (HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Get, BackendConfig.HealthUrl))
            {
                HttpResponseMessage response = await Http.SendAsync(request);
                int status = (int)response.StatusCode;
                string body = await response.Content.ReadAsStringAsync();
                string summary = status >= 200 && status < 300
                    ? "Backend reachable at " + BackendConfig.BaseHttpUrl + " (HTTP " + status + ")."
                    : "Backend reachable at " + BackendConfig.BaseHttpUrl + " but root returned HTTP " + status + ".";

                if (!string.IsNullOrWhiteSpace(body))
                {
                    summary += " Body: " + body.Trim();
                }

                return new BackendProbeResult
                {
                    reachable = true,
                    summary = summary,
                    httpStatus = status
                };
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[RoomApiService] Server check failed: " + ex.Message);
            return new BackendProbeResult
            {
                reachable = false,
                summary = "Server check failed: " + ex.Message,
                httpStatus = 0
            };
        }
    }

    public async Task<bool> JoinRoomAsync(string roomId, string role)
    {
        bool serverOnline = await CheckServerAsync();

        if (serverOnline)
        {
            Debug.Log("[RoomApiService] Backend reachable. Joining room " + roomId + " as " + role + ".");
            return true;
        }

        Debug.Log("[RoomApiService] Falling back to local room flow.");
        return BackendConfig.UseMockServices;
    }
}
