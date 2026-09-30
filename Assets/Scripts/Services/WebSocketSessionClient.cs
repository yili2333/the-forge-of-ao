using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class WebSocketSessionClient : IDisposable
{
    private ClientWebSocket socket;
    private CancellationTokenSource cancellationTokenSource;
    private readonly ConcurrentQueue<RoomMessage> incomingMessages = new ConcurrentQueue<RoomMessage>();

    public bool IsConnected
    {
        get { return socket != null && socket.State == WebSocketState.Open; }
    }

    public async Task<bool> ConnectAsync(string campaignId, string ownerId, string role, string characterId)
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        Debug.LogWarning("[WebSocketSessionClient] ClientWebSocket is not enabled in WebGL for this prototype.");
        return false;
#else
        try
        {
            await DisconnectAsync();
            socket = new ClientWebSocket();
            cancellationTokenSource = new CancellationTokenSource();

            Uri uri = new Uri(BackendConfig.GetSessionWebSocketUrl(campaignId, ownerId, role, characterId));
            await socket.ConnectAsync(uri, cancellationTokenSource.Token);
            _ = ReceiveLoopAsync(cancellationTokenSource.Token);
            return true;
        }
        catch (Exception ex)
        {
            Debug.Log("[WebSocketSessionClient] Connect failed: " + ex.Message);
            return false;
        }
#endif
    }

    public async Task SendMessageAsync(RoomMessage message)
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        await Task.CompletedTask;
#else
        if (!IsConnected || message == null)
        {
            return;
        }

        try
        {
            string type = string.IsNullOrWhiteSpace(message.type) ? "chat" : message.type.Trim();
            string sender = string.IsNullOrWhiteSpace(message.sender) ? BackendConfig.OwnerId : message.sender.Trim();
            string ts = string.IsNullOrWhiteSpace(message.ts) ? DateTime.UtcNow.ToString("o") : message.ts;
            string msgId = string.IsNullOrWhiteSpace(message.msg_id) ? Guid.NewGuid().ToString("N").Substring(0, 8) : message.msg_id;
            string dataJson = !string.IsNullOrWhiteSpace(message.dataJson)
                ? message.dataJson
                : "{\"text\":\"" + CharacterSheetPayloadBuilder.Escape(message.content ?? string.Empty) + "\"}";

            string json = "{\"type\":\"" + CharacterSheetPayloadBuilder.Escape(type) +
                          "\",\"sender\":\"" + CharacterSheetPayloadBuilder.Escape(sender) +
                          "\",\"data\":" + dataJson +
                          ",\"ts\":\"" + CharacterSheetPayloadBuilder.Escape(ts) +
                          "\",\"msg_id\":\"" + CharacterSheetPayloadBuilder.Escape(msgId) + "\"}";

            byte[] bytes = Encoding.UTF8.GetBytes(json);
            ArraySegment<byte> segment = new ArraySegment<byte>(bytes);
            await socket.SendAsync(segment, WebSocketMessageType.Text, true, cancellationTokenSource.Token);
        }
        catch (Exception ex)
        {
            Debug.Log("[WebSocketSessionClient] Send failed: " + ex.Message);
        }
#endif
    }

    public bool TryDequeueMessage(out RoomMessage message)
    {
        return incomingMessages.TryDequeue(out message);
    }

    public async Task DisconnectAsync()
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        await Task.CompletedTask;
#else
        try
        {
            if (cancellationTokenSource != null && !cancellationTokenSource.IsCancellationRequested)
            {
                cancellationTokenSource.Cancel();
            }

            if (socket != null)
            {
                if (socket.State == WebSocketState.Open || socket.State == WebSocketState.CloseReceived)
                {
                    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None);
                }

                socket.Dispose();
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[WebSocketSessionClient] Disconnect warning: " + ex.Message);
        }
        finally
        {
            socket = null;
            if (cancellationTokenSource != null)
            {
                cancellationTokenSource.Dispose();
                cancellationTokenSource = null;
            }
        }
#endif
    }

    private async Task ReceiveLoopAsync(CancellationToken token)
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        await Task.CompletedTask;
#else
        byte[] buffer = new byte[4096];

        while (!token.IsCancellationRequested && socket != null && socket.State == WebSocketState.Open)
        {
            using (MemoryStream stream = new MemoryStream())
            {
                WebSocketReceiveResult result;

                do
                {
                    result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), token);

                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None);
                        return;
                    }

                    stream.Write(buffer, 0, result.Count);
                }
                while (!result.EndOfMessage);

                string text = Encoding.UTF8.GetString(stream.ToArray());
                RoomMessage message = SafeParseMessage(text);
                incomingMessages.Enqueue(message);
            }
        }
#endif
    }

    private RoomMessage SafeParseMessage(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return new RoomMessage { type = "system", sender = "Server", content = "Received an empty websocket message." };
        }

        string type = JsonRegexUtility.ExtractString(json, "type");
        string sender = JsonRegexUtility.ExtractString(json, "sender");
        string content = JsonRegexUtility.ExtractString(json, "text");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "message");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "content");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "detail");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "breakdown");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "response");
        if (string.IsNullOrWhiteSpace(content)) content = JsonRegexUtility.ExtractString(json, "hp_status");
        if (string.IsNullOrWhiteSpace(content)) content = json;

        return new RoomMessage
        {
            type = string.IsNullOrWhiteSpace(type) ? "chat" : type,
            sender = string.IsNullOrWhiteSpace(sender) ? "Server" : sender,
            content = content,
            ts = JsonRegexUtility.ExtractString(json, "ts"),
            msg_id = JsonRegexUtility.ExtractString(json, "msg_id"),
            dataJson = json
        };
    }

    public void Dispose()
    {
        _ = DisconnectAsync();
    }
}
