"""
地图图片生成抽象层（策略模式）

支持四种后端：
  pillow   - 本地 Pillow 生成色块占位图（默认，无需网络）
  doubao   - 豆包 doubao-seedream 文生图 API（推荐，高质量）
  dalle    - OpenAI DALL-E 3 API
  sdwebui  - Stable Diffusion WebUI API（本地 GPU 服务）

后端由 .env 的 MAP_GENERATOR 配置项选择（默认 pillow）。
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import MAPS_DIR, image_path_to_url


def _get_backend() -> str:
    from config import get_settings
    return get_settings().map_generator.lower()


# ============================================================
#  地图生成专用 System Prompt（正向 + 负向）
# ============================================================

_WORLD_MAP_PROMPT_PREFIX = (
    "Fantasy RPG world map, top-down bird's eye view, "
    "hand-drawn cartographic style, parchment paper texture, "
    "soft watercolor terrain shading, "
    "clearly distinct terrain zones (mountains, forests, plains, rivers, coastlines), "
    "illustrated city/town icons, winding roads and rivers, "
    "aged vignette border, warm candlelight color palette, "
    "no characters or figures, no UI elements, no text overlay, "
    "professional tabletop RPG map illustration, high detail, painterly style. "
)

_WORLD_MAP_NEGATIVE = (
    "modern style, sci-fi, isometric, 3D render, photo-realistic, "
    "characters, people, figures, perspective view, blurry, low quality, "
    "watermark, logo, text, grid lines, hex grid, numbers"
)

_ENCOUNTER_MAP_PROMPT_PREFIX = (
    "D&D tactical battle map, perfectly top-down overhead view, "
    "flat 2D map illustration style suitable for virtual tabletop (VTT), "
    "clearly readable floor/ground texture, "
    "rich environmental details (furniture, obstacles, terrain features), "
    "consistent lighting from above, strong contrast between walkable areas and walls/obstacles, "
    "no characters, no creatures, no miniatures, no grid overlay, "
    "high resolution, clean and detailed. "
)

_ENCOUNTER_MAP_NEGATIVE = (
    "characters, people, miniatures, tokens, perspective view, isometric, "
    "3D render, photo-realistic, modern setting, sci-fi, "
    "grid lines, hex grid, blurry, low quality, watermark, text, "
    "dark and unreadable, overly cluttered"
)

_ENCOUNTER_ENV_HINTS = {
    ("dungeon", "地牢", "underground", "地下"): (
        "stone dungeon floor with cracks and moss, "
        "dark stone walls, flickering torchlight warm glow, "
        "iron-barred doors, barrels, crates, chains"
    ),
    ("forest", "森林", "woodland", "trees", "jungle", "丛林"): (
        "forest floor with grass and dirt path, tree roots, "
        "dappled sunlight through canopy, fallen logs, undergrowth, "
        "natural clearing, mossy stones"
    ),
    ("tavern", "酒馆", "inn", "旅店", "interior", "indoor", "室内"): (
        "wooden plank floor, tavern interior, "
        "tables and chairs, fireplace, bar counter, "
        "warm candlelight, cozy atmosphere"
    ),
    ("cave", "洞穴", "cavern"): (
        "rocky cave floor with stalagmites and stalactites, "
        "underground lake, glowing crystals, rough stone walls"
    ),
    ("city", "城市", "street", "街道", "urban", "plaza", "广场"): (
        "cobblestone street or plaza, "
        "building facades and doorways, market stalls, "
        "urban furniture, daytime outdoor lighting"
    ),
    ("desert", "沙漠", "ruin", "遗迹", "temple", "神殿"): (
        "sand-covered ancient stone floor, "
        "crumbling pillars and walls, hieroglyph carvings, "
        "sand drifts in corners, bleached stone texture"
    ),
}

_WORLD_ENV_HINTS = {
    ("arctic", "冰原", "frozen", "tundra", "snow", "雪"): "icy tundra, frozen lakes, sparse pine forests, snow-capped mountains, ",
    ("tropical", "热带", "jungle", "丛林", "rainforest"): "dense jungle, tropical rivers, ancient ruins overgrown with vines, swampy lowlands, ",
    ("desert", "沙漠"): "vast desert expanse, oasis towns, sandstone mesas, ancient caravan routes, ",
    ("volcanic", "火山", "lava", "岩浆"): "volcanic mountain ranges, lava fields, ashen wastelands, obsidian formations, ",
}


def _enhance_encounter_prompt(user_prompt: str) -> str:
    p = user_prompt.lower()
    for keywords, hint in _ENCOUNTER_ENV_HINTS.items():
        if any(k in p for k in keywords):
            return _ENCOUNTER_MAP_PROMPT_PREFIX + hint + ", " + user_prompt
    return _ENCOUNTER_MAP_PROMPT_PREFIX + "stone or wooden floor, generic fantasy environment, " + user_prompt


def _enhance_world_prompt(user_prompt: str) -> str:
    p = user_prompt.lower()
    for keywords, hint in _WORLD_ENV_HINTS.items():
        if any(k in p for k in keywords):
            return _WORLD_MAP_PROMPT_PREFIX + hint + user_prompt
    return _WORLD_MAP_PROMPT_PREFIX + user_prompt


# ============================================================
#  对外接口
# ============================================================

async def generate_region_map(
    prompt: str,
    width_px: int = 1024,
    height_px: int = 1024,
) -> str:
    """Generate a region map image. Returns a served URL path (/static/maps/...)."""
    backend = _get_backend()
    if backend == "doubao":
        disk_path = await _doubao_generate(prompt, _WORLD_MAP_NEGATIVE, width_px, height_px, "region")
    elif backend == "dalle":
        disk_path = await _dalle_generate(prompt, width_px, height_px, "region")
    elif backend == "sdwebui":
        disk_path = await _sdwebui_generate(prompt, width_px, height_px, "region")
    else:
        disk_path = await _pillow_generate_world(prompt, width_px, height_px)
    return image_path_to_url(disk_path)


async def generate_world_map(
    prompt: str,
    width_px: int = 1024,
    height_px: int = 1024,
) -> str:
    """Generate a world map image. Returns a served URL path (/static/maps/...)."""
    backend = _get_backend()
    enhanced = _enhance_world_prompt(prompt)
    if backend == "doubao":
        disk_path = await _doubao_generate(enhanced, _WORLD_MAP_NEGATIVE, width_px, height_px, "world")
    elif backend == "dalle":
        disk_path = await _dalle_generate(enhanced, width_px, height_px, "world")
    elif backend == "sdwebui":
        disk_path = await _sdwebui_generate(enhanced, width_px, height_px, "world")
    else:
        disk_path = await _pillow_generate_world(prompt, width_px, height_px)
    return image_path_to_url(disk_path)


async def generate_encounter_bg(
    prompt: str,
    grid_cols: int = 20,
    grid_rows: int = 20,
    cell_px: int = 48,
    overlay_grid: bool = True,
) -> str:
    """Generate an encounter background image. Returns a served URL path (/static/maps/...)."""
    width_px  = grid_cols * cell_px
    height_px = grid_rows * cell_px
    backend   = _get_backend()
    enhanced  = _enhance_encounter_prompt(prompt)

    if backend == "doubao":
        disk_path = await _doubao_generate(enhanced, _ENCOUNTER_MAP_NEGATIVE, width_px, height_px, "encounter")
    elif backend == "dalle":
        disk_path = await _dalle_generate(enhanced, width_px, height_px, "encounter")
    elif backend == "sdwebui":
        disk_path = await _sdwebui_generate(enhanced, width_px, height_px, "encounter")
        if overlay_grid:
            disk_path = _overlay_grid(disk_path, grid_cols, grid_rows, cell_px)
        return image_path_to_url(disk_path)
    else:
        disk_path = await _pillow_generate_encounter(prompt, grid_cols, grid_rows, cell_px)

    if overlay_grid:
        disk_path = _overlay_grid(disk_path, grid_cols, grid_rows, cell_px)
    return image_path_to_url(disk_path)


# ============================================================
#  豆包 doubao-seedream 文生图
# ============================================================

async def _doubao_generate(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    map_type: str,
) -> str:
    import uuid, httpx
    from config import get_settings

    s = get_settings()
    api_key = s.doubao_api_key
    if not api_key:
        raise RuntimeError("DOUBAO_API_KEY 未配置，请在 .env 中填写")

    size = _pick_doubao_size(width, height)

    payload = {
        "model": s.doubao_image_model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "negative_prompt": negative_prompt,
        "response_format": "url",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{s.doubao_base_url}/images/generations",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        remote_url = data["data"][0]["url"]
        img_resp = await client.get(remote_url, timeout=60.0)
        img_resp.raise_for_status()

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{map_type}_{uuid.uuid4().hex[:8]}.png"
    path = MAPS_DIR / filename
    path.write_bytes(img_resp.content)
    return str(path)


def _pick_doubao_size(width: int, height: int) -> str:
    ratio = width / height
    candidates = [
        (1, 1, "1024x1024"),
        (4, 3, "1024x768"),
        (3, 4, "768x1024"),
        (16, 9, "1280x720"),
        (9, 16, "720x1280"),
        (3, 2, "1024x682"),
        (2, 3, "682x1024"),
    ]
    best, best_diff = "1024x1024", float("inf")
    for w, h, label in candidates:
        diff = abs(ratio - w / h)
        if diff < best_diff:
            best, best_diff = label, diff
    return best


# ============================================================
#  DALL-E 3
# ============================================================

async def _dalle_generate(
    prompt: str,
    width: int,
    height: int,
    map_type: str,
) -> str:
    import uuid, httpx
    from config import get_settings

    s = get_settings()
    api_key = s.dalle_api_key or s.openai_api_key
    if not api_key:
        raise RuntimeError("DALLE_API_KEY 未配置")

    size = "1792x1024" if width > height else ("1024x1792" if height > width else "1024x1024")

    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": size,
        "quality": "standard",
        "n": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers)
        resp.raise_for_status()
        remote_url = resp.json()["data"][0]["url"]
        img_resp = await client.get(remote_url)
        img_resp.raise_for_status()

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{map_type}_{uuid.uuid4().hex[:8]}.png"
    path = MAPS_DIR / filename
    path.write_bytes(img_resp.content)
    return str(path)


# ============================================================
#  Stable Diffusion WebUI
# ============================================================

async def _sdwebui_generate(
    prompt: str,
    width: int,
    height: int,
    map_type: str,
) -> str:
    import base64, uuid, httpx
    from config import get_settings

    base_url = get_settings().sdwebui_url
    neg = _ENCOUNTER_MAP_NEGATIVE if map_type == "encounter" else _WORLD_MAP_NEGATIVE

    payload = {
        "prompt": prompt,
        "negative_prompt": neg,
        "width": min(width, 768),
        "height": min(height, 768),
        "steps": 20,
        "cfg_scale": 7,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}/sdapi/v1/txt2img", json=payload)
        resp.raise_for_status()
        img_b64 = resp.json()["images"][0]

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{map_type}_{uuid.uuid4().hex[:8]}.png"
    path = MAPS_DIR / filename
    path.write_bytes(base64.b64decode(img_b64))
    return str(path)


# ============================================================
#  Pillow 占位生成器
# ============================================================

async def _pillow_generate_world(prompt: str, width: int, height: int) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow 未安装，请运行: pip install Pillow")

    import uuid, random

    p = prompt.lower()
    if any(k in p for k in ("forest", "森林", "jungle", "丛林")):
        bg = (34, 139, 34)
    elif any(k in p for k in ("ocean", "sea", "海", "洋")):
        bg = (30, 144, 255)
    elif any(k in p for k in ("desert", "沙漠")):
        bg = (210, 180, 140)
    elif any(k in p for k in ("snow", "ice", "雪", "冰")):
        bg = (220, 240, 255)
    else:
        bg = (144, 169, 85)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    rng = random.Random(hash(prompt) % (2**31))
    for _ in range(60):
        x, y, r = rng.randint(0, width-1), rng.randint(0, height-1), rng.randint(20, 80)
        shade = tuple(max(0, min(255, c + rng.randint(-40, 40))) for c in bg)
        draw.ellipse([x-r, y-r, x+r, y+r], fill=shade)
    for _ in range(8):
        x, y, w, h = rng.randint(0, width-1), rng.randint(0, height-1), rng.randint(40, 150), rng.randint(20, 80)
        draw.ellipse([x, y, x+w, y+h], fill=(65, 105, 225))
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 10), f"[Pillow] {prompt[:40]}", fill=(0, 0, 0), font=font)

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"world_{uuid.uuid4().hex[:8]}.png"
    path = MAPS_DIR / filename
    img.save(path)
    return str(path)


async def _pillow_generate_encounter(
    prompt: str, grid_cols: int, grid_rows: int, cell_px: int
) -> str:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise RuntimeError("Pillow 未安装，请运行: pip install Pillow")

    import uuid

    width, height = grid_cols * cell_px, grid_rows * cell_px
    p = prompt.lower()
    if any(k in p for k in ("dungeon", "地牢", "cave", "洞穴")):
        bg, grid_color = (60, 50, 40), (100, 90, 80)
    elif any(k in p for k in ("forest", "森林")):
        bg, grid_color = (50, 100, 50), (70, 130, 70)
    else:
        bg, grid_color = (200, 190, 170), (160, 150, 130)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    for col in range(grid_cols + 1):
        draw.line([(col * cell_px, 0), (col * cell_px, height)], fill=grid_color, width=1)
    for row in range(grid_rows + 1):
        draw.line([(0, row * cell_px), (width, row * cell_px)], fill=grid_color, width=1)

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"encounter_{uuid.uuid4().hex[:8]}.png"
    path = MAPS_DIR / filename
    img.save(path)
    return str(path)


# ============================================================
#  网格叠加后处理（AI 生成图 + 精确网格）
# ============================================================

def _overlay_grid(
    image_path: str,
    grid_cols: int,
    grid_rows: int,
    cell_px: int,
    grid_color: tuple = (255, 255, 255, 80),
    line_width: int = 1,
) -> str:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return image_path

    target_w, target_h = grid_cols * cell_px, grid_rows * cell_px
    img = Image.open(image_path).convert("RGBA")
    if img.size != (target_w, target_h):
        img = img.resize((target_w, target_h), Image.LANCZOS)

    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for col in range(grid_cols + 1):
        x = col * cell_px
        draw.line([(x, 0), (x, target_h)], fill=grid_color, width=line_width)
    for row in range(grid_rows + 1):
        y = row * cell_px
        draw.line([(0, y), (target_w, y)], fill=grid_color, width=line_width)

    Image.alpha_composite(img, overlay).convert("RGB").save(image_path)
    return image_path
