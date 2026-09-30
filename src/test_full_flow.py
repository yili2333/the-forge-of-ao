"""
完整游玩流程集成测试
从建卡 → 拉房 → 大地图 → 遭遇战地图 → 战斗 → 休息
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "http://localhost:8765"
PASS = 0; FAIL = 0
IDS = {}   # 存储跨步骤需要的 ID

def ok(label, val=None):
    global PASS
    PASS += 1
    print(f"  [OK]  {label}" + (f" = {val}" if val is not None else ""))

def fail(label, detail=""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {label}: {detail}")

def call(method, path, *, headers=None, json_body=None, params=None, label=""):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    r = requests.request(method, BASE + path, headers=h, json=json_body, params=params, timeout=30)
    return r

def show(r, label):
    status = r.status_code
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]
    if status >= 400:
        fail(label, f"HTTP {status}: {json.dumps(body, ensure_ascii=False)[:400]}")
    else:
        ok(label, f"HTTP {status}")
    return body, status < 400

# ══════════════════════════════════════════════
print("\n━━━ Phase 1: 玩家建卡 ━━━")
# ══════════════════════════════════════════════
char_body = {
    "name": "铁拳·斯通",
    "owner_id": "TestPlayer#0001",
    "owner_display": "TestPlayer",
    "edition": "2024",
    "build_method": "standard_array",
    "ability_scores": {
        "strength": 16, "dexterity": 12, "constitution": 15,
        "intelligence": 10, "wisdom": 13, "charisma": 8
    },
    "species": {"name": "Human"},
    "background": {"name": "Soldier"},
    "class_levels": [{"class_name": "Fighter", "level": 1, "hit_die_size": 10}],
    "hit_points": {"current": 12, "maximum": 12, "hit_die_size": 10, "hit_dice_total": 1},
    "speed": {"walk": 30},
    "armor_proficiencies": ["light", "medium", "heavy", "shield"],
    "weapon_proficiencies": ["simple_melee", "simple_ranged", "martial_melee", "martial_ranged"],
    "saving_throws": {"proficient": ["strength", "constitution"]},
    "inventory": [
        {
            "name": "Chain Mail",
            "item_type": "armor",
            "armor_category": "heavy",
            "armor_class_base": 16,
            "equipped": True,
            "weight": 55.0
        }
    ]
}
r = call("POST", "/api/character",
         headers={"X-Owner-Id": "TestPlayer#0001", "X-Owner-Display": "TestPlayer"},
         json_body=char_body)
body, success = show(r, "POST /api/character")
if success:
    IDS["char_id"] = body["id"]
    ok("  character_id", IDS["char_id"])
    ok("  HP", f"{body['hit_points']['current']}/{body['hit_points']['maximum']}")

# ══════════════════════════════════════════════
print("\n━━━ Phase 2: DM 建立战役 ━━━")
# ══════════════════════════════════════════════
r = call("POST", "/api/campaign",
         headers={"X-Owner-Id": "DM#0001", "X-Role": "dm"},
         json_body={"name": "失落的矿坑", "dm_owner_id": "DM#0001", "dm_display": "DM"})
body, success = show(r, "POST /api/campaign")
if success:
    IDS["camp_id"] = body["id"]
    ok("  campaign_id", IDS["camp_id"])

# ══════════════════════════════════════════════
print("\n━━━ Phase 3: 邀请码 + 玩家加入 ━━━")
# ══════════════════════════════════════════════
if "camp_id" in IDS:
    r = call("POST", f"/api/campaign/{IDS['camp_id']}/invite",
             headers={"X-Owner-Id": "DM#0001", "X-Role": "dm"},
             json_body={"max_uses": 5})
    body, success = show(r, "POST /api/campaign/{id}/invite")
    if success:
        IDS["invite_code"] = body["code"]
        ok("  invite_code", IDS["invite_code"])

    if "invite_code" in IDS:
        r = call("POST", f"/api/campaign/join/{IDS['invite_code']}",
                 headers={"X-Owner-Id": "TestPlayer#0001"},
                 json_body={})
        body, success = show(r, "POST /api/campaign/join/{code}")

    # 将角色关联到战役
    if "char_id" in IDS:
        r = call("POST", f"/api/campaign/{IDS['camp_id']}/characters/{IDS['char_id']}",
                 headers={"X-Owner-Id": "DM#0001", "X-Role": "dm"})
        body, success = show(r, "POST /api/campaign/{id}/characters/{char_id}")

# ══════════════════════════════════════════════
print("\n━━━ Phase 4: 大地图生成 + POI ━━━")
# ══════════════════════════════════════════════
if "camp_id" in IDS:
    r = call("POST", f"/api/campaign/{IDS['camp_id']}/world-map/generate",
             headers={"X-Role": "dm"},
             json_body={"prompt": "中世纪奇幻大陆，森林山脉和古矿坑", "width_px": 256, "height_px": 256})
    body, success = show(r, "POST /api/campaign/{id}/world-map/generate")
    if success:
        IDS["world_map_id"] = body["id"]
        ok("  world_map image", body.get("image_url", "N/A"))

    r = call("POST", f"/api/campaign/{IDS['camp_id']}/world-map/poi",
             headers={"X-Role": "dm"},
             json_body={
                 "id": "poi-mine-001",
                 "name": "失落的矿坑",
                 "x": 45.0, "y": 60.0,
                 "poi_type": "dungeon",
                 "description": "废弃的矮人矿坑，现在住着地精"
             })
    body, success = show(r, "POST /api/campaign/{id}/world-map/poi")
    if success:
        poi_count = len(body.get("pois", []))
        ok(f"  POI count", poi_count)

# ══════════════════════════════════════════════
print("\n━━━ Phase 5: 规则查询 ━━━")
# ══════════════════════════════════════════════
r = call("POST", "/api/query",
         json_body={"question": "战士的额外攻击特性在什么等级获得"})
body, success = show(r, "POST /api/query")
if success:
    answer_preview = body.get("answer", "")[:120].replace("\n", " ")
    ok("  answer preview", answer_preview + "...")
    ok("  confidence", body.get("confidence"))
    ok("  chunks_used", body.get("chunks_used"))

# ══════════════════════════════════════════════
print("\n━━━ Phase 6: 怪物检索 ━━━")
# ══════════════════════════════════════════════
r = call("GET", "/api/monsters", params={"q": "地精", "limit": 3})
body, success = show(r, "GET /api/monsters?q=地精")
goblin_id = None
if success and isinstance(body, dict):
    monsters = body.get("monsters", body.get("items", []))
    if monsters:
        goblin_id = monsters[0]["id"]
        ok("  first monster", f"{monsters[0].get('name_cn')} (CR {monsters[0].get('cr')}) id={goblin_id}")
    else:
        # 尝试直接列出
        fail("  no monsters returned", str(body)[:100])

# 备用：搜索任意怪物
if not goblin_id:
    r = call("GET", "/api/monsters", params={"limit": 1})
    body, _ = show(r, "GET /api/monsters (fallback)")
    if isinstance(body, dict):
        monsters = body.get("monsters", body.get("items", []))
        if monsters:
            goblin_id = monsters[0]["id"]
            ok("  fallback monster", f"{monsters[0].get('name_cn')} id={goblin_id}")

IDS["goblin_id"] = goblin_id

# ══════════════════════════════════════════════
print("\n━━━ Phase 7: 遭遇战地图 ━━━")
# ══════════════════════════════════════════════
if "camp_id" in IDS:
    r = call("POST", f"/api/campaign/{IDS['camp_id']}/encounter-maps",
             headers={"X-Role": "dm"},
             json_body={
                 "campaign_id": IDS["camp_id"],
                 "name": "矿坑入口",
                 "grid_cols": 12,
                 "grid_rows": 12,
                 "cell_size_ft": 5
             })
    body, success = show(r, "POST /api/campaign/{id}/encounter-maps")
    if success:
        IDS["emap_id"] = body["id"]
        ok("  encounter_map_id", IDS["emap_id"])

    if "emap_id" in IDS:
        r = call("POST", f"/api/campaign/{IDS['camp_id']}/encounter-maps/{IDS['emap_id']}/generate-bg",
                 headers={"X-Role": "dm"},
                 json_body={"prompt": "地牢矿坑入口，石墙昏暗火把"})
        body, success = show(r, "POST .../generate-bg")
        if success:
            ok("  bg image_url", body.get("image_url", "N/A"))

# ══════════════════════════════════════════════
print("\n━━━ Phase 8: 遭遇战模拟（放置生物 + 先攻）━━━")
# ══════════════════════════════════════════════
if "camp_id" in IDS and "emap_id" in IDS and "char_id" in IDS:
    sim_body = {
        "player_character_ids": [IDS["char_id"]],
        "extra_monsters": []
    }
    if IDS.get("goblin_id"):
        sim_body["extra_monsters"] = [{"monster_id": IDS["goblin_id"], "count": 2}]

    r = call("POST", f"/api/campaign/{IDS['camp_id']}/encounter-maps/{IDS['emap_id']}/simulate",
             headers={"X-Role": "dm"},
             json_body=sim_body)
    body, success = show(r, "POST .../simulate")
    if success:
        creatures = body.get("creatures", [])
        ok("  creatures placed", len(creatures))
        for c in creatures:
            ok(f"    {c['name']} @ ({c['x']},{c['y']}) HP={c['hp_current']}/{c['hp_max']}")

# ══════════════════════════════════════════════
print("\n━━━ Phase 9: 角色升级 ━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("POST", f"/api/character/{IDS['char_id']}/level-up",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={"class_name": "Fighter", "hp_method": "average"})
    body, success = show(r, "POST /api/character/{id}/level-up")
    if success:
        cls = body["class_levels"][0]
        ok("  new level", cls["level"])
        ok("  new max HP", body["hit_points"]["maximum"])

# ══════════════════════════════════════════════
print("\n━━━ Phase 10: 背包操作 ━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("POST", f"/api/character/{IDS['char_id']}/inventory",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={"name": "治疗药水", "item_type": "consumable", "quantity": 2, "weight": 0.5, "cost_gp": 50})
    body, success = show(r, "POST /api/character/{id}/inventory (add potion)")
    if success:
        potion = next((i for i in body["inventory"] if i["name"] == "治疗药水"), None)
        if potion:
            ok("  potion added, qty", potion["quantity"])
            IDS["potion_id"] = potion["id"]

    # 修改数量
    if "potion_id" in IDS:
        r = call("PATCH", f"/api/character/{IDS['char_id']}/inventory/{IDS['potion_id']}",
                 headers={"X-Owner-Id": "TestPlayer#0001"},
                 json_body={"quantity": 1})
        body, success = show(r, "PATCH .../inventory/{id} (quantity=1)")
        if success:
            potion = next((i for i in body["inventory"] if i["name"] == "治疗药水"), None)
            ok("  quantity after patch", potion["quantity"] if potion else "N/A")

    # 货币增加
    r = call("POST", f"/api/character/{IDS['char_id']}/currency",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={"gold": 50.0, "silver": 10.0})
    body, success = show(r, "POST .../currency (+50gp +10sp)")
    if success:
        ok("  gold", body["gold"])

# ══════════════════════════════════════════════
print("\n━━━ Phase 11: 施加效果（Bless）━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("POST", f"/api/character/{IDS['char_id']}/apply-effect",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={
                 "name": "Bless",
                 "source": "spell:Bless",
                 "attack_bonus": 2,
                 "duration_type": "concentration",
                 "concentration": True
             })
    body, success = show(r, "POST .../apply-effect (Bless)")
    if success:
        effects = body.get("active_effects", [])
        bless = next((e for e in effects if e["name"] == "Bless"), None)
        ok("  Bless active", bless is not None)
        ok("  concentration_effect_id", body.get("concentration_effect_id", "")[:8])

# ══════════════════════════════════════════════
print("\n━━━ Phase 12: HP 伤害 → 短休 ━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("PATCH", f"/api/character/{IDS['char_id']}/hp",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={"delta": -8})
    body, success = show(r, "PATCH .../hp (delta=-8, simulating damage)")
    if success:
        ok("  HP after damage", f"{body['hit_points']['current']}/{body['hit_points']['maximum']}")

    r = call("POST", f"/api/character/{IDS['char_id']}/short-rest",
             headers={"X-Owner-Id": "TestPlayer#0001"},
             json_body={"hit_dice": ["d10"]})
    body, success = show(r, "POST .../short-rest (spend 1d10)")
    if success:
        ok("  hp_gained", body["result"]["hp_gained"])
        ok("  HP after rest", f"{body['sheet']['hit_points']['current']}/{body['sheet']['hit_points']['maximum']}")

# ══════════════════════════════════════════════
print("\n━━━ Phase 13: 版本历史 ━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("GET", f"/api/character/{IDS['char_id']}/history",
             headers={"X-Owner-Id": "TestPlayer#0001"})
    body, success = show(r, "GET .../history")
    if success:
        ok("  history entries", len(body))
        if body:
            ok("  latest version", body[0]["version"])

# ══════════════════════════════════════════════
print("\n━━━ Phase 14: 战役总览 ━━━")
# ══════════════════════════════════════════════
if "camp_id" in IDS:
    r = call("GET", f"/api/campaign/{IDS['camp_id']}/overview",
             headers={"X-Owner-Id": "DM#0001", "X-Role": "dm"})
    body, success = show(r, "GET /api/campaign/{id}/overview")
    if success:
        ok("  campaign name", body["campaign"]["name"])
        ok("  characters count", len(body.get("characters", [])))
        ok("  encounter_maps count", len(body.get("encounter_maps", [])))
        monsters_in_play = body.get("monsters_in_play", [])
        ok("  monsters_in_play", len(monsters_in_play))
        if monsters_in_play:
            m = monsters_in_play[0]
            ok(f"    {m['name']} @ ({m['x']},{m['y']}) HP={m['hp_current']}/{m['hp_max']}")

# ══════════════════════════════════════════════
print("\n━━━ Phase 15: 角色快照（LLM 用）━━━")
# ══════════════════════════════════════════════
if "char_id" in IDS:
    r = call("GET", f"/api/character/{IDS['char_id']}/summary")
    body, success = show(r, "GET .../summary")
    if success:
        derived = body.get("derived", {})
        ok("  AC", derived.get("ac"))
        ok("  passive_perception", derived.get("passive_perception"))
        context_text = body.get("context_text", "")[:100]
        ok("  context_text preview", context_text)

# ══════════════════════════════════════════════
print(f"\n{'═'*50}")
print(f"  结果：{PASS} 通过 / {FAIL} 失败")
print(f"{'═'*50}")
