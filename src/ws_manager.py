"""
WebSocket 房间管理器

负责维护所有在线玩家的 WebSocket 连接，以及每个战役房间的运行时状态
（先攻顺序、当前场景、轮次计数等）。

持久化策略：
  - RoomState 保持内存级（快速访问）
  - 状态变更 → 异步写入 SessionOpLog（fire-and-forget）
  - 连接时内存无状态 → 尝试从 DB 最新 GameSession 快照恢复
  - 每 UPDATE_INITIATIVE / UPDATE_SCENE → 也自动保存 GameSession 快照
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from ws_models import (
    WSMessage, WSMsgType,
    MemberInfo, SyncData,
    InitiativeUpdateData, SceneUpdateData,
)

logger = logging.getLogger(__name__)


# ================================================================
#  运行时房间状态
# ================================================================

@dataclass
class RoomState:
    """每个战役房间的运行时共享状态（先攻、场景、轮次、地图生物位置）"""
    campaign_id: str
    # 先攻条目：已序列化为 dict（从 InitiativeEntry.model_dump()）
    initiative: list[dict[str, Any]] = field(default_factory=list)
    current_turn: int = 0      # initiative 列表中的当前索引
    round_number: int = 1
    scene: dict[str, Any] = field(default_factory=dict)

    # 当前活跃遭遇战地图 ID（空字符串=无遭遇战）
    active_encounter_map_id: str = ""
    # 生物位置缓存：instance_id → {x, y, hp_current, hp_max, conditions, is_hidden, name, is_player}
    # 权威数据在 EncounterMap 表，此处为内存快照供 SYNC 快速下发
    creature_positions: dict[str, dict[str, Any]] = field(default_factory=dict)


# ================================================================
#  连接管理器
# ================================================================

class ConnectionManager:
    """
    管理所有 WebSocket 连接及房间状态。

    数据结构：
        _rooms  : campaign_id  →  { WebSocket → MemberInfo }
        _states : campaign_id  →  RoomState

    线程安全说明：FastAPI 运行在单一 asyncio 事件循环中；
    所有回调都是协程，无真正并发修改，无需锁。
    """

    def __init__(self) -> None:
        self._rooms:  dict[str, dict[WebSocket, MemberInfo]] = {}
        self._states: dict[str, RoomState] = {}

    # ----------------------------------------------------------------
    #  内部辅助
    # ----------------------------------------------------------------

    def _get_room(self, campaign_id: str) -> dict[WebSocket, MemberInfo]:
        return self._rooms.setdefault(campaign_id, {})

    def _get_state(self, campaign_id: str) -> RoomState:
        if campaign_id not in self._states:
            self._states[campaign_id] = RoomState(campaign_id=campaign_id)
        return self._states[campaign_id]

    # ----------------------------------------------------------------
    #  连接生命周期
    # ----------------------------------------------------------------

    async def connect(
        self,
        ws: WebSocket,
        campaign_id: str,
        member: MemberInfo,
    ) -> None:
        """
        接受连接，加入房间。
        1. ws.accept()
        2. 将连接登记到房间
        3. 若内存无状态 → 尝试从 DB 恢复最新 GameSession 快照
        4. 向房间内其他成员广播 JOIN
        5. 向新成员推送 SYNC（当前状态快照）
        """
        await ws.accept()
        room = self._get_room(campaign_id)
        room[ws] = member

        # 若内存中还没有该房间的状态，尝试从 DB 恢复
        if campaign_id not in self._states:
            await self._try_restore_from_db(campaign_id)

        # 通知其他人有新成员加入
        join_msg = WSMessage(
            type=WSMsgType.JOIN,
            sender="server",
            data=member.model_dump(),
        )
        await self.broadcast(campaign_id, join_msg, exclude=ws)

        # 向新成员同步当前状态（含角色卡快照，供重连恢复）
        state = self._get_state(campaign_id)

        # 生物位置：DM 获得全部（含隐藏），玩家通过视野共享系统过滤
        if member.is_dm:
            positions_for_client = state.creature_positions
        else:
            positions_for_client = await self._filter_positions_for_player(
                state, campaign_id, member
            )

        sync_data: dict = {
            "members": [m.model_dump() for m in room.values()],
            "initiative": state.initiative,
            "current_turn": state.current_turn,
            "round_number": state.round_number,
            "scene": state.scene or None,
            # 地图位置快照（重连时恢复棋盘状态）
            "active_encounter_map_id": state.active_encounter_map_id,
            "creature_positions": positions_for_client,
            # 扩展：角色快照（只同步本人角色，DM 获得全部）
            "character_snapshot": None,
            "all_characters": [],   # DM 专属：全量角色列表摘要
        }

        # 异步拉取角色快照
        try:
            from character.storage import get_character, list_characters_by_campaign
            if member.is_dm:
                # DM 获取战役内所有角色的摘要
                chars = await list_characters_by_campaign(campaign_id)
                sync_data["all_characters"] = [
                    {"id": c.id, "name": c.name, "owner_id": c.owner_id,
                     "total_level": c.total_level, "hp_current": c.hit_points.current,
                     "hp_max": c.hit_points.maximum, "conditions": [v.value for v in c.conditions]}
                    for c in chars
                ]
            elif member.character_id:
                # 玩家只拿自己的角色完整数据
                char = await get_character(member.character_id)
                if char and char.owner_id == member.owner_id:
                    sync_data["character_snapshot"] = char.model_dump()
        except Exception as exc:
            logger.warning("SYNC 角色快照加载失败: %s", exc)

        await self.send_personal(
            ws,
            WSMessage(type=WSMsgType.SYNC, sender="server", data=sync_data),
        )

    async def _try_restore_from_db(self, campaign_id: str) -> None:
        """尝试从 DB 最新 GameSession 恢复 RoomState（服务重启后用）"""
        try:
            from session.storage import get_latest_session
            session = await get_latest_session(campaign_id)
            if session is not None:
                state = self._get_state(campaign_id)
                state.initiative = [e.model_dump() for e in session.initiative]
                state.current_turn = session.current_turn_index
                state.round_number = session.round_number
                if session.scene:
                    state.scene = session.scene.model_dump()

                # 恢复活跃遭遇战地图 ID（优先用 session 记录，备选 scene 中的 ID）
                map_id = session.active_encounter_map_id
                if not map_id and session.scene:
                    map_id = session.scene.encounter_map_id
                if map_id:
                    state.active_encounter_map_id = map_id
                    await self._load_creature_positions(state, map_id)

                logger.info(
                    "已从 DB 恢复战役 %s 的房间状态（session %s，地图 %s，%d 只生物）",
                    campaign_id, session.id, map_id or "无", len(state.creature_positions),
                )
        except Exception as exc:
            logger.warning("从 DB 恢复房间状态失败: %s", exc)

    async def _load_creature_positions(self, state: RoomState, map_id: str) -> None:
        """从 EncounterMap 表加载生物位置到 RoomState 缓存"""
        try:
            from maps.storage import get_encounter_map
            emap = await get_encounter_map(map_id)
            if emap:
                state.creature_positions = {
                    c.instance_id: {
                        "x":                 c.x,
                        "y":                 c.y,
                        "hp_current":        c.hp_current,
                        "hp_max":            c.hp_max,
                        "conditions":        c.conditions,
                        "is_hidden":         c.is_hidden,
                        "name":              c.name,
                        "is_player":         c.is_player,
                        # 行动经济字段（怪物专用；玩家角色以 CharacterSheet 为准）
                        "action_used":            c.action_used,
                        "bonus_action_used":      c.bonus_action_used,
                        "reaction_used":          c.reaction_used,
                        "movement_used":          c.movement_used,
                        "legendary_actions_max":  c.legendary_actions_max,
                        "legendary_actions_used": c.legendary_actions_used,
                    }
                    for c in emap.creatures
                }
        except Exception as exc:
            logger.warning("加载遭遇地图 %s 生物位置失败: %s", map_id, exc)

    async def _filter_positions_for_player(
        self,
        state: RoomState,
        campaign_id: str,
        member: MemberInfo,
    ) -> dict[str, Any]:
        """
        Apply vision-sharing rules: return only creature positions visible
        to the connecting player (based on their characters' LOS + shared vision).
        Falls back to simple is_hidden filter if map/character data unavailable.
        """
        try:
            from maps.storage import get_encounter_map
            from maps.vision import filter_positions_for_player
            from character.storage import list_characters_by_campaign

            map_id = state.active_encounter_map_id
            if not map_id:
                raise ValueError("no active map")

            emap = await get_encounter_map(map_id)
            if not emap:
                raise ValueError("map not found")

            chars = await list_characters_by_campaign(campaign_id)
            # Collect character IDs owned by this player
            player_char_ids = [c.id for c in chars if c.owner_id == member.owner_id]

            return filter_positions_for_player(
                state.creature_positions,
                emap.creatures,
                emap.cells,
                player_char_ids,
            )
        except Exception:
            # Fallback: hide is_hidden creatures
            return {
                iid: pos for iid, pos in state.creature_positions.items()
                if not pos.get("is_hidden", False)
            }

    def disconnect(
        self,
        ws: WebSocket,
        campaign_id: str,
    ) -> MemberInfo | None:
        """
        从房间中移除连接。返回离开的 MemberInfo（用于 LEAVE 广播）。
        故意不清理空房间——保留先攻/场景状态，方便玩家断线重连。
        """
        room = self._rooms.get(campaign_id, {})
        return room.pop(ws, None)

    # ----------------------------------------------------------------
    #  发送
    # ----------------------------------------------------------------

    async def send_personal(self, ws: WebSocket, msg: WSMessage) -> None:
        """向单个连接发送消息；连接已断开时静默忽略。"""
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(msg.encode())
        except Exception:
            pass

    async def broadcast(
        self,
        campaign_id: str,
        msg: WSMessage,
        exclude: WebSocket | None = None,
    ) -> None:
        """
        向房间内所有连接广播消息。
        发送后统一清理死连接（避免在迭代时修改字典）。
        """
        room = self._rooms.get(campaign_id, {})
        if not room:
            return

        dead: list[WebSocket] = []
        encoded = msg.encode()

        for ws, _member in list(room.items()):
            if ws is exclude:
                continue
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(encoded)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)

        for ws in dead:
            room.pop(ws, None)

    async def send_to_member(
        self,
        campaign_id: str,
        owner_id: str,
        msg: WSMessage,
    ) -> bool:
        """
        向指定 owner_id 发送消息（悄悄话）。
        返回 True 表示找到并发送，False 表示目标不在线。
        """
        room = self._rooms.get(campaign_id, {})
        found = False
        for ws, member in list(room.items()):
            if member.owner_id == owner_id:
                await self.send_personal(ws, msg)
                found = True
        return found

    # ----------------------------------------------------------------
    #  查询
    # ----------------------------------------------------------------

    def get_members(self, campaign_id: str) -> list[MemberInfo]:
        return list(self._rooms.get(campaign_id, {}).values())

    def get_dm_sockets(self, campaign_id: str) -> list[WebSocket]:
        """返回该房间所有 DM 的 WebSocket 句柄。"""
        room = self._rooms.get(campaign_id, {})
        return [ws for ws, m in room.items() if m.is_dm]

    def is_dm(self, ws: WebSocket, campaign_id: str) -> bool:
        member = self._rooms.get(campaign_id, {}).get(ws)
        return member is not None and member.is_dm

    def get_room_state(self, campaign_id: str) -> RoomState:
        return self._get_state(campaign_id)

    # ----------------------------------------------------------------
    #  状态变更（由消息处理器调用）
    # ----------------------------------------------------------------

    def update_initiative(
        self,
        campaign_id: str,
        data: InitiativeUpdateData,
        actor_id: str = "",
    ) -> None:
        state = self._get_state(campaign_id)
        state.initiative = [e.model_dump() for e in data.entries]
        state.current_turn = data.current_turn
        state.round_number = data.round_number

        # 异步写入 op_log + 保存 GameSession 快照
        asyncio.create_task(self._persist_state(campaign_id, "initiative", actor_id, {
            "round_number": data.round_number,
            "current_turn": data.current_turn,
            "entries_count": len(data.entries),
        }))

    def update_scene(
        self,
        campaign_id: str,
        data: SceneUpdateData,
        actor_id: str = "",
    ) -> None:
        state = self._get_state(campaign_id)
        state.scene = data.model_dump()

        # 切换到新遭遇战地图时，重新加载生物位置快照
        if data.encounter_map_id and data.encounter_map_id != state.active_encounter_map_id:
            state.active_encounter_map_id = data.encounter_map_id
            state.creature_positions = {}   # 先清空，_load_creature_positions 异步填充
            asyncio.create_task(self._load_creature_positions(state, data.encounter_map_id))
        elif not data.encounter_map_id:
            # 离开遭遇战（如切回大地图），清空位置缓存
            state.active_encounter_map_id = ""
            state.creature_positions = {}

        asyncio.create_task(self._persist_state(campaign_id, "scene_change", actor_id, {
            "encounter_map_id": data.encounter_map_id,
            "description": data.description[:80],
        }))

    def update_creature_position(
        self,
        campaign_id: str,
        instance_id: str,
        x: int,
        y: int,
        actor_id: str = "",
    ) -> None:
        """
        更新 RoomState 中的生物位置缓存（在 main.py 已将位置写入 DB 之后调用）。
        同时写入 op_log，但不额外触发 GameSession 快照（位置权威数据已在 EncounterMap 表）。
        """
        state = self._get_state(campaign_id)
        if instance_id in state.creature_positions:
            state.creature_positions[instance_id]["x"] = x
            state.creature_positions[instance_id]["y"] = y
        else:
            state.creature_positions[instance_id] = {"x": x, "y": y}

        try:
            asyncio.get_running_loop().create_task(self._persist_state(
                campaign_id, "creature_move", actor_id,
                {"instance_id": instance_id, "x": x, "y": y},
            ))
        except RuntimeError:
            pass  # 无事件循环（测试环境），跳过后台持久化

    def update_creature_hp_in_room(
        self,
        campaign_id: str,
        instance_id: str,
        hp_current: int,
        conditions: list[str] | None = None,
    ) -> None:
        """更新 RoomState 生物 HP / 状态缓存（DB 写入由调用方完成）"""
        state = self._get_state(campaign_id)
        entry = state.creature_positions.setdefault(instance_id, {})
        entry["hp_current"] = hp_current
        if conditions is not None:
            entry["conditions"] = conditions

    async def _persist_state(
        self,
        campaign_id: str,
        op_type: str,
        actor_id: str,
        payload: dict,
    ) -> None:
        """将当前 RoomState 保存为 GameSession 快照，并写入 op_log"""
        try:
            from session.models import GameSession, InitiativeEntry, SceneData, SessionOpLog
            from session.storage import save_session, append_op_log

            state = self._get_state(campaign_id)
            initiative = [InitiativeEntry(**e) for e in state.initiative]
            scene = SceneData(**state.scene) if state.scene else None

            session = GameSession(
                campaign_id=campaign_id,
                round_number=state.round_number,
                current_turn_index=state.current_turn,
                initiative=initiative,
                scene=scene,
                active_encounter_map_id=state.active_encounter_map_id,
            )
            saved = await save_session(session)

            log = SessionOpLog(
                session_id=saved.id,
                op_type=op_type,
                actor_id=actor_id,
                payload=payload,
                round_number=state.round_number,
            )
            await append_op_log(log)
        except Exception as exc:
            logger.warning("持久化 RoomState 失败: %s", exc)

    # ----------------------------------------------------------------
    #  维护
    # ----------------------------------------------------------------

    def cleanup_empty_rooms(self) -> list[str]:
        """清理无人的空房间（可由后台定时任务调用）。"""
        empty = [cid for cid, room in self._rooms.items() if not room]
        for cid in empty:
            del self._rooms[cid]
            self._states.pop(cid, None)
        return empty
