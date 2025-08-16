from fastapi import APIRouter, Query
from pathlib import Path
from ..services.data_loader import load_anime_data

router = APIRouter()

NSFW_TAGS = {
    "hentai",
    "ecchi",
    "magical sex shift",
    "erotica"
}

# Cache
_tags_cache = {
    "nsfw_false": None,
    "nsfw_true": None,
    "last_mtime": None
}

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "anime_data.json"

def _build_tags(nsfw_ok: bool):
    data = load_anime_data()
    tags_map = {}

    for anime in data:
        for tag in anime.get("tags", []):
            tag_clean = tag.strip()
            tag_lower = tag_clean.lower()

            if not nsfw_ok and tag_lower in NSFW_TAGS:
                continue

            if tag_lower not in tags_map:
                tags_map[tag_lower] = tag_clean

    return sorted(tags_map.values(), key=lambda t: t.lower())

@router.get("/tags")
def get_tags(nsfw_ok: bool = Query(False, description="Include NSFW tags")):
    mtime = DATA_PATH.stat().st_mtime
    cache_key = "nsfw_true" if nsfw_ok else "nsfw_false"

    if _tags_cache[cache_key] is None or _tags_cache["last_mtime"] != mtime:
        _tags_cache[cache_key] = {"tags": _build_tags(nsfw_ok)}
        _tags_cache["last_mtime"] = mtime

    return _tags_cache[cache_key]
