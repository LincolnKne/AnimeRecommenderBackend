from fastapi import APIRouter, Query
from pathlib import Path
from ..services.data_loader import load_anime_data

router = APIRouter()

# Only explicit sexual themes here
NSFW_TAGS = {
    "hentai",
    "ecchi",
    "magical sex shift",
    "erotica"
}

# Cache storage
_config_cache = {
    "nsfw_false": None,
    "nsfw_true": None,
    "last_mtime": None
}

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "anime_data.json"

def _build_config(nsfw_ok: bool):
    data = load_anime_data()
    total_entries = len(data)
    last_updated = max(
        (anime.get("last_updated") for anime in data if anime.get("last_updated")),
        default=None
    )

    tags_map = {}
    for anime in data:
        for tag in anime.get("tags", []):
            tag_clean = tag.strip()
            tag_lower = tag_clean.lower()

            if not nsfw_ok and tag_lower in NSFW_TAGS:
                continue

            if tag_lower not in tags_map:
                tags_map[tag_lower] = tag_clean

    sorted_tags = sorted(tags_map.values(), key=lambda t: t.lower())

    return {
        "tags": sorted_tags,
        "total_entries": total_entries,
        "last_updated": last_updated
    }

@router.get("/config")
def get_config(nsfw_ok: bool = Query(False, description="Include NSFW tags")):
    mtime = DATA_PATH.stat().st_mtime
    cache_key = "nsfw_true" if nsfw_ok else "nsfw_false"

    # If cache is invalid or file changed, rebuild
    if _config_cache[cache_key] is None or _config_cache["last_mtime"] != mtime:
        _config_cache[cache_key] = _build_config(nsfw_ok)
        _config_cache["last_mtime"] = mtime

    return _config_cache[cache_key]
