"""
WebSocket 消息协议

所有客户端 ↔ 服务器消息均使用同一个 WSMessage 信封:
{
  "type":      "chat" | "roll" | ...,   # 消息类型
  "sender":    "Alice#1234",            # 发送者 owner_id（服务器消息用 "server"）
  "data":      { ... },                  # 消息负载（见各 *Data 类）
  "ts":        "2025-04-11T10:00:00Z",  # UTC ISO 时间戳
  "msg_id":   "a1b2c3d4"               # 8 位随机 ID（客户端可用于去重）
}

消息类型总览
────────────────────────────────────────
连接生命周期（服务器发出）:
  join          玩家进入房间
  leave         玩家离开房间
  sync          新连接时服务器推送当前房间状态
  error         服务器报告错误
  ping / pong   心跳

游戏交互（客户端发出，服务器广播）:
  chat          文本聊天（支持悄悄话 whisper_to）
  roll          掷骰请求
  roll_result   掷骰结果（服务器广播）
  initiative_update  先攻顺序更新（DM 操作）
  scene_update  场景/地图更新（DM 操作）
  character_update   角色表变动

RAG（客户端发出，服务器单播回复）:
  rule_query    规则查询请求
  rule_result   规则查询结果
────────────────────────────────────────
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ================================================================
#  消息类型枚举
# ================================================================

class WSMsgType(str, Enum):
    # 连接
    JOIN             = "join"
    LEAVE            = "leave"
    SYNC             = "sync"
    ERROR            = "error"
    PING             = "ping"
    PONG             = "pong"

    # 游戏
    CHAT             = "chat"
    ROLL             = "roll"
    ROLL_RESULT      = "roll_result"
    INITIATIVE_UPDATE = "initiative_update"
    SCENE_UPDATE     = "scene_update"
    CHARACTER_UPDATE = "character_update"

    # RAG
    RULE_QUERY       = "rule_query"
    RULE_RESULT      = "rule_result"

    # NPC 对话（玩家与 NPC 交互 → 服务器调用 RAG 生成回复）
    NPC_CHAT         = "npc_chat"
    NPC_RESPONSE     = "npc_response"

    # 休息结果广播
    REST_COMPLETE    = "rest_complete"

    # 地图系统（Phase C）
    MAP_UPDATE       = "map_update"       # 服务器推送地图变化
    CREATURE_MOVE    = "creature_move"    # DM 移动棋盘上的生物
    CREATURE_HP      = "creature_hp"      # 生物 HP 变化广播
    FOG_UPDATE       = "fog_update"       # 迷雾变化（DM 操作）
    POI_REVEAL       = "poi_reveal"       # DM 揭示大地图地点

    # 战斗回合推进
    TURN_ADVANCE     = "turn_advance"     # DM 推进回合（也可自动触发）
    COMBAT_START     = "combat_start"     # 战斗开始
    COMBAT_END       = "combat_end"       # 战斗结束（DM 操作）

    # 死亡豁免
    DEATH_SAVE       = "death_save"       # 玩家掷死亡豁免（结果广播给全员）

    # 状态异常
    CONDITION_UPDATE = "condition_update" # 应用/移除状态异常（DM 操作）

    # DM 审批流
    DM_APPROVAL_REQUEST = "dm_approval_request"  # 服务器→DM：有新角色等待审批
    DM_APPROVAL_RESULT  = "dm_approval_result"   # 服务器→玩家：审批结果通知

    # 战利品 / XP 分配
    LOOT_GRANT       = "loot_grant"       # DM 分配战利品/XP，服务器广播给玩家
    XP_GAIN          = "xp_gain"          # XP 增加结果广播（含升级提示）

    # 战斗动作资源
    REACTION_USED    = "reaction_used"    # 玩家消耗反应动作（机会攻击、盾牌法术等）
    CAST_CONCENTRATION_SPELL = "cast_concentration_spell"  # 施放集中法术，接管 concentration_effect_id
    OPPORTUNITY_ATTACK = "opportunity_attack"  # 服务器通知：有生物触发了机会攻击
    CREATURE_ACTION  = "creature_action"   # DM 标记地图上怪物的行动/附赠动作/反应已使用或重置
    LEGENDARY_ACTION = "legendary_action"  # DM 消耗或重置传奇动作点数

    # 攻击解算
    ATTACK           = "attack"           # 攻击请求（DM 或玩家发出）
    ATTACK_RESULT    = "attack_result"    # 攻击解算结果（服务器广播）

    # 通用豁免检定（P1）
    SAVING_THROW        = "saving_throw"         # DM 发起单目标豁免检定
    SAVING_THROW_RESULT = "saving_throw_result"  # 服务器广播豁免结果

    # AoE 伤害分发（P1）
    AOE_ATTACK        = "aoe_attack"        # DM 发起范围攻击（火球术等）
    AOE_ATTACK_RESULT = "aoe_attack_result" # 服务器广播汇总结果

    # 先攻自动投骰（P1）
    ROLL_INITIATIVE   = "roll_initiative"   # DM 一键为所有生物投先攻


# ================================================================
#  信封
# ================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _short_id() -> str:
    return uuid.uuid4().hex[:8]


class WSMessage(BaseModel):
    """通用消息信封，客户端和服务器均使用此结构"""
    type: WSMsgType
    sender: str = "server"                       # owner_id 或 "server"
    data: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=_now_iso)
    msg_id: str = Field(default_factory=_short_id)

    def encode(self) -> str:
        return self.model_dump_json()

    @classmethod
    def decode(cls, raw: str) -> "WSMessage":
        return cls.model_validate_json(raw)


# ================================================================
#  各消息类型的 data 负载结构
#  （可选：用于服务器内部构建，不强制要求客户端使用）
# ================================================================

# ---- 连接 ----

class MemberInfo(BaseModel):
    """房间内的一名玩家/DM 信息"""
    owner_id: str                               # "Alice#1234"
    role: str = "player"                        # "player" | "dm"
    character_id: str | None = None
    display_name: str = ""                      # 可选昵称（不含 #tag）
    connected_at: str = Field(default_factory=_now_iso)

    @property
    def is_dm(self) -> bool:
        return self.role == "dm"


class SyncData(BaseModel):
    """服务器在玩家加入时推送的当前房间状态"""
    members: list[dict[str, Any]]
    initiative: list[dict[str, Any]] = Field(default_factory=list)
    current_turn: int = 0
    scene: dict[str, Any] | None = None
    round_number: int = 1


# ---- 聊天 ----

class ChatData(BaseModel):
    text: str
    whisper_to: str | None = None    # None = 广播；填 owner_id = 悄悄话
    is_ooc: bool = False             # Out-of-character 标记（浅色显示）


# ---- 掷骰 ----

class RollRequestData(BaseModel):
    expression: str         # "1d20+5"、"4d6k3"、"2d6 adv" 等
    reason: str = ""        # "攻击检定"、"先攻"、"豁免"…
    secret: bool = False    # True = 仅 DM 可见
    target: str | None = None   # 对准哪个角色/怪物（可选标注）


class RollResultData(BaseModel):
    expression: str
    total: int
    rolls: list[int]         # 所有骰子原始值
    kept: list[int]          # 纳入合计的骰子值
    modifier: int
    breakdown: str           # 可读拆分，如 "[3,5,6](k3=14)+2=16"
    reason: str
    roller: str              # owner_id
    secret: bool = False
    natural_20: bool = False
    natural_1: bool = False


# ---- 先攻 ----

class InitiativeEntry(BaseModel):
    id: str                     # 唯一标识（character_id 或怪物实例 ID）
    name: str
    initiative: int
    is_player: bool = True
    character_id: str | None = None
    hp_current: int | None = None
    hp_max: int | None = None
    conditions: list[str] = Field(default_factory=list)  # 状态条件
    active: bool = True


class InitiativeUpdateData(BaseModel):
    entries: list[InitiativeEntry]
    current_turn: int = 0       # 当前轮到的 entries 索引
    round_number: int = 1


# ---- 场景 ----

class SceneUpdateData(BaseModel):
    scene_id: str | None = None
    encounter_map_id: str = ""     # 关联 EncounterMap ID
    name: str = ""
    description: str = ""
    map_url: str | None = None     # 地图图片 URL
    ambient: str | None = None     # 音效/氛围描述


# ---- 角色表 ----

class CharacterUpdateData(BaseModel):
    character_id: str
    changed_fields: dict[str, Any]   # 只传变更的字段，减少负载
    full_sync: bool = False          # True = 推送完整 sheet JSON


# ---- 规则查询 ----

class RuleQueryData(BaseModel):
    question: str
    campaign_id: str | None = None
    character_id: str | None = None  # 若提供，自动注入角色上下文
    top_k: int = 5


class RuleResultData(BaseModel):
    question: str
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    chunks_used: int = 0


# ---- NPC 对话 ----

class NpcChatData(BaseModel):
    """玩家向 NPC 发送对话请求"""
    npc_name: str                       # NPC 名称（如 "酒馆老板"、"神秘商人"）
    message: str                        # 玩家说的话
    character_id: str | None = None     # 发言角色 ID（用于注入角色上下文）
    campaign_id: str | None = None      # 战役 ID（用于检索自定义规则/设定）
    top_k: int = 3                      # 检索规则条数（NPC 对话不需要太多）


class NpcResponseData(BaseModel):
    """NPC 回复。
    is_suggestion=True  → 仅发给 DM，为 LLM 生成的建议文本，等待 DM 修改/确认
    is_suggestion=False → DM 确认后广播给全员的最终回复
    """
    npc_name: str
    response: str                       # NPC 的回复文本
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    triggered_by: str = ""              # 触发此对话的玩家 owner_id
    is_suggestion: bool = False         # True = 仅 DM 可见的建议；False = 已确认，对全员可见


# ---- 休息结果 ----

class RestCompleteData(BaseModel):
    """休息完成广播（通知所有人某玩家完成了休息）"""
    character_id: str
    owner_id: str
    rest_type: str                      # "short" | "long"
    hp_gained: int = 0
    resources_recovered: list[str] = Field(default_factory=list)
    effects_expired: list[str] = Field(default_factory=list)


# ---- 地图系统 ----

class MapUpdateData(BaseModel):
    """服务器推送地图变化（世界地图或遭遇战地图）"""
    map_type: str                        # "world" | "encounter"
    map_id: str
    change_type: str                     # "full_update" | "creature_moved" | "fog_changed" | "poi_revealed"
    payload: dict[str, Any] = Field(default_factory=dict)


class CreatureMoveData(BaseModel):
    """DM 移动棋盘上的生物"""
    encounter_map_id: str
    instance_id: str                     # MapCreature.instance_id
    x: int
    y: int
    reason: str = ""


class CreatureHpData(BaseModel):
    """生物 HP 变化广播（怪物 HP 全量仅 DM 可见时，此处可发送模糊信息给玩家）"""
    encounter_map_id: str
    instance_id: str
    hp_current: int
    hp_max: int
    damage_taken: int = 0
    is_hidden: bool = False              # True = 只广播给 DM


class FogUpdateData(BaseModel):
    """迷雾变化（DM 操作）"""
    encounter_map_id: str
    revealed_cells: list[dict[str, int]] = Field(default_factory=list)   # [{"x":0,"y":0}, ...]
    hidden_cells: list[dict[str, int]] = Field(default_factory=list)


class PoiRevealData(BaseModel):
    """DM 揭示大地图地点"""
    world_map_id: str
    poi_id: str
    poi_name: str
    visible_to: list[str] = Field(default_factory=list)   # owner_id 列表；空=所有人


# ---- 战斗回合推进 ----

class TurnAdvanceData(BaseModel):
    """
    回合推进广播。
    DM 发送此消息（或服务器自动触发），推进 current_turn_index。
    包含下一个行动者信息供客户端高亮显示。
    """
    current_turn: int          # 推进后的 current_turn_index
    round_number: int          # 当前回合数（index 归零时 +1）
    active_entry_id: str       # 当前行动者的 InitiativeEntry.id
    active_entry_name: str     # 当前行动者名称（方便日志显示）
    round_started: bool = False  # True = 本次推进触发了新一轮（index 归零）


class CombatStartData(BaseModel):
    """战斗开始广播"""
    encounter_map_id: str = ""   # 关联遭遇地图（可选）
    description: str = ""        # 战斗场景描述


class CombatEndData(BaseModel):
    """战斗结束广播"""
    outcome: str = ""            # "victory" | "defeat" | "retreat" | ""
    rounds_elapsed: int = 0      # 总共经历的回合数
    description: str = ""


# ---- 死亡豁免 ----

class DeathSaveData(BaseModel):
    """
    死亡豁免掷骰结果广播。
    玩家 HP=0 时每回合掷 1d20：≥10=成功，<10=失败；1=2次失败；20=立即稳定。
    3次成功→稳定，3次失败→死亡。
    """
    character_id: str
    roll: int                    # 骰子结果（1-20）
    is_success: bool
    successes: int               # 累计成功次数
    failures: int                # 累计失败次数
    is_stable: bool = False      # True = 角色已稳定
    is_dead: bool = False        # True = 3 次失败，角色死亡
    natural_20: bool = False     # True = 投出 20，立即稳定
    natural_1: bool = False      # True = 投出 1，计2次失败


# ---- 状态异常 ----

class ConditionUpdateData(BaseModel):
    """
    DM 对目标应用或移除状态异常。
    target_type: "character" | "creature"（地图上的怪物）
    """
    target_id: str               # character_id 或 MapCreature.instance_id
    target_type: str = "character"   # "character" | "creature"
    condition: str               # Condition enum value，如 "blinded"
    action: str                  # "add" | "remove"
    encounter_map_id: str = ""   # 非角色目标时需要


# ---- DM 审批流 ----

class DmApprovalRequestData(BaseModel):
    """服务器 → DM：提醒有非标准角色等待审批"""
    character_id: str
    character_name: str
    owner_id: str
    owner_display: str = ""
    campaign_id: str = ""
    non_standard_reason: str = ""  # 说明为何非标准（如特殊种族/专长）


class DmApprovalResultData(BaseModel):
    """服务器 → 角色拥有者：DM 审批结果通知"""
    character_id: str
    character_name: str
    approved: bool
    dm_note: str = ""            # DM 备注


# ---- 战利品 / XP ----

class LootGrantData(BaseModel):
    """DM 向参战角色分配战利品和经验值"""
    encounter_id: str = ""          # 遭遇标识（可为空）
    xp_per_player: int = 0          # 每人获得的经验值
    gold: float = 0.0
    items: list[dict[str, Any]] = Field(default_factory=list)  # [{name, quantity, ...}]
    recipient_ids: list[str] = Field(default_factory=list)     # character_id 列表；空=全员


class XpGainData(BaseModel):
    """XP 增加结果广播（REST 端点授予 XP 后广播给房间）"""
    character_id: str
    character_name: str = ""
    owner_id: str
    xp_gained: int
    xp_before: int
    xp_after: int
    level_before: int
    level_after: int
    leveled_up: bool
    xp_to_next: int
    note: str = ""                    # 来源备注，如"击败骷髅王"


# ---- 战斗动作资源 ----

class ReactionUsedData(BaseModel):
    """玩家消耗反应动作（机会攻击、盾牌法术、反击等）"""
    character_id: str
    reason: str = ""                  # "机会攻击" / "盾牌法术" / "反击" / ...


class CastConcentrationSpellData(BaseModel):
    """玩家施放集中法术，服务器接管 concentration_effect_id。
    若角色已有集中，旧法术自动解除。
    effect_id 必须已存在于 CharacterSheet.active_effects 中。
    """
    character_id: str
    effect_id: str                    # ActiveEffect.id
    spell_name: str                   # 仅用于广播显示


class OpportunityAttackData(BaseModel):
    """服务器通知：某生物的移动触发了机会攻击。
    DM 负责决定是否执行攻击（调用 REACTION_USED 确认消耗反应）。
    """
    encounter_map_id: str
    attacker_instance_id: str         # 拥有机会攻击机会的生物
    attacker_name: str
    mover_instance_id: str            # 触发机会攻击的移动者
    mover_name: str
    attacker_is_player: bool = False  # 攻击者是否为玩家角色


class AttackData(BaseModel):
    """攻击请求。攻击者/目标各用二选一字段标识。

    attacker_instance_id  → 怪物/地图生物（MapCreature.instance_id）
    attacker_character_id → 玩家角色（CharacterSheet.id）

    auto_calculate=True 时：服务器从攻击者角色卡自动计算命中加值；
    auto_calculate=False 时：直接使用 to_hit_bonus 字段。

    advantage:
      "normal"      → 1d20
      "advantage"   → 1d20adv（取高）
      "disadvantage"→ 1d20dis（取低）
    """
    encounter_map_id: str

    # 攻击者（二选一）
    attacker_instance_id: str = ""    # 地图生物 instance_id
    attacker_character_id: str = ""   # 玩家角色 character_id

    # 目标（二选一）
    target_instance_id: str = ""      # 地图生物 instance_id
    target_character_id: str = ""     # 玩家角色 character_id

    # 攻击属性
    attack_type: str = "weapon"       # "weapon" | "spell" | "unarmed"
    weapon_name: str = ""             # 武器名（auto_calculate 时查背包用；同时用于显示）
    to_hit_bonus: int = 0             # 手动命中加值（auto_calculate=False 时生效）
    damage_dice: str = "1d4"          # 伤害骰表达式，如 "1d8+3"、"2d6"
    damage_type: str = ""             # "slashing" | "piercing" | "fire" | ...
    advantage: str = "normal"         # "normal" | "advantage" | "disadvantage"
    auto_calculate: bool = True       # True = 服务器从角色卡重算命中加值
    magical_bonus: int = 0            # 魔法武器加值（auto_calculate=True 时由服务器读取）
    spell_slot_level: int = 0         # 命中时自动扣减的法术位等级（0 = 不扣）


class AttackResultData(BaseModel):
    """攻击解算结果广播。包含完整的命中/伤害/HP 更新信息。"""
    encounter_map_id: str

    # 攻击者信息
    attacker_instance_id: str = ""
    attacker_character_id: str = ""
    attacker_name: str = ""

    # 目标信息
    target_instance_id: str = ""
    target_character_id: str = ""
    target_name: str = ""
    target_ac: int = 0

    # 命中骰
    to_hit_bonus: int = 0
    attack_roll: int = 0              # 原始 d20 点数（不含加值）
    total_to_hit: int = 0             # attack_roll + to_hit_bonus
    is_hit: bool = False
    is_crit: bool = False             # 自然 20
    is_crit_fail: bool = False        # 自然 1

    # 伤害
    damage_dice_rolled: str = ""      # 实际掷的伤害骰（重击时已 doubled）
    damage_raw: int = 0               # 未经抗性的原始伤害
    damage_final: int = 0             # 经抗性/免疫/易伤后的最终伤害
    damage_type: str = ""
    resistant: bool = False
    immune: bool = False
    vulnerable: bool = False

    # 目标 HP 更新
    target_hp_before: int = 0
    target_hp_after: int = 0
    target_is_down: bool = False      # hp_after <= 0

    # 集中检定（目标是正在集中的玩家时）
    concentration_check: dict | None = None

    # 可读摘要（方便聊天栏显示）
    roll_breakdown: str = ""


class CreatureActionData(BaseModel):
    """DM 标记地图上某怪物/生物的行动资源使用或重置。

    action 取值：
      "action"        → 切换 action_used（used=True 标记已用，used=False 恢复）
      "bonus_action"  → 切换 bonus_action_used
      "reaction"      → 切换 reaction_used
      "reset"         → 重置全部行动资源（movement_used=0，action/bonus/reaction=False）

    广播给全员，前端可更新怪物 token 上的行动标记显示。
    """
    encounter_map_id: str
    instance_id: str                  # MapCreature.instance_id
    action: str                       # "action" | "bonus_action" | "reaction" | "reset"
    used: bool = True                 # 仅对单项操作有效；reset 时忽略此字段
    # 回显字段（服务器写回，方便前端直接用）
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False
    movement_used: int = 0


class LegendaryActionData(BaseModel):
    """DM 消耗或重置传奇动作点数。

    operation 取值：
      "use"   → 消耗 cost 点传奇动作（默认 1 点）
      "reset" → 重置为 0（通常由 TURN_ADVANCE 自动触发，DM 也可手动调用）

    广播给全员，前端更新传奇动作点数显示。
    """
    encounter_map_id: str
    instance_id: str              # MapCreature.instance_id
    operation: str = "use"        # "use" | "reset"
    cost: int = 1                 # 消耗点数（use 时有效；部分传奇动作消耗 2-3 点）
    action_name: str = ""         # 可选，记录用了哪个传奇动作（仅用于日志展示）
    # 回显字段
    legendary_actions_used: int = 0
    legendary_actions_max: int = 0


# ---- 通用豁免检定（P1）----

class SavingThrowData(BaseModel):
    """DM 对单个目标发起豁免检定。
    目标可以是玩家角色（target_character_id）或地图生物（target_instance_id），二选一。
    服务器投骰、算伤害，广播 SAVING_THROW_RESULT。
    """
    encounter_map_id: str

    # 目标（二选一）
    target_character_id: str = ""      # 玩家角色 CharacterSheet.id
    target_instance_id:  str = ""      # 地图生物 MapCreature.instance_id

    # 豁免属性
    ability: str = "dexterity"         # strength / dexterity / constitution / intelligence / wisdom / charisma

    # 难度等级
    dc: int = 14

    # 伤害参数（不填则仅做检定，不扣血）
    damage_dice: str = ""              # 如 "8d6"；空串 = 只检定
    damage_type: str = ""              # 如 "fire" | "cold" | "poison"
    half_on_success: bool = True       # True = 成功减半（火球术等）；False = 成功无伤

    description: str = ""              # 效果来源说明，用于聊天栏显示，如 "火球术"


class SavingThrowResultData(BaseModel):
    """豁免检定结果广播"""
    encounter_map_id: str

    target_character_id: str = ""
    target_instance_id:  str = ""
    target_name: str = ""

    ability: str = ""
    dc: int = 0
    roll: int = 0          # d20 原始值
    bonus: int = 0         # 属性修正 + 熟练（若有）
    total: int = 0         # roll + bonus
    success: bool = False

    damage_rolled: int = 0  # 伤害骰原始值（命中/豁免失败前）
    damage_applied: int = 0 # 实际扣除的伤害（已考虑减半/免疫/抗性）
    damage_type: str = ""
    hp_before: int = 0
    hp_after: int = 0
    target_is_down: bool = False

    description: str = ""
    roll_breakdown: str = ""


# ---- AoE 伤害自动分发（P1）----

class AoeAttackData(BaseModel):
    """DM 发起范围攻击（火球术、灼热射线等）。
    前端可先调用 GET .../spell-area 获得范围内生物列表，
    再将 instance_id / character_id 传入此消息，服务器一次性完成所有豁免和伤害分发。

    伤害骰只投一次（D&D 5e 规则），每个目标独立投豁免。
    """
    encounter_map_id: str

    # 目标列表（前端从 spell-area 响应中 creatures_in_area 提取）
    target_instance_ids:  list[str] = Field(default_factory=list)   # 地图生物
    target_character_ids: list[str] = Field(default_factory=list)   # 玩家角色

    # 豁免参数
    ability: str = "dexterity"    # 豁免属性
    dc: int = 14                  # 难度等级

    # 伤害参数
    damage_dice: str = "8d6"      # 伤害骰表达式
    damage_type: str = "fire"     # 伤害类型
    half_on_success: bool = True  # True = 豁免成功受一半伤害

    description: str = ""         # 如 "火球术（8d6 火焰）"


class AoeAttackResultData(BaseModel):
    """AoE 攻击结果汇总广播"""
    encounter_map_id: str
    description: str = ""

    # 检定参数回显
    ability: str = ""
    dc: int = 0
    damage_dice: str = ""
    damage_rolled: int = 0   # 伤害骰投出的原始值（所有目标共享）
    damage_type: str = ""

    # 各目标详细结果
    results: list[dict[str, Any]] = Field(default_factory=list)

    # 汇总统计
    total_targets: int = 0
    successes: int = 0       # 豁免成功人数
    failures: int = 0        # 豁免失败人数
    total_damage_dealt: int = 0   # 本次 AoE 总计伤害


# ---- 先攻自动投骰（P1）----

class RollInitiativeData(BaseModel):
    """DM 一键为棋盘上所有生物投先攻（1d20 + DEX 修正）。
    服务器完成投骰 + 排序后，自动广播 INITIATIVE_UPDATE 更新先攻列表。
    """
    encounter_map_id: str
    reroll_players: bool = False   # True = 同时重掷已有先攻值的玩家角色
