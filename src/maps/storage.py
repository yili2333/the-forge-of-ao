"""
地图持久化
支持 SQLite 和 MySQL 双后端（通过 db_helper）
"""
from __future__ import annotations

import json
from datetime import datetime

from db_helper import async_conn, IS_MYSQL, PH

from .models import EncounterMap, RegionMap, WorldMap


async def init_map_db() -> None:
    async with async_conn() as conn:
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS world_maps (
                    id              VARCHAR(255) PRIMARY KEY,
                    campaign_id     VARCHAR(255) NOT NULL,
                    name            VARCHAR(255) NOT NULL,
                    description     TEXT DEFAULT '',
                    width_km        DOUBLE DEFAULT 1000.0,
                    height_km       DOUBLE DEFAULT 1000.0,
                    image_url       TEXT,
                    image_prompt    TEXT DEFAULT '',
                    pois_json       MEDIUMTEXT DEFAULT '[]',
                    player_positions_json MEDIUMTEXT DEFAULT '{}',
                    visited_locations_json MEDIUMTEXT DEFAULT '{}',
                    fog_of_war      TINYINT DEFAULT 1,
                    created_at      VARCHAR(50),
                    updated_at      VARCHAR(50),
                    INDEX idx_wmap_campaign (campaign_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS encounter_maps (
                    id              VARCHAR(255) PRIMARY KEY,
                    campaign_id     VARCHAR(255) NOT NULL,
                    name            VARCHAR(255) NOT NULL,
                    description     TEXT DEFAULT '',
                    grid_cols       INT DEFAULT 20,
                    grid_rows       INT DEFAULT 20,
                    cell_size_ft    INT DEFAULT 5,
                    image_url       TEXT,
                    image_prompt    TEXT DEFAULT '',
                    cells_json      MEDIUMTEXT DEFAULT '[]',
                    creatures_json  MEDIUMTEXT DEFAULT '[]',
                    objects_json    MEDIUMTEXT DEFAULT '[]',
                    is_active       TINYINT DEFAULT 0,
                    created_at      VARCHAR(50),
                    updated_at      VARCHAR(50),
                    INDEX idx_emap_campaign (campaign_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS world_maps (
                    id              TEXT PRIMARY KEY,
                    campaign_id     TEXT NOT NULL,
                    name            TEXT NOT NULL,
                    description     TEXT DEFAULT '',
                    width_km        REAL DEFAULT 1000.0,
                    height_km       REAL DEFAULT 1000.0,
                    image_url       TEXT,
                    image_prompt    TEXT DEFAULT '',
                    pois_json       TEXT DEFAULT '[]',
                    player_positions_json TEXT DEFAULT '{}',
                    visited_locations_json TEXT DEFAULT '{}',
                    fog_of_war      INTEGER DEFAULT 1,
                    created_at      TEXT,
                    updated_at      TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_wmap_campaign ON world_maps(campaign_id)"
            )

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS encounter_maps (
                    id              TEXT PRIMARY KEY,
                    campaign_id     TEXT NOT NULL,
                    name            TEXT NOT NULL,
                    description     TEXT DEFAULT '',
                    grid_cols       INTEGER DEFAULT 20,
                    grid_rows       INTEGER DEFAULT 20,
                    cell_size_ft    INTEGER DEFAULT 5,
                    image_url       TEXT,
                    image_prompt    TEXT DEFAULT '',
                    cells_json      TEXT DEFAULT '[]',
                    creatures_json  TEXT DEFAULT '[]',
                    objects_json    TEXT DEFAULT '[]',
                    is_active       INTEGER DEFAULT 0,
                    created_at      TEXT,
                    updated_at      TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_emap_campaign ON encounter_maps(campaign_id)"
            )
        if IS_MYSQL:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS region_maps (
                    id                  VARCHAR(255) PRIMARY KEY,
                    campaign_id         VARCHAR(255) NOT NULL,
                    name                VARCHAR(255) NOT NULL,
                    description         TEXT DEFAULT '',
                    region_type         VARCHAR(50) DEFAULT 'other',
                    area_km             DOUBLE DEFAULT 10.0,
                    image_url           TEXT,
                    image_prompt        TEXT DEFAULT '',
                    pois_json           MEDIUMTEXT DEFAULT '[]',
                    parent_world_map_id VARCHAR(255),
                    parent_poi_id       VARCHAR(255),
                    created_at          VARCHAR(50),
                    updated_at          VARCHAR(50),
                    INDEX idx_rmap_campaign (campaign_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS region_maps (
                    id                  TEXT PRIMARY KEY,
                    campaign_id         TEXT NOT NULL,
                    name                TEXT NOT NULL,
                    description         TEXT DEFAULT '',
                    region_type         TEXT DEFAULT 'other',
                    area_km             REAL DEFAULT 10.0,
                    image_url           TEXT,
                    image_prompt        TEXT DEFAULT '',
                    pois_json           TEXT DEFAULT '[]',
                    parent_world_map_id TEXT,
                    parent_poi_id       TEXT,
                    created_at          TEXT,
                    updated_at          TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rmap_campaign ON region_maps(campaign_id)"
            )
        await conn.commit()


# ---- WorldMap ----

async def save_world_map(m: WorldMap) -> WorldMap:
    m = m.model_copy(deep=True)
    now = datetime.now().isoformat(timespec="seconds")
    if not m.created_at:
        m.created_at = now
    m.updated_at = now

    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO world_maps
            (id, campaign_id, name, description, width_km, height_km,
             image_url, image_prompt, pois_json, player_positions_json,
             visited_locations_json, fog_of_war, created_at, updated_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            m.id, m.campaign_id, m.name, m.description,
            m.width_km, m.height_km, m.image_url, m.image_prompt,
            json.dumps([p.model_dump() for p in m.pois]),
            json.dumps(m.player_positions),
            json.dumps(m.visited_locations),
            int(m.fog_of_war),
            m.created_at, m.updated_at,
        ))
        await conn.commit()
    return m


async def get_world_map(map_id: str) -> WorldMap | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM world_maps WHERE id = {PH}", (map_id,)
        )
        row = await cur.fetchone()
        return _row_to_world_map(row) if row else None


async def get_campaign_world_map(campaign_id: str) -> WorldMap | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM world_maps WHERE campaign_id = {PH} ORDER BY updated_at DESC LIMIT 1",
            (campaign_id,),
        )
        row = await cur.fetchone()
        return _row_to_world_map(row) if row else None


async def delete_world_map(map_id: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM world_maps WHERE id = {PH}", (map_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


# ---- EncounterMap ----

async def save_encounter_map(m: EncounterMap) -> EncounterMap:
    m = m.model_copy(deep=True)
    now = datetime.now().isoformat(timespec="seconds")
    if not m.created_at:
        m.created_at = now
    m.updated_at = now

    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO encounter_maps
            (id, campaign_id, name, description, grid_cols, grid_rows,
             cell_size_ft, image_url, image_prompt,
             cells_json, creatures_json, objects_json,
             is_active, created_at, updated_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            m.id, m.campaign_id, m.name, m.description,
            m.grid_cols, m.grid_rows, m.cell_size_ft,
            m.image_url, m.image_prompt,
            json.dumps(m.cells),
            json.dumps([c.model_dump() for c in m.creatures]),
            json.dumps([o.model_dump() for o in m.objects]),
            int(m.is_active),
            m.created_at, m.updated_at,
        ))
        await conn.commit()
    return m


async def get_encounter_map(map_id: str) -> EncounterMap | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM encounter_maps WHERE id = {PH}", (map_id,)
        )
        row = await cur.fetchone()
        return _row_to_encounter_map(row) if row else None


async def list_encounter_maps(campaign_id: str) -> list[EncounterMap]:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM encounter_maps WHERE campaign_id = {PH} ORDER BY updated_at DESC",
            (campaign_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_encounter_map(r) for r in rows]


async def delete_encounter_map(map_id: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM encounter_maps WHERE id = {PH}", (map_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


# ---- RegionMap ----

async def save_region_map(m: RegionMap) -> RegionMap:
    m = m.model_copy(deep=True)
    now = datetime.now().isoformat(timespec="seconds")
    if not m.created_at:
        m.created_at = now
    m.updated_at = now

    async with async_conn() as conn:
        await conn.execute(f"""
            INSERT OR REPLACE INTO region_maps
            (id, campaign_id, name, description, region_type, area_km,
             image_url, image_prompt, pois_json,
             parent_world_map_id, parent_poi_id, created_at, updated_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        """, (
            m.id, m.campaign_id, m.name, m.description,
            m.region_type.value, m.area_km,
            m.image_url, m.image_prompt,
            json.dumps([p.model_dump() for p in m.pois]),
            m.parent_world_map_id, m.parent_poi_id,
            m.created_at, m.updated_at,
        ))
        await conn.commit()
    return m


async def get_region_map(map_id: str) -> RegionMap | None:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM region_maps WHERE id = {PH}", (map_id,)
        )
        row = await cur.fetchone()
        return _row_to_region_map(row) if row else None


async def list_region_maps(campaign_id: str) -> list[RegionMap]:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"SELECT * FROM region_maps WHERE campaign_id = {PH} ORDER BY updated_at DESC",
            (campaign_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_region_map(r) for r in rows]


async def delete_region_map(map_id: str) -> bool:
    async with async_conn() as conn:
        cur = await conn.execute(
            f"DELETE FROM region_maps WHERE id = {PH}", (map_id,)
        )
        await conn.commit()
        return cur.rowcount > 0


# ---- serialization ----

def _row_to_world_map(row: dict) -> WorldMap:
    from .models import PointOfInterest
    pois_raw = json.loads(row["pois_json"] or "[]")
    return WorldMap(
        id=row["id"],
        campaign_id=row["campaign_id"],
        name=row["name"],
        description=row["description"] or "",
        width_km=row["width_km"] or 1000.0,
        height_km=row["height_km"] or 1000.0,
        image_url=row["image_url"],
        image_prompt=row["image_prompt"] or "",
        pois=[PointOfInterest(**p) for p in pois_raw],
        player_positions=json.loads(row["player_positions_json"] or "{}"),
        visited_locations=json.loads(row["visited_locations_json"] or "{}"),
        fog_of_war=bool(row["fog_of_war"]),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def _row_to_encounter_map(row: dict) -> EncounterMap:
    from .models import MapCreature, MapObject
    creatures_raw = json.loads(row["creatures_json"] or "[]")
    objects_raw   = json.loads(row["objects_json"] or "[]")
    return EncounterMap(
        id=row["id"],
        campaign_id=row["campaign_id"],
        name=row["name"],
        description=row["description"] or "",
        grid_cols=row["grid_cols"] or 20,
        grid_rows=row["grid_rows"] or 20,
        cell_size_ft=row["cell_size_ft"] or 5,
        image_url=row["image_url"],
        image_prompt=row["image_prompt"] or "",
        cells=json.loads(row["cells_json"] or "[]"),
        creatures=[MapCreature(**c) for c in creatures_raw],
        objects=[MapObject(**o) for o in objects_raw],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def _row_to_region_map(row: dict) -> RegionMap:
    from .models import PointOfInterest, RegionType
    pois_raw = json.loads(row["pois_json"] or "[]")
    return RegionMap(
        id=row["id"],
        campaign_id=row["campaign_id"],
        name=row["name"],
        description=row["description"] or "",
        region_type=RegionType(row["region_type"] or "other"),
        area_km=row["area_km"] or 10.0,
        image_url=row["image_url"],
        image_prompt=row["image_prompt"] or "",
        pois=[PointOfInterest(**p) for p in pois_raw],
        parent_world_map_id=row["parent_world_map_id"],
        parent_poi_id=row["parent_poi_id"],
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )
