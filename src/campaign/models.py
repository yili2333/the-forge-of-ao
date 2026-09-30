"""
战役数据模型 (Campaign Models)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CampaignStatus(str, Enum):
    PLANNING   = "planning"    # 筹备中
    ACTIVE     = "active"      # 进行中
    PAUSED     = "paused"      # 暂停
    COMPLETED  = "completed"   # 已完结


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: f"camp-{uuid.uuid4().hex[:10]}")
    name: str
    description: str = ""

    dm_owner_id: str                    # DM 的 stable_key
    dm_display: str = ""                # DM 的显示名

    status: CampaignStatus = CampaignStatus.PLANNING

    player_ids: list[str] = Field(default_factory=list)      # 成员 owner_id
    character_ids: list[str] = Field(default_factory=list)   # 参团角色 ID
    world_map_id: str = ""                                    # 关联大地图 ID
    session_count: int = 0

    edition: Literal["2024", "2014"] = "2024"
    tags: list[str] = Field(default_factory=list)            # 自由标签

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class CampaignSummary(BaseModel):
    id: str
    name: str
    dm_owner_id: str
    dm_display: str
    status: CampaignStatus
    player_count: int
    character_count: int
    session_count: int
    updated_at: str


def campaign_to_summary(c: Campaign) -> CampaignSummary:
    return CampaignSummary(
        id=c.id,
        name=c.name,
        dm_owner_id=c.dm_owner_id,
        dm_display=c.dm_display,
        status=c.status,
        player_count=len(c.player_ids),
        character_count=len(c.character_ids),
        session_count=c.session_count,
        updated_at=c.updated_at,
    )


class CampaignInvite(BaseModel):
    """战役邀请码"""
    code: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:8].upper()
    )                                       # 8位大写邀请码，如 "A3F9B2C1"
    campaign_id: str
    campaign_name: str = ""
    dm_display: str = ""
    max_uses: int = 10                      # 最多可使用次数（-1=无限）
    uses: int = 0                           # 已使用次数
    expires_at: str = ""                    # ISO 时间戳；空=永不过期
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    is_active: bool = True
