# sync_engine.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging

# 配置日志记录，显得更专业
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SyncEngine")

router = APIRouter()

class ConnectionManager:
    """管理所有连接到后端的 Unity 客户端 (WebSocket)"""
    def __init__(self):
        # 存储当前活跃的连接
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受新的客户端连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """处理客户端断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """将消息广播给房间内的所有玩家"""
        message_str = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

manager = ConnectionManager()

@router.websocket("/ws/session/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket 通信端点，Unity 客户端将连接到此地址"""
    await manager.connect(websocket)
    
    # 广播系统消息：某玩家加入
    await manager.broadcast({
        "type": "system",
        "sender": "Server",
        "content": f"Player {client_id} has joined the session."
    })
    
    try:
        while True:
            # 持续接收来自 Unity 的数据 (JSON格式)
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            logger.info(f"Received from {client_id}: {data}")
            
            # 【核心逻辑预留区】：在这里拦截数据
            # 如果 data["type"] == "npc_chat"，你就调用 Tan Rui 的 generator.py
            # 如果 data["type"] == "update_hp"，你就调用 Yang Zixu 的 db.py
            
            # 目前的默认行为：将收到的消息加上发送者ID，直接广播给所有人
            response_message = {
                "type": data.get("type", "chat"),
                "sender": client_id,
                "content": data.get("content", "")
            }
            await manager.broadcast(response_message)
            
    except WebSocketDisconnect:
        # 处理玩家异常掉线
        manager.disconnect(websocket)
        await manager.broadcast({
            "type": "system",
            "sender": "Server",
            "content": f"Player {client_id} has disconnected."
        })
    except json.JSONDecodeError:
        logger.error(f"Received invalid JSON from {client_id}")