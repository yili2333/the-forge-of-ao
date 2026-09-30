"""
完整游玩流程集成测试 (TestClient 版本，无需运行服务器)
"""
import sys, io, os, asyncio, contextlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
os.environ["SQLITE_PATH"] = "dnd_rules_flowtest.db"

with contextlib.redirect_stderr(io.StringIO()):
    from fastapi.testclient import TestClient
    import main

# TestClient 必须作为 context manager 使用才能触发 lifespan（DB 初始化）
_client_ctx = TestClient(main.app, raise_server_exceptions=False)
_client_ctx.__enter__()
client = _client_ctx
IDS = {}
PASS = 0
FAIL = 0


def chk(label, r, expected=200):
    global PASS, FAIL
    ok = r.status_code == expected
    if ok:
        PASS += 1
        print(f"  OK   [{r.status_code}] {label}")
    else:
        FAIL += 1
        print(f"  FAIL [{r.status_code}] {label}: {r.text[:250]}")
    try:
        return r.json(), ok
    except Exception:
        return r.text, ok


print("\n--- Phase 1: 建角色 ---")
r = client.post("/api/character",
    headers={"X-Owner-Id": "P#001", "X-Owner-Display": "Player1"},
    json={
        "name": "铁拳·斯通", "owner_id": "P#001", "edition": "2024",
        "build_method": "standard_array",
        "ability_scores": {"strength": 16, "dexterity": 12, "constitution": 15,
                           "intelligence": 10, "wisdom": 13, "charisma": 8},
        "species": {"name": "Human"},
        "background": {"name": "Soldier"},
        "class_levels": [{"class_name": "Fighter", "level": 1, "hit_die_size": 10}],
        "hit_points": {"current": 12, "maximum": 12, "hit_die_size": 10, "hit_dice_total": 1},
        "speed": {"walk": 30},
        "saving_throws": {"proficient": ["strength", "constitution"]},
        "inventory": [{"name": "Chain Mail", "item_type": "armor",
                       "armor_category": "heavy", "armor_class_base": 16,
                       "equipped": True, "weight": 55.0}],
    })
b, ok = chk("POST /api/character", r)
if ok:
    IDS["char_id"] = b["id"]
    print(f"       char_id={IDS['char_id']}  HP={b['hit_points']['current']}/{b['hit_points']['maximum']}")


print("\n--- Phase 2: 建战役 ---")
r = client.post("/api/campaign",
    headers={"X-Owner-Id": "DM#001", "X-Role": "dm"},
    json={"name": "失落的矿坑", "dm_owner_id": "DM#001", "dm_display": "DM"})
b, ok = chk("POST /api/campaign", r)
if ok:
    IDS["camp_id"] = b["id"]
    print(f"       camp_id={IDS['camp_id']}")


print("\n--- Phase 3: 邀请码 + 玩家加入 ---")
if "camp_id" in IDS:
    r = client.post(f"/api/campaign/{IDS['camp_id']}/invite",
        headers={"X-Owner-Id": "DM#001", "X-Role": "dm"},
        json={"max_uses": 5})
    b, ok = chk("POST /api/campaign/{id}/invite", r)
    if ok:
        IDS["code"] = b["code"]
        print(f"       code={IDS['code']}")

    if "code" in IDS:
        r = client.post(f"/api/campaign/join/{IDS['code']}",
            headers={"X-Owner-Id": "P#001"}, json={})
        b, ok = chk("POST /api/campaign/join/{code}", r)

    if "char_id" in IDS:
        r = client.post(f"/api/campaign/{IDS['camp_id']}/characters/{IDS['char_id']}",
            headers={"X-Owner-Id": "DM#001", "X-Role": "dm"})
        b, ok = chk("POST /api/campaign/{id}/characters/{char_id}", r)


print("\n--- Phase 4: 大地图生成 + POI ---")
if "camp_id" in IDS:
    r = client.post(f"/api/campaign/{IDS['camp_id']}/world-map/generate",
        headers={"X-Role": "dm"},
        json={"prompt": "中世纪奇幻大陆森林山脉", "width_px": 256, "height_px": 256})
    b, ok = chk("POST /world-map/generate", r)
    if ok:
        print(f"       image={b.get('image_url')}")

    r = client.post(f"/api/campaign/{IDS['camp_id']}/world-map/poi",
        headers={"X-Role": "dm"},
        json={"id": "poi-mine", "name": "失落的矿坑", "x": 45.0, "y": 60.0,
              "poi_type": "dungeon", "description": "废弃矮人矿坑"})
    b, ok = chk("POST /world-map/poi", r)
    if ok:
        print(f"       pois={len(b.get('pois', []))}")


print("\n--- Phase 5: 怪物检索 ---")
r = client.get("/api/monsters", params={"q": "哥布林", "limit": 3})
b, ok = chk("GET /api/monsters?q=哥布林", r)
if ok and isinstance(b, dict):
    monsters = b.get("monsters", [])
    if monsters:
        IDS["monster_id"] = monsters[0]["id"]
        print(f"       {monsters[0].get('name_cn')} CR={monsters[0].get('cr')}  id={IDS['monster_id']}")
    else:
        print(f"       no results (total={b.get('total')})  body keys={list(b.keys())}")

if "monster_id" not in IDS:
    r = client.get("/api/monsters", params={"limit": 1})
    b, _ = chk("GET /api/monsters (fallback)", r)
    if isinstance(b, dict):
        monsters = b.get("monsters", [])
        if monsters:
            IDS["monster_id"] = monsters[0]["id"]
            print(f"       fallback: {monsters[0].get('name_cn')} id={IDS['monster_id']}")


print("\n--- Phase 6: 遭遇战地图 ---")
if "camp_id" in IDS:
    r = client.post(f"/api/campaign/{IDS['camp_id']}/encounter-maps",
        headers={"X-Role": "dm"},
        json={"campaign_id": IDS["camp_id"], "name": "矿坑入口",
              "grid_cols": 12, "grid_rows": 12, "cell_size_ft": 5})
    b, ok = chk("POST /encounter-maps", r)
    if ok:
        IDS["emap_id"] = b["id"]
        print(f"       emap_id={IDS['emap_id']}")

    if "emap_id" in IDS:
        r = client.post(
            f"/api/campaign/{IDS['camp_id']}/encounter-maps/{IDS['emap_id']}/generate-bg",
            headers={"X-Role": "dm"},
            json={"prompt": "地牢石墙昏暗火把"})
        b, ok = chk("POST /generate-bg", r)
        if ok:
            print(f"       bg={b.get('image_url')}")


print("\n--- Phase 7: 遭遇战模拟（放置生物 + 先攻）---")
if all(k in IDS for k in ["camp_id", "emap_id", "char_id"]):
    sim = {"player_character_ids": [IDS["char_id"]], "extra_monsters": []}
    if "monster_id" in IDS:
        sim["extra_monsters"] = [{"monster_id": IDS["monster_id"], "count": 2}]
    r = client.post(
        f"/api/campaign/{IDS['camp_id']}/encounter-maps/{IDS['emap_id']}/simulate",
        headers={"X-Role": "dm"}, json=sim)
    b, ok = chk("POST /simulate", r)
    if ok:
        creatures = b.get("creatures", [])
        print(f"       creatures={len(creatures)}")
        for c in creatures:
            print(f"         {c['name']}  @({c['x']},{c['y']})  HP={c['hp_current']}/{c['hp_max']}  init={c.get('initiative',0)}")


print("\n--- Phase 8: 升级到 Lv2 ---")
if "char_id" in IDS:
    r = client.post(f"/api/character/{IDS['char_id']}/level-up",
        headers={"X-Owner-Id": "P#001"},
        json={"class_name": "Fighter", "hp_method": "average"})
    b, ok = chk("POST /level-up (Fighter Lv2)", r)
    if ok:
        print(f"       level={b['class_levels'][0]['level']}  maxHP={b['hit_points']['maximum']}")


print("\n--- Phase 9: 背包 + 货币 ---")
if "char_id" in IDS:
    r = client.post(f"/api/character/{IDS['char_id']}/inventory",
        headers={"X-Owner-Id": "P#001"},
        json={"name": "治疗药水", "item_type": "consumable", "quantity": 2, "weight": 0.5, "cost_gp": 50})
    b, ok = chk("POST /inventory (治疗药水 x2)", r)
    if ok:
        p = next((i for i in b["inventory"] if i["name"] == "治疗药水"), None)
        if p:
            IDS["potion_id"] = p["id"]
            print(f"       qty={p['quantity']}")

    if "potion_id" in IDS:
        r = client.patch(f"/api/character/{IDS['char_id']}/inventory/{IDS['potion_id']}",
            headers={"X-Owner-Id": "P#001"}, json={"quantity": 1})
        b, ok = chk("PATCH /inventory (qty 2→1)", r)
        if ok:
            p = next((i for i in b["inventory"] if i["name"] == "治疗药水"), None)
            print(f"       qty after patch={p['quantity'] if p else '?'}")

    r = client.post(f"/api/character/{IDS['char_id']}/currency",
        headers={"X-Owner-Id": "P#001"}, json={"gold": 50.0, "silver": 20.0})
    b, ok = chk("POST /currency (+50gp +20sp)", r)
    if ok:
        print(f"       gold={b['gold']}  silver={b['silver']}")


print("\n--- Phase 10: 施加效果（Bless）+ HP 伤害 + 短休 ---")
if "char_id" in IDS:
    r = client.post(f"/api/character/{IDS['char_id']}/apply-effect",
        headers={"X-Owner-Id": "P#001"},
        json={"name": "Bless", "source": "spell:Bless",
              "attack_bonus": 2, "duration_type": "concentration", "concentration": True})
    b, ok = chk("POST /apply-effect (Bless)", r)
    if ok:
        print(f"       concentration_id={b.get('concentration_effect_id','')[:8]}")

    r = client.patch(f"/api/character/{IDS['char_id']}/hp",
        headers={"X-Owner-Id": "P#001"}, json={"delta": -8})
    b, ok = chk("PATCH /hp (damage -8)", r)
    if ok:
        print(f"       HP after damage={b['hit_points']['current']}/{b['hit_points']['maximum']}")

    r = client.post(f"/api/character/{IDS['char_id']}/short-rest",
        headers={"X-Owner-Id": "P#001"}, json={"hit_dice": ["d10"]})
    b, ok = chk("POST /short-rest (d10)", r)
    if ok:
        print(f"       gained={b['result']['hp_gained']}  HP={b['sheet']['hit_points']['current']}/{b['sheet']['hit_points']['maximum']}")


print("\n--- Phase 11: 版本历史 + 总览 + 角色快照 ---")
if "char_id" in IDS:
    r = client.get(f"/api/character/{IDS['char_id']}/history",
        headers={"X-Owner-Id": "P#001"})
    b, ok = chk("GET /history", r)
    if ok:
        print(f"       entries={len(b)}  latest_version={b[0]['version'] if b else 0}")

if "camp_id" in IDS:
    r = client.get(f"/api/campaign/{IDS['camp_id']}/overview",
        headers={"X-Owner-Id": "DM#001", "X-Role": "dm"})
    b, ok = chk("GET /overview", r)
    if ok:
        print(f"       campaign={b['campaign']['name']}")
        print(f"       characters={len(b.get('characters', []))}  "
              f"encounter_maps={len(b.get('encounter_maps', []))}  "
              f"monsters_in_play={len(b.get('monsters_in_play', []))}")

if "char_id" in IDS:
    r = client.get(f"/api/character/{IDS['char_id']}/summary")
    b, ok = chk("GET /summary (LLM context)", r)
    if ok:
        d = b.get("derived", {})
        print(f"       AC={d.get('ac')}  passive_perception={d.get('passive_perception')}")
        ctx = b.get("context_text", "")[:80]
        print(f"       context: {ctx}")


# 清理
try:
    _client_ctx.__exit__(None, None, None)
except Exception:
    pass
try:
    os.unlink("dnd_rules_flowtest.db")
except OSError:
    pass

print(f"\n{'='*52}")
print(f"  结果: {PASS} 通过 / {FAIL} 失败")
print(f"{'='*52}")
