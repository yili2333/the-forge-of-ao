"""
游戏场次数据模型 (Session Models)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InitiativeEntry(BaseModel):
    instance_id: str        # character_id 或 monster instance id
    name: str
    initiative: int
    is_player: bool = True
    is_hidden: bool = False  # 隐藏的 NPC（DM 专属可见）
    hp_current: int = 0
    hp_max: int = 0


class SceneData(BaseModel):
    encounter_map_id: str = ""   # 关联 EncounterMap ID
    description: str = ""        # 文字描述，备用
    ambient: str = ""            # 环境音效/氛围标签


class GameSession(BaseModel):
    """
    单局游戏状态快照。
    内存中的 RoomState 与此对应；服务重启后从此恢复。
    """
    id: str = Field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:10]}")
    campaign_id: str

    round_number: int = 0
    current_turn_index: int = 0
    initiative: list[InitiativeEntry] = Field(default_factory=list)
    scene: SceneData | None = None

    # 当前正在进行的遭遇战地图 ID（用于重启后恢复生物坐标）
    active_encounter_map_id: str = ""

    started_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_active_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class SessionOpLog(BaseModel):
    """
    操作日志条目（append-only，用于审计/重放）。
    """
    id: int | None = None          # DB autoincrement，写入后填充
    session_id: str
    op_type: str                   # "roll"/"hp_change"/"initiative"/"scene_change"/"rest"
    actor_id: str = ""             # 操作者 owner_id
    payload: dict[str, Any] = Field(default_factory=dict)
    round_number: int = 0
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
