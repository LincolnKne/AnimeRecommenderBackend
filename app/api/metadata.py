from fastapi import APIRouter
from pathlib import Path
from ..services.data_loader import load_anime_data

router = APIRouter()

_metadata_cache = {
    "data": None,
    "last_mtime": None
}

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "anime_data.json"

def _build_metadata():
    data = load_anime_data()
    total_entries = len(data)
    last_updated = max(
        (anime.get("last_updated") for anime in data if anime.get("last_updated")),
        default=None
    )
    return {"total_entries": total_entries, "last_updated": last_updated}

@router.get("/metadata")
def get_metadata():
    mtime = DATA_PATH.stat().st_mtime

    if _metadata_cache["data"] is None or _metadata_cache["last_mtime"] != mtime:
        _metadata_cache["data"] = _build_metadata()
        _metadata_cache["last_mtime"] = mtime

    return _metadata_cache["data"]
