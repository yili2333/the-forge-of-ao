from pathlib import Path

# Canonical directory for all map image files (world maps + encounter backgrounds).
# Anchored to src/data/maps regardless of the working directory at launch time.
MAPS_DIR = Path(__file__).parent.parent / "data" / "maps"

# URL prefix under which map images are served (mounted as StaticFiles in main.py).
MAPS_URL_PREFIX = "/static/maps"


def image_path_to_url(disk_path: str) -> str:
    """Convert an absolute/relative disk path inside MAPS_DIR to a served URL."""
    rel = Path(disk_path).name
    return f"{MAPS_URL_PREFIX}/{rel}"


def image_url_to_path(url: str) -> Path:
    """Convert a served URL back to the absolute disk path."""
    filename = url.removeprefix(MAPS_URL_PREFIX).lstrip("/")
    return MAPS_DIR / filename
