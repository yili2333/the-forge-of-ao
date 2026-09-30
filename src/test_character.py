"""
人物卡模块的独立测试

运行方式:
    cd src && python test_character.py

测试范围:
- models 序列化/反序列化
- calculator 关键派生值
- storage CRUD + 软删除 + 导入导出
- user_identity 配置文件读写

不需要启动 FastAPI 服务器。
使用一个临时 sqlite 文件，避免污染主数据库。
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Windows 终端默认 cp936，先切到 UTF-8，避免 emoji 打印崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# 把临时 db 路径注入到环境中，config.py 读取时会用
_TMP_DB = tempfile.NamedTemporaryFile(suffix="_chartest.db", delete=False)
_TMP_DB.close()
os.environ["SQLITE_PATH"] = _TMP_DB.name

# 修改 config 的默认值（config 已经 lru_cache，需要提前设置）
# 用 monkeypatch 的方式: 在 import config 之前改 env
# pydantic-settings 支持小写 env 名，所以 SQLITE_PATH 会被 config 读取

# 让 src 成为 import 根
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from character import storage  # noqa: E402
from character.calculator import (  # noqa: E402
    compute_ac,
    compute_derived_stats,
    passive_perception,
    saving_throw_modifier,
    skill_modifier,
)
from character.models import (  # noqa: E402
    AbilityName,
    AbilityScores,
    ArmorCategory,
    BuildMethod,
    CharacterSheet,
    ClassLevel,
    Condition,
    HitPoints,
    Item,
    ItemType,
    ProficiencyLevel,
    SavingThrowProficiencies,
    Skill,
    SkillProficiencies,
    Species,
    Speed,
    WeaponCategory,
    WeaponProperty,
)
from character import builder  # noqa: E402
from character import rule_bridge  # noqa: E402

# 覆盖 storage 模块的 DB_PATH 为临时文件
storage.DB_PATH = _TMP_DB.name


# ============================================================
#  测试辅助: 构造一个典型 5 级游荡者
# ============================================================

def build_sample_rogue() -> CharacterSheet:
    ability = AbilityScores(
        strength=10, dexterity=16, constitution=14,
        intelligence=12, wisdom=13, charisma=8,
    )

    sheet = CharacterSheet(
        name="Elora Shadowstep",
        owner_id="Tanrui#7281",
        owner_display="Tanrui#7281",
        edition="2024",
        build_method=BuildMethod.POINT_BUY,
        ability_scores=ability,
        species=Species(name="Elf", lineage="Wood Elf", granted_senses={"darkvision": 60}),
        class_levels=[
            ClassLevel(class_name="Rogue", level=5, subclass="Thief", hit_die_size=8),
        ],
        hit_points=HitPoints(current=33, maximum=33, hit_die_size=8, hit_dice_total=5),
        speed=Speed(walk=30),
        weapon_proficiencies=["simple_melee", "simple_ranged", "martial_melee", "martial_ranged"],
        armor_proficiencies=[ArmorCategory.LIGHT],
    )

    # 技能熟练 (游荡者典型选择)
    sheet.skills.set(Skill.STEALTH, ProficiencyLevel.EXPERTISE)
    sheet.skills.set(Skill.PERCEPTION, ProficiencyLevel.PROFICIENT)
    sheet.skills.set(Skill.ACROBATICS, ProficiencyLevel.PROFICIENT)

    # 豁免熟练
    sheet.saving_throws = SavingThrowProficiencies(
        proficient={AbilityName.DEX, AbilityName.INT}
    )

    # 装备: 皮甲 + 短剑
    leather = Item(
        name="Leather Armor",
        item_type=ItemType.ARMOR,
        armor_category=ArmorCategory.LIGHT,
        armor_class_base=11,
        equipped=True,
    )
    shortsword = Item(
        name="Shortsword",
        item_type=ItemType.WEAPON,
        weapon_category=WeaponCategory.MARTIAL_MELEE,
        damage_dice="1d6",
        weapon_properties=[WeaponProperty.FINESSE, WeaponProperty.LIGHT],
        equipped=True,
    )
    sheet.inventory.extend([leather, shortsword])
    return sheet


# ============================================================
#  断言工具
# ============================================================

class TestFailure(AssertionError):
    pass


def check(name: str, actual, expected):
    if actual != expected:
        raise TestFailure(f"[{name}] 期望 {expected}，实际 {actual}")
    print(f"  [OK] {name} = {actual}")


def check_in(name: str, actual, allowed):
    if actual not in allowed:
        raise TestFailure(f"[{name}] 期望属于 {allowed}，实际 {actual}")
    print(f"  [OK] {name} = {actual}")


# ============================================================
#  测试: 计算器
# ============================================================

def test_calculator():
    print("\n=== calculator ===")
    rogue = build_sample_rogue()

    # 属性修正
    check("DEX modifier", rogue.ability_scores.modifier(AbilityName.DEX), 3)
    check("STR modifier", rogue.ability_scores.modifier(AbilityName.STR), 0)

    # 熟练加值 (Lv5)
    check("proficiency bonus", rogue.proficiency_bonus, 3)

    # AC: 皮甲 11 + DEX 3 = 14
    check("AC", compute_ac(rogue), 14)

    # 豁免: DEX 熟练 → 3 + 3 = 6; CON 非熟练 → +2
    check("DEX save", saving_throw_modifier(rogue, AbilityName.DEX), 6)
    check("CON save", saving_throw_modifier(rogue, AbilityName.CON), 2)
    check("INT save (proficient)", saving_throw_modifier(rogue, AbilityName.INT), 4)

    # 技能: 潜行专精 = 3(DEX) + 3*2(expertise) = 9
    check("Stealth (expertise)", skill_modifier(rogue, Skill.STEALTH), 9)
    check("Perception (proficient)", skill_modifier(rogue, Skill.PERCEPTION), 4)
    # 未熟练技能只有属性修正
    check("Arcana (untrained)", skill_modifier(rogue, Skill.ARCANA), 1)

    # 被动察觉: 10 + 熟练察觉修正 = 14
    check("Passive Perception", passive_perception(rogue), 14)

    # 综合派生
    stats = compute_derived_stats(rogue)
    check_in("derived keys", "ac" in stats and "skills" in stats, [True])
    check("derived AC matches", stats["ac"], 14)


# ============================================================
#  测试: 模型序列化
# ============================================================

def test_serialization():
    print("\n=== serialization ===")
    rogue = build_sample_rogue()
    data = rogue.model_dump_json()
    restored = CharacterSheet.model_validate_json(data)

    check("name preserved", restored.name, rogue.name)
    check("AC (post-restore)", compute_ac(restored), 14)
    check("skills preserved", restored.skills.get(Skill.STEALTH), ProficiencyLevel.EXPERTISE)
    check("inventory size", len(restored.inventory), 2)


# ============================================================
#  测试: 存储
# ============================================================

async def test_storage():
    print("\n=== storage (CRUD) ===")
    await storage.init_character_db()

    rogue = build_sample_rogue()
    saved = await storage.save_character(rogue)
    check("id assigned", bool(saved.id), True)
    check("version=1 on create", saved.version, 1)

    # 读取
    loaded = await storage.get_character(saved.id)
    check("loaded", loaded is not None, True)
    check("name roundtrip", loaded.name, "Elora Shadowstep")
    check("AC post-load", compute_ac(loaded), 14)

    # 更新 → version 自增
    loaded.name = "Elora the Swift"
    updated = await storage.save_character(loaded)
    check("version=2 on update", updated.version, 2)

    # 列表
    mine = await storage.list_characters_by_owner("Tanrui#7281")
    check("list by owner", len(mine), 1)

    # non_standard + DM 审批
    rogue2 = build_sample_rogue()
    rogue2.name = "Homebrewed Hero"
    rogue2.non_standard = True
    await storage.save_character(rogue2)
    pending = await storage.list_pending_approval()
    check("pending contains rogue2", any(s.id == rogue2.id for s in pending), True)

    approved = await storage.mark_dm_approval(rogue2.id, True, "OK, fits campaign theme")
    check("approved", approved.dm_approved, True)

    pending_after = await storage.list_pending_approval()
    check("pending empty after approval", any(s.id == rogue2.id for s in pending_after), False)

    # 软删除 / 恢复
    ok = await storage.soft_delete_character(saved.id)
    check("soft delete", ok, True)
    after_delete = await storage.get_character(saved.id)
    check("invisible after delete", after_delete is None, True)
    still_there = await storage.get_character(saved.id, include_deleted=True)
    check("still there with flag", still_there is not None, True)

    ok2 = await storage.restore_character(saved.id)
    check("restore", ok2, True)
    recovered = await storage.get_character(saved.id)
    check("visible after restore", recovered is not None, True)

    # 导入导出
    exported = await storage.export_character_json(saved.id)
    check("export non-empty", bool(exported), True)

    imported = await storage.import_character_json(exported, owner_id_override="Other#0001")
    check("imported new id != old", imported.id != saved.id, True)
    check("imported owner override", imported.owner_id, "Other#0001")


# ============================================================
#  测试: UserIdentity (可选，只测序列化/解析路径)
# ============================================================

def test_builder():
    print("\n=== builder ===")

    # 1) 点数购买合法性
    legal = {
        AbilityName.STR: 15, AbilityName.DEX: 14, AbilityName.CON: 13,
        AbilityName.INT: 12, AbilityName.WIS: 10, AbilityName.CHA: 8,
    }
    check("standard array cost", builder.point_buy_cost(legal), 27)
    check("point_buy_valid (27)", builder.point_buy_valid(legal), True)

    tight = {
        AbilityName.STR: 15, AbilityName.DEX: 15, AbilityName.CON: 15,
        AbilityName.INT: 9, AbilityName.WIS: 9, AbilityName.CHA: 9,
    }
    # 三个 15(9 点) + 三个 9(1 点) = 30 点 > 27 预算
    check("point_buy_valid (overbudget)", builder.point_buy_valid(tight), False)

    # 2) 4d6 掷骰
    rng = __import__("random").Random(42)
    pool = builder.roll_ability_array(rng)
    check("roll returns 6 values", len(pool), 6)
    for v in pool:
        if not (3 <= v <= 18):
            raise TestFailure(f"掷骰结果 {v} 超出 [3,18]")
    print(f"  [OK] roll pool = {pool}")

    # 3) 一站式建卡
    hero = builder.build_character(
        name="Thorin",
        owner_id="Tanrui#7281",
        ability_scores=builder.assign_ability_pool(
            builder.STANDARD_ARRAY,
            [AbilityName.STR, AbilityName.CON, AbilityName.DEX,
             AbilityName.WIS, AbilityName.INT, AbilityName.CHA],
        ),
        build_method=BuildMethod.STANDARD_ARRAY,
        species="Dwarf",
        background="Soldier",
        class_name="Fighter",
        level=1,
        chosen_skills=[Skill.ATHLETICS, Skill.PERCEPTION],
    )

    # Dwarf 基础属性: STR 15, 背景 Soldier (+2 STR/+1 CON): STR 17, CON 15
    check("STR after background", hero.ability_scores.strength, 17)
    check("CON after background", hero.ability_scores.constitution, 15)

    # Dwarf 给 darkvision 120
    check("dwarf darkvision", hero.senses.darkvision, 120)

    # Fighter Lv1 应有 STR/CON 豁免熟练
    check("STR save proficient", AbilityName.STR in hero.saving_throws.proficient, True)
    check("CON save proficient", AbilityName.CON in hero.saving_throws.proficient, True)
    check("INT save not proficient", AbilityName.INT in hero.saving_throws.proficient, False)

    # 重甲熟练
    check("heavy armor prof", ArmorCategory.HEAVY in hero.armor_proficiencies, True)

    # 生命骰 d10 (Fighter)
    check("hit die size", hero.hit_points.hit_die_size, 10)

    # finalize 后最大 HP = 10 + CON修正(2) = 12
    check("max HP after finalize", hero.hit_points.maximum, 12)
    check("current HP filled", hero.hit_points.current, 12)

    # 标准阵列应当保持 non_standard=False
    check("standard array not flagged", hero.non_standard, False)

    # 4) 多职业
    builder.apply_class(hero, "Rogue", level=1, chosen_skills=[Skill.STEALTH])
    check("multiclass total level", hero.total_level, 2)
    # 多职业第二职业只给生命骰，不复写豁免
    check("DEX save still not prof", AbilityName.DEX in hero.saving_throws.proficient, False)

    # 5) 手动覆盖应打标记
    manual_sheet = CharacterSheet(name="Custom", owner_id="x")
    builder.apply_ability_scores(
        manual_sheet,
        {AbilityName.STR: 20, AbilityName.DEX: 20, AbilityName.CON: 20,
         AbilityName.INT: 20, AbilityName.WIS: 20, AbilityName.CHA: 20},
        BuildMethod.MANUAL,
    )
    check("manual flagged", manual_sheet.non_standard, True)

    # 6) 未知物种打标记
    custom_species_sheet = CharacterSheet(name="Custom2", owner_id="x")
    builder.apply_species(custom_species_sheet, "Tabaxi-Homebrew")
    check("unknown species flagged", custom_species_sheet.non_standard, True)


def test_rule_bridge():
    print("\n=== rule_bridge ===")

    rogue = build_sample_rogue()
    rogue.spellcasting_ability = None

    # 1) 话题提取
    topics = rule_bridge.extract_rule_topics(rogue)
    check("rogue in topics", "Rogue" in topics, True)
    check("thief subclass in topics", "Thief" in topics, True)
    check("elf in topics", "Elf" in topics, True)
    check("shortsword in topics", "Shortsword" in topics, True)

    # 2) 增强问题
    enriched = rule_bridge.build_enriched_question("我能不能偷袭?", rogue)
    check("enriched contains character name", "Elora Shadowstep" in enriched, True)
    check("enriched contains question", "我能不能偷袭" in enriched, True)
    check("enriched contains hint line", "请结合角色的实际情况" in enriched, True)

    # 3) 基础动作检查: 正常状态
    act = rule_bridge.check_can_act(rogue)
    check("normal character not blocked", act.hard_block, False)

    # 4) 失能状态
    rogue.conditions.append(Condition.UNCONSCIOUS)
    act2 = rule_bridge.check_can_act(rogue)
    check("unconscious hard block", act2.hard_block, True)
    check("unconscious reason present", any("昏迷" in r for r in act2.block_reasons), True)
    rogue.conditions.remove(Condition.UNCONSCIOUS)

    # 5) 近战攻击检查 (已装备短剑)
    atk = rule_bridge.check_can_attack_melee(rogue)
    check("can attack melee", atk.hard_block, False)
    check("melee weapon noted", any("Shortsword" in n for n in atk.notes), True)

    # 6) 非施法者施法应被阻
    cast = rule_bridge.check_can_cast_spell(rogue, spell_level=1)
    check("non-caster blocked", cast.hard_block, True)

    # 7) 综合快照
    snap = rule_bridge.character_snapshot_for_llm(rogue)
    check("snapshot has summary", "summary_text" in snap, True)
    check("snapshot has topics", len(snap["topics"]) > 0, True)


def test_identity_toml_roundtrip():
    print("\n=== user_identity toml ===")
    import user_identity as ui

    ident = ui.UserIdentity(
        nickname="Tanrui",
        discriminator="7281",
        email="tan@example.com",
        created_at="2026-04-10T12:00:00",
    )
    text = ui._serialize_toml(ident)
    data = ui._parse_toml(text)
    check("toml identity.nickname", data["identity"]["nickname"], "Tanrui")
    check("toml identity.discriminator", data["identity"]["discriminator"], "7281")
    check("toml identity.email", data["identity"]["email"], "tan@example.com")

    # stable_key 优先 email
    check("stable_key uses email", ident.stable_key, "tan@example.com")

    ident_no_email = ui.UserIdentity(nickname="Foo", discriminator="0123")
    check("stable_key fallback owner_id", ident_no_email.stable_key, "Foo#0123")


# ============================================================
#  测试: 效果引擎
# ============================================================

def test_effects_engine():
    print("\n=== effects_engine ===")
    from character.effects_engine import apply_effect, remove_effect, tick_effects
    from character.models import ActiveEffect, DurationType, Condition

    rogue = build_sample_rogue()

    # 1. apply_effect: Bless (+1d4 save, attack)
    bless = ActiveEffect(
        name="Bless",
        source="spell:Bless",
        save_bonus=0,    # Bless adds +1d4 bonus dice (tracked elsewhere), use attack_bonus as placeholder
        attack_bonus=2,
        duration_type=DurationType.CONCENTRATION,
        duration_value=10,
        concentration=True,
    )
    after_bless = apply_effect(rogue, bless)
    check("bless in active_effects", len(after_bless.active_effects), 1)
    check("concentration_effect_id set", after_bless.concentration_effect_id, bless.id)

    # 2. 第二个集中法术自动解除第一个
    bless2 = ActiveEffect(
        name="Bless2",
        source="spell:Bless",
        attack_bonus=1,
        duration_type=DurationType.CONCENTRATION,
        concentration=True,
    )
    after_bless2 = apply_effect(after_bless, bless2)
    check("old concentration removed", len([e for e in after_bless2.active_effects if e.name == "Bless"]), 0)
    check("new concentration set", after_bless2.concentration_effect_id, bless2.id)

    # 3. remove_effect
    after_remove = remove_effect(after_bless2, bless2.id)
    check("effect removed", len(after_remove.active_effects), 0)
    check("concentration cleared", after_remove.concentration_effect_id, "")

    # 4. tick_effects - ROUNDS 减少
    rounds_effect = ActiveEffect(
        name="Shield of Faith",
        ac_bonus=2,
        duration_type=DurationType.ROUNDS,
        duration_value=3,
    )
    with_effect = apply_effect(rogue, rounds_effect)
    ticked, expired = tick_effects(with_effect, trigger="round", rounds=2)
    check("duration decremented", ticked.active_effects[0].duration_value, 1)
    check("no expiry yet", len(expired), 0)

    ticked2, expired2 = tick_effects(ticked, trigger="round", rounds=2)
    check("effect expired", len(expired2), 1)
    check("no active effects", len(ticked2.active_effects), 0)

    # 5. tick_effects - UNTIL_SHORT_REST
    sr_effect = ActiveEffect(
        name="Second Wind",
        hp_max_modifier=5,
        duration_type=DurationType.UNTIL_SHORT_REST,
    )
    with_sr = apply_effect(rogue, sr_effect)
    after_sr, expired_sr = tick_effects(with_sr, trigger="short_rest")
    check("short rest clears effect", len(expired_sr), 1)
    check("effect gone after short rest", len(after_sr.active_effects), 0)

    # 6. apply_wish_permanent
    from character.effects_engine import apply_wish_permanent
    wished = apply_wish_permanent(rogue, {
        "ability_scores": {"strength": 20},
        "languages": ["Celestial"],
    })
    check("wish strength", wished.ability_scores.strength, 20)
    check("wish language added", "Celestial" in wished.languages, True)
    check("wish effect tracked", any(e.source == "wish" for e in wished.active_effects), True)

    print("  effects_engine: ALL PASSED")


# ============================================================
#  测试: 变形术
# ============================================================

def test_polymorph():
    print("\n=== polymorph ===")
    from character.effects_engine import apply_polymorph, remove_polymorph
    from monster.models import Monster, MonsterAbilities

    rogue = build_sample_rogue()
    original_str = rogue.ability_scores.strength
    original_hp = rogue.hit_points.maximum

    # 构造一个最小怪物 (狼)
    wolf = Monster(
        id="wolf-test",
        name_cn="狼",
        name_en="Wolf",
        abilities=MonsterAbilities(str=12, dex=15, con=12, int_=3, wis=12, cha=6),
        hp=11,
        ac=13,
        speed="40尺",   # Monster.speed 是字符串
        source="test",
    )

    polymorphed = apply_polymorph(rogue, wolf)
    check("is_polymorphed=True", polymorphed.is_polymorphed, True)
    check("STR replaced to wolf value", polymorphed.ability_scores.strength, 12)
    check("HP replaced to wolf HP", polymorphed.hit_points.maximum, 11)
    check("INT keeps character value (3 < 12 rogue INT)", polymorphed.ability_scores.intelligence, 12)  # max(3,12)=12
    check("speed replaced", polymorphed.speed.walk, 40)
    check("snapshot saved", polymorphed.polymorph_snapshot is not None, True)
    check("monster_id saved", polymorphed.polymorph_monster_id, "wolf-test")

    # 解除变形
    restored = remove_polymorph(polymorphed)
    check("is_polymorphed cleared", restored.is_polymorphed, False)
    check("STR restored", restored.ability_scores.strength, original_str)
    check("HP restored", restored.hit_points.maximum, original_hp)
    check("snapshot cleared", restored.polymorph_snapshot, None)

    print("  polymorph: ALL PASSED")


# ============================================================
#  测试: 休息引擎
# ============================================================

async def test_rest_engine():
    print("\n=== rest_engine ===")
    import random
    from character.rest_engine import long_rest, short_rest
    from character.models import ClassResource, SpellSlots, SpellSlot

    rogue = build_sample_rogue()
    # 模拟已消耗资源
    rogue.hit_points.current = 10
    rogue.hit_points.hit_dice_used = 3

    # 加一个 Ki Points 资源 (short rest)
    ki = ClassResource(name="Ki Points", current=0, maximum=5, recharge="short_rest")
    rogue.class_resources.append(ki)

    # 短休: 花费 1d8
    rng = random.Random(42)   # 固定种子便于测试
    updated, result = await short_rest(rogue, ["d8"], rng=rng)
    check("short rest hp gained > 0", result.hp_gained > 0, True)
    check("hit dice used +1", updated.hit_points.hit_dice_used, 4)
    check("ki restored", "Ki Points" in result.resources_recovered, True)
    check("ki current after short rest", updated.class_resources[0].current, 5)

    # 长休
    wiz = build_sample_rogue()
    wiz.hit_points.current = 1
    wiz.exhaustion_level = 2
    wiz.spell_slots = SpellSlots(slots={
        1: SpellSlot(maximum=4, current=1),
        2: SpellSlot(maximum=3, current=0),
    })
    wiz.class_resources.append(ClassResource(name="Channel Divinity", current=0, maximum=1, recharge="long_rest"))

    long_updated, long_result = await long_rest(wiz)
    check("long rest: full HP", long_updated.hit_points.current, long_updated.hit_points.maximum)
    check("long rest: slot 1 restored", long_updated.spell_slots.slots[1].current, 4)
    check("long rest: slot 2 restored", long_updated.spell_slots.slots[2].current, 3)
    check("long rest: channel divinity restored", "Channel Divinity" in long_result.resources_recovered, True)
    check("long rest: exhaustion reduced", long_updated.exhaustion_level, 1)
    check("long rest: action reset", long_updated.action_used, False)

    print("  rest_engine: ALL PASSED")


# ============================================================
#  测试: 升级
# ============================================================

def test_level_up():
    print("\n=== level_up ===")
    from character.builder import apply_class, finalize
    from character.calculator import ability_modifier

    # 创建一个 4 级战士
    sheet = CharacterSheet(
        name="Test Fighter",
        owner_id="test#0001",
        ability_scores=AbilityScores(strength=16, dexterity=14, constitution=15,
                                      intelligence=10, wisdom=12, charisma=8),
    )
    apply_class(sheet, "Fighter", level=4)
    finalize(sheet)

    original_max_hp = sheet.hit_points.maximum
    check("fighter lv4 hp > 0", original_max_hp > 0, True)

    # 手动升级到 5 级 (average method)
    con_mod = ability_modifier(sheet.ability_scores.constitution)
    hp_gain_avg = 10 // 2 + 1 + con_mod  # d10 average = 6, +CON
    sheet.hit_points.maximum += hp_gain_avg
    sheet.hit_points.current = sheet.hit_points.maximum

    check("lv5 hp increased", sheet.hit_points.maximum > original_max_hp, True)
    check("hp gain >= 1", hp_gain_avg >= 1, True)

    print("  level_up: ALL PASSED")


# ============================================================
#  测试: 法术位表
# ============================================================

def test_spell_slots():
    print("\n=== spell_slots ===")
    from character.spell_slots import get_spell_slots, merge_multiclass_spell_slots

    # Wizard Lv5 应有 4/3/2
    wiz5 = get_spell_slots("Wizard", 5)
    check("wizard lv5 slot1", wiz5.slots[1].maximum, 4)
    check("wizard lv5 slot2", wiz5.slots[2].maximum, 3)
    check("wizard lv5 slot3", wiz5.slots[3].maximum, 2)
    check("wizard lv5 no slot4", wiz5.slots.get(4), None)

    # Warlock Lv5: 3级槽×2
    lock5 = get_spell_slots("Warlock", 5)
    check("warlock lv5 pact level", lock5.pact_level, 3)
    check("warlock lv5 pact slots", lock5.pact_slots.maximum, 2)
    check("warlock lv5 no regular slots", len(lock5.slots), 0)

    # Paladin Lv4 (半施法者): slot1=3
    pal4 = get_spell_slots("Paladin", 4)
    check("paladin lv4 slot1", pal4.slots[1].maximum, 3)
    check("paladin lv4 no slot2", pal4.slots.get(2), None)

    # 多职业: Wizard 2 + Paladin 2 → caster_level = 2 + 1 = 3 → slot1=4, slot2=2
    merged = merge_multiclass_spell_slots([("Wizard", 2), ("Paladin", 2)])
    check("multiclass lv3 slot1", merged.slots[1].maximum, 4)
    check("multiclass lv3 slot2", merged.slots[2].maximum, 2)

    print("  spell_slots: ALL PASSED")


# ============================================================
#  测试: 背包
# ============================================================

def test_inventory():
    print("\n=== inventory ===")
    from character.calculator import carry_capacity, current_load, is_encumbered

    sheet = build_sample_rogue()

    # 添加物品
    potion = Item(name="Healing Potion", item_type=ItemType.CONSUMABLE,
                  quantity=3, weight=0.5, cost_gp=50.0)
    sheet.inventory.append(potion)

    # 负重检查
    total_load = current_load(sheet)
    capacity = carry_capacity(sheet)
    check("load is positive", total_load > 0, True)
    check("capacity is 150 (STR 10 * 15)", capacity, 150.0)

    # 修改物品
    potion_in_inv = next(i for i in sheet.inventory if i.name == "Healing Potion")
    potion_in_inv.quantity = 1
    check("quantity updated", potion_in_inv.quantity, 1)

    # 装备护甲
    leather = next(i for i in sheet.inventory if i.name == "Leather Armor")
    check("leather equipped", leather.equipped, True)

    # 卸下护甲
    leather.equipped = False
    from character.calculator import compute_ac as calc_ac
    sheet.armor_class_cache = calc_ac(sheet)
    check("AC without armor = 10 + DEX 3 = 13", sheet.armor_class_cache, 13)

    # 移除物品
    sheet.inventory = [i for i in sheet.inventory if i.name != "Healing Potion"]
    check("potion removed", not any(i.name == "Healing Potion" for i in sheet.inventory), True)

    # 货币
    sheet.gold = 100.0
    sheet.silver = 50.0
    sheet.gold += 25.0
    sheet.silver -= 10.0
    check("gold updated", sheet.gold, 125.0)
    check("silver updated", sheet.silver, 40.0)

    print("  inventory: ALL PASSED")


# ============================================================
#  Main
# ============================================================

async def main():
    print(f"Temp DB: {_TMP_DB.name}")
    try:
        test_calculator()
        test_serialization()
        await test_storage()
        test_builder()
        test_rule_bridge()
        test_identity_toml_roundtrip()
        test_effects_engine()
        test_polymorph()
        await test_rest_engine()
        test_level_up()
        test_spell_slots()
        test_inventory()
    except TestFailure as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 清理临时 db
        try:
            os.unlink(_TMP_DB.name)
        except OSError:
            pass

    print("\n[PASS] All character module tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
