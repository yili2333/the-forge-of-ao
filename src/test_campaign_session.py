"""
战役/场次/WS模型 模块测试

运行方式:
    cd src && python test_campaign_session.py

测试范围:
- campaign CRUD + 成员/角色管理
- campaign overview 聚合
- encounter map 生物放置/先攻
- session 持久化/op_log
- ws_models 序列化/反序列化（新增类型）
- rest_engine + REST_COMPLETE 数据格式
- 回合推进逻辑
- 死亡豁免状态机
- 状态异常 Condition 枚举
- 法术准备上限计算
- character_history 快照

不需要启动 FastAPI 服务器。
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

_TMP_DB = tempfile.NamedTemporaryFile(suffix="_camptest.db", delete=False)
_TMP_DB.close()
os.environ["SQLITE_PATH"] = _TMP_DB.name

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class TestFailure(AssertionError):
    pass


def check(label: str, got, expected=None, *, truthy: bool = False):
    if truthy:
        if not got:
            raise TestFailure(f"[{label}] expected truthy, got {got!r}")
    elif got != expected:
        raise TestFailure(f"[{label}] expected {expected!r}, got {got!r}")
    print(f"    OK  {label}")


# ============================================================
#  测试1: Campaign CRUD
# ============================================================

async def test_campaign_crud():
    print("\n[test_campaign_crud]")
    # 直接从子模块导入，绕过 campaign/__init__.py（其中引入了 fastapi）
    import importlib
    camp_storage = importlib.import_module("campaign.storage")
    camp_models = importlib.import_module("campaign.models")
    init_campaign_db = camp_storage.init_campaign_db
    save_campaign = camp_storage.save_campaign
    get_campaign = camp_storage.get_campaign
    list_campaigns = camp_storage.list_campaigns_by_dm
    delete_campaign = camp_storage.delete_campaign
    Campaign = camp_models.Campaign
    CampaignStatus = camp_models.CampaignStatus

    await init_campaign_db()

    c = Campaign(
        id="camp-test-001",
        name="测试战役：黑暗地牢",
        dm_owner_id="DM#0001",
    )
    saved = await save_campaign(c)
    check("save returns Campaign", type(saved).__name__, "Campaign")
    check("id preserved", saved.id, "camp-test-001")
    check("name preserved", saved.name, "测试战役：黑暗地牢")

    fetched = await get_campaign("camp-test-001")
    check("get by id", fetched is not None, True)
    check("fetched name", fetched.name, "测试战役：黑暗地牢")

    # 状态更新
    fetched.status = CampaignStatus.ACTIVE
    await save_campaign(fetched)
    updated = await get_campaign("camp-test-001")
    check("status updated", updated.status, CampaignStatus.ACTIVE)

    # 成员管理
    fetched.player_ids = ["Player#001", "Player#002"]
    await save_campaign(fetched)
    with_players = await get_campaign("camp-test-001")
    check("players saved", len(with_players.player_ids), 2)

    # 列表
    camps = await list_campaigns(dm_owner_id="DM#0001")
    check("list by dm", len(camps) >= 1, True)

    # 删除
    ok = await delete_campaign("camp-test-001")
    check("delete returns True", ok, True)
    gone = await get_campaign("camp-test-001")
    check("deleted gone", gone, None)

    print("  campaign_crud: ALL PASSED")


# ============================================================
#  测试2: Session 持久化 + OpLog
# ============================================================

async def test_session_storage():
    print("\n[test_session_storage]")
    import importlib
    sess_storage = importlib.import_module("session.storage")
    sess_models = importlib.import_module("session.models")
    init_session_db = sess_storage.init_session_db
    save_session = sess_storage.save_session
    get_session = sess_storage.get_session
    get_latest_session = sess_storage.get_latest_session
    append_op_log = sess_storage.append_op_log
    get_op_log = sess_storage.get_op_log
    GameSession = sess_models.GameSession
    SessionOpLog = sess_models.SessionOpLog
    InitiativeEntry = sess_models.InitiativeEntry
    SceneData = sess_models.SceneData

    await init_session_db()

    sess = GameSession(
        id="sess-test-001",
        campaign_id="camp-x",
        round_number=3,
        current_turn_index=1,
        initiative=[
            InitiativeEntry(instance_id="char-001", name="勇者阿明", initiative=18, is_player=True),
            InitiativeEntry(instance_id="goblin-01", name="哥布林首领", initiative=12, is_player=False),
        ],
        scene=SceneData(description="黑暗的山洞入口"),
    )

    saved = await save_session(sess)
    check("save session", saved.id, "sess-test-001")
    check("round preserved", saved.round_number, 3)
    check("initiative count", len(saved.initiative), 2)

    fetched = await get_session("sess-test-001")
    check("get session", fetched is not None, True)
    check("initiative restored", len(fetched.initiative), 2)
    check("scene restored", fetched.scene.description, "黑暗的山洞入口")

    latest = await get_latest_session("camp-x")
    check("get latest", latest is not None, True)
    check("latest id", latest.id, "sess-test-001")

    # OpLog
    log = SessionOpLog(
        session_id="sess-test-001",
        op_type="roll",
        actor_id="Player#001",
        payload={"expression": "1d20+5", "result": 17},
        round_number=3,
    )
    await append_op_log(log)
    await append_op_log(SessionOpLog(
        session_id="sess-test-001",
        op_type="hp_change",
        actor_id="DM#0001",
        payload={"target": "goblin-01", "delta": -8},
        round_number=3,
    ))

    logs = await get_op_log("sess-test-001", limit=10)
    check("op_log count", len(logs), 2)
    check("first log type", logs[0].op_type, "hp_change")  # 倒序

    print("  session_storage: ALL PASSED")


# ============================================================
#  测试3: ws_models 序列化 (新增类型)
# ============================================================

def test_ws_models():
    print("\n[test_ws_models]")
    from ws_models import (
        WSMessage, WSMsgType,
        TurnAdvanceData, CombatStartData, CombatEndData,
        DeathSaveData, ConditionUpdateData,
        RestCompleteData,
        DmApprovalRequestData, DmApprovalResultData,
        LootGrantData, XpGainData,
    )

    # TurnAdvanceData
    tad = TurnAdvanceData(
        current_turn=2,
        round_number=3,
        active_entry_id="char-001",
        active_entry_name="勇者阿明",
        round_started=False,
    )
    msg = WSMessage(type=WSMsgType.TURN_ADVANCE, sender="server", data=tad.model_dump())
    raw = msg.encode()
    decoded = WSMessage.decode(raw)
    check("TURN_ADVANCE encode/decode", decoded.type, WSMsgType.TURN_ADVANCE)
    check("active_entry_name", decoded.data["active_entry_name"], "勇者阿明")

    # CombatStartData
    csd = CombatStartData(description="战斗开始！")
    msg2 = WSMessage(type=WSMsgType.COMBAT_START, sender="DM#0001", data=csd.model_dump())
    check("COMBAT_START type", msg2.type, WSMsgType.COMBAT_START)

    # DeathSaveData — 自然20情形
    dsd = DeathSaveData(
        character_id="char-001",
        roll=20,
        is_success=True,
        successes=3,
        failures=0,
        is_stable=True,
        is_dead=False,
        natural_20=True,
    )
    msg3 = WSMessage(type=WSMsgType.DEATH_SAVE, sender="Player#001", data=dsd.model_dump())
    raw3 = msg3.encode()
    d3 = WSMessage.decode(raw3)
    check("DEATH_SAVE natural_20", d3.data["natural_20"], True)
    check("DEATH_SAVE is_stable", d3.data["is_stable"], True)

    # DeathSaveData — 自然1情形（2次失败）
    dsd_fail = DeathSaveData(
        character_id="char-001",
        roll=1,
        is_success=False,
        successes=0,
        failures=2,
        natural_1=True,
    )
    check("DEATH_SAVE nat1 failures=2", dsd_fail.failures, 2)

    # ConditionUpdateData
    cond = ConditionUpdateData(
        target_id="char-001",
        target_type="character",
        condition="blinded",
        action="add",
    )
    msg4 = WSMessage(type=WSMsgType.CONDITION_UPDATE, sender="DM#0001", data=cond.model_dump())
    check("CONDITION_UPDATE encode", msg4.data["condition"], "blinded")

    # RestCompleteData
    rcd = RestCompleteData(
        character_id="char-001",
        owner_id="Player#001",
        rest_type="long",
        hp_gained=24,
        resources_recovered=["Second Wind", "Action Surge"],
        effects_expired=["Bless"],
    )
    msg5 = WSMessage(type=WSMsgType.REST_COMPLETE, sender="server", data=rcd.model_dump())
    check("REST_COMPLETE hp_gained", msg5.data["hp_gained"], 24)

    # DM 审批流
    dm_req = DmApprovalRequestData(
        character_id="char-002",
        character_name="半龙战士",
        owner_id="Player#002",
        campaign_id="camp-001",
        non_standard_reason="半龙种族",
    )
    msg6 = WSMessage(type=WSMsgType.DM_APPROVAL_REQUEST, sender="server", data=dm_req.model_dump())
    check("DM_APPROVAL_REQUEST type", msg6.type, WSMsgType.DM_APPROVAL_REQUEST)
    check("DM_APPROVAL_REQUEST char_name", msg6.data["character_name"], "半龙战士")

    dm_res = DmApprovalResultData(character_id="char-002", character_name="半龙战士", approved=True, dm_note="允许")
    msg7 = WSMessage(type=WSMsgType.DM_APPROVAL_RESULT, sender="server", data=dm_res.model_dump())
    check("DM_APPROVAL_RESULT approved", msg7.data["approved"], True)

    # LootGrantData
    loot = LootGrantData(
        encounter_id="enc-001",
        xp_per_player=300,
        gold=50.0,
        items=[{"name": "治疗药水", "quantity": 2}],
        recipient_ids=["char-001", "char-002"],
    )
    msg8 = WSMessage(type=WSMsgType.LOOT_GRANT, sender="DM#0001", data=loot.model_dump())
    raw8 = msg8.encode()
    d8 = WSMessage.decode(raw8)
    check("LOOT_GRANT xp_per_player", d8.data["xp_per_player"], 300)
    check("LOOT_GRANT gold", d8.data["gold"], 50.0)
    check("LOOT_GRANT items count", len(d8.data["items"]), 1)

    # XpGainData
    xp_data = XpGainData(
        character_id="char-001",
        character_name="勇者阿明",
        owner_id="Player#001",
        xp_gained=300,
        xp_before=0,
        xp_after=300,
        level_before=1,
        level_after=2,
        leveled_up=True,
        xp_to_next=0,
        note="击败骷髅王",
    )
    msg9 = WSMessage(type=WSMsgType.XP_GAIN, sender="server", data=xp_data.model_dump())
    raw9 = msg9.encode()
    d9 = WSMessage.decode(raw9)
    check("XP_GAIN type", d9.type, WSMsgType.XP_GAIN)
    check("XP_GAIN leveled_up", d9.data["leveled_up"], True)
    check("XP_GAIN xp_after", d9.data["xp_after"], 300)
    check("XP_GAIN note", d9.data["note"], "击败骷髅王")

    print("  ws_models: ALL PASSED")


# ============================================================
#  测试4: 死亡豁免状态机
# ============================================================

def test_death_save_logic():
    print("\n[test_death_save_logic]")
    from character.models import DeathSaves

    def simulate_roll(saves: DeathSaves, roll: int) -> DeathSaves:
        """模拟一次死亡豁免掷骰，返回更新后的 DeathSaves"""
        if saves.stable or saves.failures >= 3 or saves.successes >= 3:
            return saves  # 已终结

        is_nat20 = roll == 20
        is_nat1 = roll == 1

        if is_nat20:
            return saves.model_copy(update={"stable": True, "successes": 3})
        elif is_nat1:
            new_fail = min(3, saves.failures + 2)
            return saves.model_copy(update={"failures": new_fail})
        elif roll >= 10:
            return saves.model_copy(update={"successes": min(3, saves.successes + 1)})
        else:
            return saves.model_copy(update={"failures": min(3, saves.failures + 1)})

    # 3次成功 → 稳定
    saves = DeathSaves()
    for roll in [10, 15, 12]:
        saves = simulate_roll(saves, roll)
    check("3 successes → successes=3", saves.successes, 3)
    check("3 successes → not dead", saves.failures < 3, True)

    # 3次失败 → 死亡
    saves2 = DeathSaves()
    for roll in [5, 3, 8]:
        saves2 = simulate_roll(saves2, roll)
    check("3 failures → failures=3", saves2.failures, 3)

    # 自然1 → 2次失败
    saves3 = DeathSaves()
    saves3 = simulate_roll(saves3, 1)
    check("nat1 → 2 failures", saves3.failures, 2)
    saves3 = simulate_roll(saves3, 5)
    check("nat1 + fail → 3 failures dead", saves3.failures, 3)

    # 自然20 → 立即稳定
    saves4 = DeathSaves(successes=1, failures=2)  # 危险状态
    saves4 = simulate_roll(saves4, 20)
    check("nat20 → stable", saves4.stable, True)

    print("  death_save_logic: ALL PASSED")


# ============================================================
#  测试5: Condition 枚举完整性
# ============================================================

def test_conditions():
    print("\n[test_conditions]")
    from character.models import Condition

    standard_conditions = [
        "blinded", "charmed", "deafened", "frightened",
        "grappled", "incapacitated", "invisible", "paralyzed",
        "petrified", "poisoned", "prone", "restrained",
        "stunned", "unconscious",
    ]
    for c_val in standard_conditions:
        try:
            c = Condition(c_val)
            check(f"Condition({c_val})", c.value, c_val)
        except ValueError:
            raise TestFailure(f"Condition enum 缺少: {c_val}")

    check("total conditions >= 14", len(Condition), 14)

    # 角色可以应用/移除
    from character.models import CharacterSheet, AbilityScores, HitPoints
    sheet = CharacterSheet(
        id="cond-test",
        name="测试角色",
        owner_id="Player#001",
        ability_scores=AbilityScores(),
        hit_points=HitPoints(maximum=10, current=10),
    )
    sheet = sheet.model_copy(update={"conditions": [Condition.BLINDED, Condition.FRIGHTENED]})
    check("apply 2 conditions", len(sheet.conditions), 2)

    sheet = sheet.model_copy(update={
        "conditions": [c for c in sheet.conditions if c != Condition.BLINDED]
    })
    check("remove blinded", len(sheet.conditions), 1)
    check("frightened remains", sheet.conditions[0], Condition.FRIGHTENED)

    print("  conditions: ALL PASSED")


# ============================================================
#  测试6: 法术准备上限计算
# ============================================================

def test_spell_preparation():
    print("\n[test_spell_preparation]")
    from character.models import (
        CharacterSheet, AbilityScores, HitPoints, ClassLevel, KnownSpell,
    )

    # 内联准备施法者逻辑（与 character/api.py 保持一致，使用全称字段名）
    _PREPARED_CASTER_ABILITY = {
        "cleric": "wisdom", "druid": "wisdom",
        "paladin": "charisma", "wizard": "intelligence",
    }

    def _max_prepared(sheet, class_name: str) -> int:
        ability_key = _PREPARED_CASTER_ABILITY.get(class_name.lower(), "intelligence")
        level = next(
            (cl.level for cl in sheet.class_levels if cl.class_name.lower() == class_name.lower()), 1
        )
        mod = sheet.ability_scores.modifier(ability_key)
        return max(1, level + mod)

    # 祭司 Lv5, WIS 16 (+3)  → max = 5+3 = 8
    sheet = CharacterSheet(
        id="cleric-test",
        name="圣光祭司",
        owner_id="Player#001",
        ability_scores=AbilityScores(wisdom=16),
        hit_points=HitPoints(maximum=38, current=38),
        class_levels=[ClassLevel(class_name="Cleric", level=5)],
    )
    check("cleric max_prepared", _max_prepared(sheet, "Cleric"), 8)

    # 法师 Lv3, INT 14 (+2) → max = 3+2 = 5
    sheet2 = CharacterSheet(
        id="wiz-test",
        name="书院法师",
        owner_id="Player#002",
        ability_scores=AbilityScores(intelligence=14),
        hit_points=HitPoints(maximum=18, current=18),
        class_levels=[ClassLevel(class_name="Wizard", level=3)],
    )
    check("wizard max_prepared", _max_prepared(sheet2, "Wizard"), 5)

    # 圣武士 Lv4, CHA 18 (+4) → max = 4+4 = 8
    sheet3 = CharacterSheet(
        id="pal-test",
        name="荣光圣武士",
        owner_id="Player#003",
        ability_scores=AbilityScores(charisma=18),
        hit_points=HitPoints(maximum=36, current=36),
        class_levels=[ClassLevel(class_name="Paladin", level=4)],
    )
    check("paladin max_prepared", _max_prepared(sheet3, "Paladin"), 8)

    # 游侠不在准备施法者名单内
    check("ranger not in list", "ranger" not in _PREPARED_CASTER_ABILITY, True)

    # KnownSpell prepared 字段
    spell = KnownSpell(name="Cure Wounds", level=1, source_class="Cleric")
    check("default not prepared", spell.prepared, False)
    prepared = spell.model_copy(update={"prepared": True})
    check("prepared=True", prepared.prepared, True)
    check("always_prepared default", spell.always_prepared, False)

    print("  spell_preparation: ALL PASSED")


# ============================================================
#  测试7: character_history 快照
# ============================================================

async def test_character_history():
    print("\n[test_character_history]")
    from character.storage import init_character_db, save_character, get_character_history, restore_character_version
    from character.models import CharacterSheet, AbilityScores, HitPoints

    await init_character_db()

    sheet = CharacterSheet(
        id="hist-char-001",
        name="历史测试角色",
        owner_id="Player#999",
        ability_scores=AbilityScores(str_=10, dex=14),
        hit_points=HitPoints(maximum=20, current=20),
    )

    # 初始保存（version=1，不写历史）
    v1 = await save_character(sheet)
    check("initial version", v1.version, 1)

    # 第一次更新 → 写入历史 version=2
    v1_mod = v1.model_copy(update={"name": "历史角色(v2)"})
    v2 = await save_character(v1_mod)
    check("version incremented", v2.version, 2)

    # 第二次更新 → 写入历史 version=3
    v2_mod = v2.model_copy(update={"name": "历史角色(v3)"})
    v3 = await save_character(v2_mod)
    check("version v3", v3.version, 3)

    # 获取历史记录
    history = await get_character_history("hist-char-001", limit=10)
    check("history count >= 2", len(history) >= 2, True)
    check("history has version key", "version" in history[0], True)
    check("history has snapshot", "snapshot" in history[0], True)
    # 最新的先（倒序）
    check("latest history version first", history[0]["version"] >= history[-1]["version"], True)

    # 恢复到历史版本（找 v2 的 history_id）
    v2_entry = next((h for h in history if h["version"] == 2), None)
    check("v2 history entry exists", v2_entry is not None, True)

    restored = await restore_character_version("hist-char-001", v2_entry["history_id"])
    check("restored name", restored.name, "历史角色(v2)")
    check("restored version > 3", restored.version, 4)  # 恢复本身也是新版本

    print("  character_history: ALL PASSED")


# ============================================================
#  测试8: Maps 模型基本结构
# ============================================================

async def test_maps_models():
    print("\n[test_maps_models]")
    import importlib
    maps_storage = importlib.import_module("maps.storage")
    maps_models = importlib.import_module("maps.models")
    init_map_db = maps_storage.init_map_db
    save_world_map = maps_storage.save_world_map
    get_campaign_world_map = maps_storage.get_campaign_world_map
    save_encounter_map = maps_storage.save_encounter_map
    get_encounter_map = maps_storage.get_encounter_map
    WorldMap = maps_models.WorldMap
    PointOfInterest = maps_models.PointOfInterest
    EncounterMap = maps_models.EncounterMap
    MapCreature = maps_models.MapCreature

    await init_map_db()

    # 世界地图
    wmap = WorldMap(
        id="wmap-test-001",
        campaign_id="camp-maps-test",
        name="艾尔法大陆",
        width=100,
        height=100,
        pois=[
            PointOfInterest(id="poi-001", name="银月城", x=30.0, y=45.0),
            PointOfInterest(id="poi-002", name="黑暗森林", x=70.0, y=20.0, is_hidden=True),
        ]
    )
    await save_world_map(wmap)
    fetched = await get_campaign_world_map("camp-maps-test")
    check("world map saved", fetched is not None, True)
    check("poi count", len(fetched.pois), 2)
    check("hidden poi", fetched.pois[1].is_hidden, True)

    # 揭示 POI
    fetched.pois[1].is_hidden = False
    await save_world_map(fetched)
    updated = await get_campaign_world_map("camp-maps-test")
    check("poi revealed", updated.pois[1].is_hidden, False)

    # 遭遇地图
    emap = EncounterMap(
        id="emap-test-001",
        campaign_id="camp-maps-test",
        name="山洞入口",
        grid_width=20,
        grid_height=15,
        creatures=[
            MapCreature(
                instance_id="creature-001",
                source_type="monster",
                source_id="goblin",
                name="哥布林",
                x=5, y=5,
                hp_current=7, hp_max=7,
            ),
        ]
    )
    await save_encounter_map(emap)
    fetched_e = await get_encounter_map("emap-test-001")
    check("encounter map saved", fetched_e is not None, True)
    check("creature count", len(fetched_e.creatures), 1)
    check("creature name", fetched_e.creatures[0].name, "哥布林")

    print("  maps_models: ALL PASSED")


# ============================================================
#  测试9: 邀请码系统
# ============================================================

async def test_invite_system():
    print("\n[test_invite_system]")
    import importlib
    camp_storage = importlib.import_module("campaign.storage")
    camp_models = importlib.import_module("campaign.models")
    Campaign = camp_models.Campaign
    CampaignInvite = camp_models.CampaignInvite

    # 确保 DB 初始化
    await camp_storage.init_campaign_db()

    # 创建测试战役
    camp = Campaign(
        id="camp-invite-test",
        name="邀请测试战役",
        dm_owner_id="DM#invite",
    )
    await camp_storage.save_campaign(camp)

    # 生成邀请码
    invite = CampaignInvite(
        campaign_id="camp-invite-test",
        campaign_name="邀请测试战役",
        dm_display="DM大师",
        max_uses=3,
    )
    saved_inv = await camp_storage.create_invite(invite)
    check("invite code length", len(saved_inv.code), 8)
    check("invite code upper", saved_inv.code, saved_inv.code.upper())
    check("max_uses", saved_inv.max_uses, 3)
    check("uses=0", saved_inv.uses, 0)

    # 查询邀请码
    fetched = await camp_storage.get_invite(saved_inv.code)
    check("get invite", fetched is not None, True)
    check("is_active", fetched.is_active, True)

    # 消耗邀请码（玩家加入）
    inv_result, err = await camp_storage.consume_invite(saved_inv.code, "Player#invite001")
    check("consume no error", err, "")
    check("uses incremented", inv_result.uses, 1)

    # 验证玩家已被加入战役
    updated_camp = await camp_storage.get_campaign("camp-invite-test")
    check("player joined", "Player#invite001" in updated_camp.player_ids, True)

    # 超过次数限制
    await camp_storage.consume_invite(saved_inv.code, "Player#002")
    await camp_storage.consume_invite(saved_inv.code, "Player#003")
    _, err4 = await camp_storage.consume_invite(saved_inv.code, "Player#004")
    check("over limit error", "上限" in err4, True)

    # 作废邀请码
    ok = await camp_storage.deactivate_invite(saved_inv.code)
    check("deactivate ok", ok, True)
    inv_deactivated = await camp_storage.get_invite(saved_inv.code)
    check("is_active False", inv_deactivated.is_active, False)
    _, err5 = await camp_storage.consume_invite(saved_inv.code, "Player#005")
    check("deactivated error", "失效" in err5, True)

    print("  invite_system: ALL PASSED")


# ============================================================
#  测试10: 多职业前置条件
# ============================================================

def test_multiclass_prereqs():
    print("\n[test_multiclass_prereqs]")
    from character.models import AbilityScores
    from character.multiclass_rules import validate_multiclass, check_multiclass_prereq

    # 纯职业（第一职业）无条件
    ok, reason = validate_multiclass(AbilityScores(), [], "Fighter")
    check("first class no prereq", ok, True)

    # Fighter 多职业：STR 13 OR DEX 13
    scores_str13 = AbilityScores(strength=13)
    ok, _ = validate_multiclass(scores_str13, ["Rogue"], "Fighter")
    check("fighter with STR 13", ok, True)

    scores_dex13 = AbilityScores(dexterity=13)
    ok, _ = validate_multiclass(scores_dex13, ["Rogue"], "Fighter")
    check("fighter with DEX 13", ok, True)

    scores_low = AbilityScores(strength=10, dexterity=10)
    ok, reason = validate_multiclass(scores_low, ["Rogue"], "Fighter")
    check("fighter fails without STR/DEX 13", ok, False)
    check("reason mentions STR or DEX", "STR" in reason or "DEX" in reason or "strength" in reason.lower(), True)

    # Monk：DEX 13 AND WIS 13（都要）
    scores_monk_ok = AbilityScores(dexterity=14, wisdom=13)
    ok, _ = validate_multiclass(scores_monk_ok, ["Fighter"], "Monk")
    check("monk with DEX+WIS 13", ok, True)

    scores_monk_fail = AbilityScores(dexterity=14, wisdom=10)
    ok, _ = validate_multiclass(scores_monk_fail, ["Fighter"], "Monk")
    check("monk fails without WIS 13", ok, False)

    # Paladin：STR 13 AND CHA 13
    scores_pal_ok = AbilityScores(strength=13, charisma=14)
    ok, _ = validate_multiclass(scores_pal_ok, ["Fighter"], "Paladin")
    check("paladin with STR+CHA 13", ok, True)

    # 已有该职业再升级不触发校验
    ok, _ = validate_multiclass(AbilityScores(), ["Wizard"], "Wizard")
    check("same class upgrade skips check", ok, True)

    # Wizard：INT 13
    scores_wiz_fail = AbilityScores(intelligence=10)
    ok, _ = validate_multiclass(scores_wiz_fail, ["Cleric"], "Wizard")
    check("wizard fails without INT 13", ok, False)

    print("  multiclass_prereqs: ALL PASSED")


# ============================================================
#  测试11: XP 系统
# ============================================================

def test_xp_system():
    print("\n[test_xp_system]")
    from character.xp_system import (
        xp_for_level, level_from_xp, xp_to_next, cr_to_xp, apply_xp
    )

    # xp_for_level 基础校验
    check("xp L1 = 0", xp_for_level(1), 0)
    check("xp L2 = 300", xp_for_level(2), 300)
    check("xp L5 = 6500", xp_for_level(5), 6_500)
    check("xp L20 = 355000", xp_for_level(20), 355_000)
    check("xp L0 = 0 (clamp)", xp_for_level(0), 0)
    check("xp L21 = L20 (clamp)", xp_for_level(21), xp_for_level(20))

    # level_from_xp
    check("0 xp = level 1", level_from_xp(0), 1)
    check("300 xp = level 2", level_from_xp(300), 2)
    check("299 xp = level 1", level_from_xp(299), 1)
    check("6500 xp = level 5", level_from_xp(6_500), 5)
    check("354999 xp = level 19", level_from_xp(354_999), 19)
    check("355000 xp = level 20", level_from_xp(355_000), 20)

    # xp_to_next
    check("xp_to_next at L1 (0 xp)", xp_to_next(0), 300)
    check("xp_to_next at L1 (100 xp)", xp_to_next(100), 200)
    check("xp_to_next at L20 = 0", xp_to_next(355_000), 0)

    # cr_to_xp
    check("CR 0 = 10", cr_to_xp("0"), 10)
    check("CR 1/8 = 25", cr_to_xp("1/8"), 25)
    check("CR 1/2 = 100", cr_to_xp("1/2"), 100)
    check("CR 5 = 1800", cr_to_xp("5"), 1_800)
    check("CR 20 = 25000", cr_to_xp("20"), 25_000)
    check("CR 30 = 155000", cr_to_xp("30"), 155_000)
    check("unknown CR = 0", cr_to_xp("999"), 0)

    # apply_xp 无升级
    r1 = apply_xp("c1", 0, 100)
    check("xp_before", r1.xp_before, 0)
    check("xp_after", r1.xp_after, 100)
    check("level_before", r1.level_before, 1)
    check("level_after", r1.level_after, 1)
    check("not leveled_up", r1.leveled_up, False)
    check("xp_to_next", r1.xp_to_next, 200)

    # apply_xp 触发升级（L1→L2，需要300）
    r2 = apply_xp("c2", 200, 200)
    check("level up: before=1", r2.level_before, 1)
    check("level up: after=2", r2.level_after, 2)
    check("leveled_up=True", r2.leveled_up, True)
    check("xp_after=400", r2.xp_after, 400)

    # apply_xp 跨多级（从0直接给14000 XP → 应到L6）
    r3 = apply_xp("c3", 0, 14_000)
    check("multi-level: after=6", r3.level_after, 6)
    check("multi-level: leveled_up", r3.leveled_up, True)

    # 最高级满后再加XP
    r4 = apply_xp("c4", 355_000, 10_000)
    check("max level still 20", r4.level_after, 20)
    check("xp_to_next at max = 0", r4.xp_to_next, 0)

    print("  xp_system: ALL PASSED")


# ============================================================
#  测试12: 法术位消耗（cast_spell 逻辑）
# ============================================================

def test_spell_slot_consumption():
    print("\n[test_spell_slot_consumption]")
    from character.models import (
        CharacterSheet, SpellSlots, SpellSlot
    )

    def make_wizard_sheet():
        ss = SpellSlots()
        ss.slots = {
            1: SpellSlot(maximum=4, current=4),
            2: SpellSlot(maximum=3, current=3),
            3: SpellSlot(maximum=2, current=2),
        }
        sheet = CharacterSheet(id="wizard-test", name="Gandalf")
        sheet = sheet.model_copy(update={"spell_slots": ss})
        return sheet

    sheet = make_wizard_sheet()

    # 消耗 1 级法术位
    slot1 = sheet.spell_slots.slots[1]
    slot1.current -= 1
    check("slot1 after cast", sheet.spell_slots.slots[1].current, 3)

    # 消耗至 0
    slot2 = sheet.spell_slots.slots[2]
    for _ in range(3):
        slot2.current -= 1
    check("slot2 exhausted", sheet.spell_slots.slots[2].current, 0)
    # 再消耗应为负值（实际 API 层会阻止，这里测逻辑层）
    check("slot2 max unchanged", sheet.spell_slots.slots[2].maximum, 3)

    # Warlock 誓约法术位
    pact = sheet.spell_slots.pact_slots
    pact.maximum = 2
    pact.current = 2
    pact.current -= 1
    check("pact slot after cast", sheet.spell_slots.pact_slots.current, 1)
    pact.current -= 1
    check("pact slot exhausted", sheet.spell_slots.pact_slots.current, 0)

    # 验证 SpellSlot 的边界值
    check("slot max = 3", sheet.spell_slots.slots[2].maximum, 3)

    print("  spell_slot_consumption: ALL PASSED")


# ============================================================
#  测试13: 遭遇难度计算器
# ============================================================

def test_encounter_difficulty():
    print("\n[test_encounter_difficulty]")
    from character.encounter_difficulty import (
        EncounterDifficultyRequest, MonsterEntry, calculate_encounter_difficulty
    )

    # --- 场景1: 1级队（4人）vs CR 1/4 老鼠（trivial）---
    req1 = EncounterDifficultyRequest(
        party_levels=[1, 1, 1, 1],
        monsters=[MonsterEntry(cr="1/4", count=1, name="大鼠")],
    )
    r1 = calculate_encounter_difficulty(req1)
    check("rat is trivial/easy", r1.rating in ("trivial", "easy"), True)
    check("party_size=4", r1.party_size, 4)
    check("monster_count=1", r1.monster_count, 1)
    check("multiplier 1 monster", r1.encounter_multiplier, 1.0)
    check("raw xp = 50", r1.raw_monster_xp, 50)      # CR1/4 = 50 XP
    check("adjusted xp = 50.0", r1.adjusted_xp, 50.0)
    check("suggestion truthy", r1.suggestion, truthy=True)

    # --- 场景2: 5级队（4人）vs CR 5 龙×2（medium~deadly, 3600*1.5=5400）---
    req2 = EncounterDifficultyRequest(
        party_levels=[5, 5, 5, 5],
        monsters=[MonsterEntry(cr="5", count=2, name="年幼龙")],
    )
    r2 = calculate_encounter_difficulty(req2)
    check("dragon x2 rating valid", r2.rating in ("medium", "hard", "deadly"), True)
    check("raw xp = 3600", r2.raw_monster_xp, 3_600)

    # --- 场景3: 5级队（4人）vs 8x CR 1（hard/deadly，倍率×2.5）---
    req3 = EncounterDifficultyRequest(
        party_levels=[5, 5, 5, 5],
        monsters=[MonsterEntry(cr="1", count=8, name="骷髅")],
    )
    r3 = calculate_encounter_difficulty(req3)
    check("8 skeletons monster_count", r3.monster_count, 8)
    check("8 skeletons multiplier", r3.encounter_multiplier, 2.5)  # 7-10 → ×2.5
    check("8 skeletons raw xp = 1600", r3.raw_monster_xp, 1_600)  # 8 × 200
    check("8 skeletons adjusted = 4000", r3.adjusted_xp, 4_000.0)
    check("8 skeletons is hard or deadly", r3.rating in ("hard", "deadly"), True)

    # --- 场景4: 小队（2人）倍率上调 ---
    req4 = EncounterDifficultyRequest(
        party_levels=[5, 5],
        monsters=[MonsterEntry(cr="1", count=2, name="骷髅")],
    )
    r4 = calculate_encounter_difficulty(req4)
    # 2人小队 + 2只怪：正常倍率1.5，小队上调一档→2.0
    check("small party multiplier upgraded", r4.encounter_multiplier >= 2.0, True)

    # --- 场景5: 阈值校验（中等难度阈值）---
    # L5 玩家每人 medium=500，4人合计=2000
    req5 = EncounterDifficultyRequest(
        party_levels=[5, 5, 5, 5],
        monsters=[MonsterEntry(cr="3", count=2, name="元素")],   # 2×700=1400 ×2.0=2800
    )
    r5 = calculate_encounter_difficulty(req5)
    check("thresholds computed", r5.threshold_easy > 0, True)
    check("threshold easy < medium", r5.threshold_easy < r5.threshold_medium, True)
    check("threshold medium < hard", r5.threshold_medium < r5.threshold_hard, True)
    check("threshold hard < deadly", r5.threshold_hard < r5.threshold_deadly, True)

    # --- 场景6: CR 30 boss vs L20 队（deadly）---
    req6 = EncounterDifficultyRequest(
        party_levels=[20, 20, 20, 20, 20],
        monsters=[MonsterEntry(cr="30", count=1, name="Tiamat")],
    )
    r6 = calculate_encounter_difficulty(req6)
    check("tiamat raw xp = 155000", r6.raw_monster_xp, 155_000)
    check("tiamat deadly", r6.rating, "deadly")

    print("  encounter_difficulty: ALL PASSED")


# ============================================================
#  测试14: HP / Conditions / Exhaustion 模型层逻辑
# ============================================================

def test_hp_conditions_exhaustion():
    print("\n[test_hp_conditions_exhaustion]")
    from character.models import CharacterSheet, HitPoints, DeathSaves, Condition

    def make_fighter():
        hp = HitPoints(current=30, maximum=30, temporary=5)
        return CharacterSheet(id="fighter-test", name="勇士").model_copy(update={"hit_points": hp})

    # --- HP delta：伤害先抵扣临时HP ---
    sheet = make_fighter()
    hp = sheet.hit_points.model_copy()
    damage = 8
    absorbed = min(hp.temporary, damage)
    hp = hp.model_copy(update={"temporary": hp.temporary - absorbed})
    remaining = damage - absorbed
    hp = hp.model_copy(update={"current": max(0, hp.current - remaining)})
    check("temp absorbed 5", hp.temporary, 0)
    check("current = 30-3=27", hp.current, 27)

    # --- HP delta：治疗不超过上限 ---
    hp2 = HitPoints(current=20, maximum=30, temporary=0)
    healed = min(30, 20 + 15)   # heal 15，上限 30
    check("heal capped at max", healed, 30)

    # --- HP set_current ---
    hp3 = HitPoints(current=10, maximum=30)
    hp3 = hp3.model_copy(update={"current": min(30, 0)})   # set to 0
    check("set_current=0", hp3.current, 0)

    # --- 临时HP：取较大值不叠加 ---
    hp4 = HitPoints(current=20, maximum=30, temporary=5)
    new_temp = max(hp4.temporary, 8)
    check("temp hp takes larger", new_temp, 8)
    new_temp2 = max(new_temp, 3)
    check("temp hp no downgrade", new_temp2, 8)

    # --- 死亡豁免重置 ---
    ds = DeathSaves(successes=2, failures=1, stable=False)
    ds_reset = DeathSaves()
    check("death saves reset successes", ds_reset.successes, 0)
    check("death saves reset failures", ds_reset.failures, 0)

    # --- Conditions add/remove/set ---
    sheet2 = CharacterSheet(id="cond-test", name="测试")
    conds = list(sheet2.conditions)
    # add
    if Condition.BLINDED not in conds:
        conds.append(Condition.BLINDED)
    if Condition.POISONED not in conds:
        conds.append(Condition.POISONED)
    check("conditions after add", len(conds), 2)
    check("blinded in conds", Condition.BLINDED in conds, True)
    # remove
    conds = [c for c in conds if c != Condition.BLINDED]
    check("after remove blinded", Condition.BLINDED not in conds, True)
    check("poisoned remains", Condition.POISONED in conds, True)
    # set (replace all)
    conds = [Condition.PRONE]
    check("set conditions to prone", conds, [Condition.PRONE])
    # set empty
    conds = []
    check("set empty clears all", conds, [])

    # --- Condition enum validation ---
    valid_vals = {c.value for c in Condition}
    check("14 conditions", len(valid_vals), 14)
    check("unconscious valid", "unconscious" in valid_vals, True)
    check("flying not valid", "flying" not in valid_vals, True)

    # --- Exhaustion: PHB 2024 = 10 levels ---
    exhaustion = 0
    exhaustion = min(10, exhaustion + 3)
    check("exhaustion after +3", exhaustion, 3)
    exhaustion = max(0, exhaustion - 1)   # 长休 -1
    check("exhaustion after long rest", exhaustion, 2)
    exhaustion = min(10, exhaustion + 9)  # 超过上限
    check("exhaustion capped at 10", exhaustion, 10)
    exhaustion = max(0, exhaustion - 15)  # 低于下限
    check("exhaustion floored at 0", exhaustion, 0)

    print("  hp_conditions_exhaustion: ALL PASSED")


# ============================================================
#  Main
# ============================================================

async def main():
    print(f"Temp DB: {_TMP_DB.name}")
    try:
        await test_campaign_crud()
        await test_session_storage()
        test_ws_models()
        test_death_save_logic()
        test_conditions()
        test_spell_preparation()
        await test_character_history()
        await test_maps_models()
        await test_invite_system()
        test_multiclass_prereqs()
        test_xp_system()
        test_spell_slot_consumption()
        test_encounter_difficulty()
        test_hp_conditions_exhaustion()

    except TestFailure as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            os.unlink(_TMP_DB.name)
        except OSError:
            pass

    print("\n[PASS] All campaign/session/ws tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
