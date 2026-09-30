"""
怪物持久化层

表名：monsters
数据库：与 rule_chunks 共用（由 config 指定）
支持 SQLite 和 MySQL 双后端（通过 db_helper）
"""
from __future__ import annotations

import json
from datetime import datetime

from db_helper import async_conn, IS_MYSQL, PH

from monster.models import Monster, MonsterAction, MonsterAbilities, MonsterSummary


_CREATE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS monsters (
    id                      TEXT PRIMARY KEY,
    name_cn                 TEXT NOT NULL,
    name_en                 TEXT DEFAULT '',
    size                    TEXT DEFAULT '',
    creature_type           TEXT DEFAULT '',
    subtype                 TEXT DEFAULT '',
    alignment               TEXT DEFAULT '',
    ac                      INTEGER DEFAULT 10,
    ac_note                 TEXT DEFAULT '',
    hp                      INTEGER DEFAULT 0,
    hp_formula              TEXT DEFAULT '',
    speed                   TEXT DEFAULT '',
    initiative_bonus        INTEGER DEFAULT 0,
    str                     INTEGER DEFAULT 10,
    dex                     INTEGER DEFAULT 10,
    con                     INTEGER DEFAULT 10,
    int_                    INTEGER DEFAULT 10,
    wis                     INTEGER DEFAULT 10,
    cha                     INTEGER DEFAULT 10,
    saving_throws           TEXT DEFAULT '{}',
    skills                  TEXT DEFAULT '{}',
    damage_vulnerabilities  TEXT DEFAULT '[]',
    damage_resistances      TEXT DEFAULT '[]',
    damage_immunities       TEXT DEFAULT '[]',
    condition_immunities    TEXT DEFAULT '[]',
    senses                  TEXT DEFAULT '',
    passive_perception      INTEGER DEFAULT 10,
    languages               TEXT DEFAULT '',
    equipment               TEXT DEFAULT '',
    cr                      TEXT DEFAULT '',
    xp                      INTEGER DEFAULT 0,
    proficiency_bonus       INTEGER DEFAULT 0,
    traits                  TEXT DEFAULT '[]',
    actions                 TEXT DEFAULT '[]',
    bonus_actions           TEXT DEFAULT '[]',
    reactions               TEXT DEFAULT '[]',
    legendary_actions       TEXT DEFAULT '[]',
    legendary_action_desc   TEXT DEFAULT '',
    lair_actions            TEXT DEFAULT '[]',
    mythic_actions          TEXT DEFAULT '[]',
    source                  TEXT DEFAULT 'MM 2024',
    source_file             TEXT DEFAULT '',
    tags                    TEXT DEFAULT '[]',
    created_at              TEXT,
    updated_at              TEXT
)
"""

_CREATE_TABLE_MYSQL = """
CREATE TABLE IF NOT EXISTS monsters (
    id                      VARCHAR(255) PRIMARY KEY,
    name_cn                 VARCHAR(255) NOT NULL,
    name_en                 VARCHAR(255) DEFAULT '',
    size                    VARCHAR(50) DEFAULT '',
    creature_type           VARCHAR(100) DEFAULT '',
    subtype                 VARCHAR(100) DEFAULT '',
    alignment               VARCHAR(100) DEFAULT '',
    ac                      INT DEFAULT 10,
    ac_note                 VARCHAR(255) DEFAULT '',
    hp                      INT DEFAULT 0,
    hp_formula              VARCHAR(100) DEFAULT '',
    speed                   VARCHAR(255) DEFAULT '',
    initiative_bonus        INT DEFAULT 0,
    str                     INT DEFAULT 10,
    dex                     INT DEFAULT 10,
    con                     INT DEFAULT 10,
    int_                    INT DEFAULT 10,
    wis                     INT DEFAULT 10,
    cha                     INT DEFAULT 10,
    saving_throws           TEXT DEFAULT '{}',
    skills                  TEXT DEFAULT '{}',
    damage_vulnerabilities  TEXT DEFAULT '[]',
    damage_resistances      TEXT DEFAULT '[]',
    damage_immunities       TEXT DEFAULT '[]',
    condition_immunities    TEXT DEFAULT '[]',
    senses                  TEXT DEFAULT '',
    passive_perception      INT DEFAULT 10,
    languages               TEXT DEFAULT '',
    equipment               TEXT DEFAULT '',
    cr                      VARCHAR(20) DEFAULT '',
    xp                      INT DEFAULT 0,
    proficiency_bonus       INT DEFAULT 0,
    traits                  MEDIUMTEXT,
    actions                 MEDIUMTEXT,
    bonus_actions           MEDIUMTEXT,
    reactions               MEDIUMTEXT,
    legendary_actions       MEDIUMTEXT,
    legendary_action_desc   TEXT DEFAULT '',
    lair_actions            MEDIUMTEXT,
    mythic_actions          MEDIUMTEXT,
    source                  VARCHAR(100) DEFAULT 'MM 2024',
    source_file             VARCHAR(255) DEFAULT '',
    tags                    TEXT DEFAULT '[]',
    created_at              VARCHAR(50),
    updated_at              VARCHAR(50),
    INDEX idx_monsters_name_cn (name_cn),
    INDEX idx_monsters_cr (cr),
    INDEX idx_monsters_type (creature_type),
    INDEX idx_monsters_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_CREATE_INDEXES_SQLITE = [
    "CREATE INDEX IF NOT EXISTS idx_monsters_name_cn ON monsters(name_cn)",
    "CREATE INDEX IF NOT EXISTS idx_monsters_cr ON monsters(cr)",
    "CREATE INDEX IF NOT EXISTS idx_monsters_type ON monsters(creature_type)",
    "CREATE INDEX IF NOT EXISTS idx_monsters_source ON monsters(source)",
]


# ================================================================
#  序列化
# ================================================================

def _actions_to_json(actions: list[MonsterAction]) -> str:
    return json.dumps([a.model_dump() for a in actions], ensure_ascii=False)


def _json_to_actions(raw: str) -> list[MonsterAction]:
    data = json.loads(raw or "[]")
    return [MonsterAction(**d) for d in data]


def _monster_to_row(m: Monster) -> tuple:
    return (
        m.id, m.name_cn, m.name_en, m.size, m.creature_type,
        m.subtype, m.alignment,
        m.ac, m.ac_note, m.hp, m.hp_formula, m.speed, m.initiative_bonus,
        m.abilities.str, m.abilities.dex, m.abilities.con,
        m.abilities.int_, m.abilities.wis, m.abilities.cha,
        json.dumps(m.saving_throws, ensure_ascii=False),
        json.dumps(m.skills, ensure_ascii=False),
        json.dumps(m.damage_vulnerabilities, ensure_ascii=False),
        json.dumps(m.damage_resistances, ensure_ascii=False),
        json.dumps(m.damage_immunities, ensure_ascii=False),
        json.dumps(m.condition_immunities, ensure_ascii=False),
        m.senses, m.passive_perception, m.languages, m.equipment,
        m.cr, m.xp, m.proficiency_bonus,
        _actions_to_json(m.traits),
        _actions_to_json(m.actions),
        _actions_to_json(m.bonus_actions),
        _actions_to_json(m.reactions),
        _actions_to_json(m.legendary_actions),
        m.legendary_action_desc,
        _actions_to_json(m.lair_actions),
        _actions_to_json(m.mythic_actions),
        m.source, m.source_file,
        json.dumps(m.tags, ensure_ascii=False),
        m.created_at, m.updated_at,
    )


def _row_to_monster(row: dict) -> Monster:
    return Monster(
        id=row["id"],
        name_cn=row["name_cn"],
        name_en=row["name_en"] or "",
        size=row["size"] or "",
        creature_type=row["creature_type"] or "",
        subtype=row["subtype"] or "",
        alignment=row["alignment"] or "",
        ac=row["ac"],
        ac_note=row["ac_note"] or "",
        hp=row["hp"],
        hp_formula=row["hp_formula"] or "",
        speed=row["speed"] or "",
        initiative_bonus=row["initiative_bonus"],
        abilities=MonsterAbilities(
            str=row["str"], dex=row["dex"], con=row["con"],
            int_=row["int_"], wis=row["wis"], cha=row["cha"],
        ),
        saving_throws=json.loads(row["saving_throws"] or "{}"),
        skills=json.loads(row["skills"] or "{}"),
        damage_vulnerabilities=json.loads(row["damage_vulnerabilities"] or "[]"),
        damage_resistances=json.loads(row["damage_resistances"] or "[]"),
        damage_immunities=json.loads(row["damage_immunities"] or "[]"),
        condition_immunities=json.loads(row["condition_immunities"] or "[]"),
        senses=row["senses"] or "",
        passive_perception=row["passive_perception"],
        languages=row["languages"] or "",
        equipment=row["equipment"] or "",
        cr=row["cr"] or "",
        xp=row["xp"],
        proficiency_bonus=row["proficiency_bonus"],
        traits=_json_to_actions(row["traits"]),
        actions=_json_to_actions(row["actions"]),
        bonus_actions=_json_to_actions(row["bonus_actions"]),
        reactions=_json_to_actions(row["reactions"]),
        legendary_actions=_json_to_actions(row["legendary_actions"]),
        legendary_action_desc=row["legendary_action_desc"] or "",
        lair_actions=_json_to_actions(row["lair_actions"]),
        mythic_actions=_json_to_actions(row["mythic_actions"]),
        source=row["source"] or "MM 2024",
        source_file=row["source_file"] or "",
        tags=json.loads(row["tags"] or "[]"),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


# ================================================================
#  公开 CRUD
# ================================================================

async def init_monster_db() -> None:
    """建表（幂等）"""
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute(_CREATE_TABLE_MYSQL)
        else:
            await conn.execute(_CREATE_TABLE_SQLITE)
            for idx in _CREATE_INDEXES_SQLITE:
                await conn.execute(idx)
        await conn.commit()


async def save_monster(monster: Monster, overwrite: bool = True) -> Monster:
    """INSERT OR REPLACE"""
    monster.updated_at = datetime.now().isoformat()
    async with async_conn() as conn:
        if not overwrite:
            # 按中文名查重
            cur = await conn.execute(
                f"SELECT id FROM monsters WHERE name_cn = {PH}", (monster.name_cn,)
            )
            if await cur.fetchone():
                return monster   # 跳过
        placeholders = ",".join([PH] * 45)
        await conn.execute(
            f"INSERT OR REPLACE INTO monsters VALUES ({placeholders})",
            _monster_to_row(monster),
        )
        await conn.commit()
    return monster


async def save_monsters(
    monsters: list[Monster],
    overwrite: bool = True,
) -> tuple[int, int]:
    """批量保存，返回 (inserted, skipped)"""
    inserted = 0
    skipped = 0
    async with async_conn() as conn:
        existing_names: set[str] = set()
        if not overwrite:
            cur = await conn.execute("SELECT name_cn FROM monsters")
            rows = await cur.fetchall()
            existing_names = {r["name_cn"] for r in rows}

        for m in monsters:
            if not overwrite and m.name_cn in existing_names:
                skipped += 1
                continue
            m.updated_at = datetime.now().isoformat()
            placeholders = ",".join([PH] * 45)
            await conn.execute(
                f"INSERT OR REPLACE INTO monsters VALUES ({placeholders})",
                _monster_to_row(m),
            )
            inserted += 1
        await conn.commit()
    return inserted, skipped


async def get_monster(monster_id: str) -> Monster | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM monsters WHERE id = {PH}", (monster_id,)
        )
        row = await cur.fetchone()
        return _row_to_monster(row) if row else None


async def get_monster_by_name(name: str) -> Monster | None:
    """按中文名精确匹配"""
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM monsters WHERE name_cn = {PH} OR name_en = {PH}",
            (name, name),
        )
        row = await cur.fetchone()
        return _row_to_monster(row) if row else None


async def list_monsters(
    creature_type: str | None = None,
    cr: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MonsterSummary]:
    """列表查询，返回轻量摘要"""
    wheres = []
    params: list = []
    if creature_type:
        wheres.append(f"creature_type = {PH}")
        params.append(creature_type)
    if cr:
        wheres.append(f"cr = {PH}")
        params.append(cr)
    if source:
        wheres.append(f"source = {PH}")
        params.append(source)

    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    sql = f"""
        SELECT id, name_cn, name_en, size, creature_type, alignment,
               ac, hp, cr, source
        FROM monsters
        {where_clause}
        ORDER BY name_cn
        LIMIT {PH} OFFSET {PH}
    """
    params += [limit, offset]

    async with async_conn() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
        return [
            MonsterSummary(
                id=r["id"], name_cn=r["name_cn"], name_en=r["name_en"] or "",
                size=r["size"] or "", creature_type=r["creature_type"] or "",
                alignment=r["alignment"] or "", ac=r["ac"], hp=r["hp"],
                cr=r["cr"] or "", source=r["source"] or "",
            )
            for r in rows
        ]


async def search_monsters(
    query: str,
    limit: int = 20,
) -> list[MonsterSummary]:
    """模糊搜索（名称 + 类型）"""
    like = f"%{query}%"
    sql = f"""
        SELECT id, name_cn, name_en, size, creature_type, alignment,
               ac, hp, cr, source
        FROM monsters
        WHERE name_cn LIKE {PH} OR name_en LIKE {PH} OR creature_type LIKE {PH}
        ORDER BY name_cn
        LIMIT {PH}
    """
    async with async_conn() as conn:
        cur = await conn.execute(sql, (like, like, like, limit))
        rows = await cur.fetchall()
        return [
            MonsterSummary(
                id=r["id"], name_cn=r["name_cn"], name_en=r["name_en"] or "",
                size=r["size"] or "", creature_type=r["creature_type"] or "",
                alignment=r["alignment"] or "", ac=r["ac"], hp=r["hp"],
                cr=r["cr"] or "", source=r["source"] or "",
            )
            for r in rows
        ]


async def delete_monster(monster_id: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM monsters WHERE id = {PH}", (monster_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


async def count_monsters() -> int:
    async with async_conn() as conn:
        cur = await conn.execute("SELECT COUNT(*) as cnt FROM monsters")
        row = await cur.fetchone()
        return row["cnt"] if row else 0
