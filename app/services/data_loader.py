import json
from pathlib import Path
from typing import List, Dict, Any
from rapidfuzz import fuzz

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "anime_data.json"

_cache: List[Dict[str, Any]] | None = None
_index_by_id: Dict[int, Dict[str, Any]] | None = None

def _normalize_titles_inplace(rows: List[Dict[str, Any]]) -> None:
    for a in rows:
        title = (a.get("title") or "").strip()
        if not title:
            ats = [t.strip() for t in a.get("all_titles", []) if t and t.strip()]
            a["title"] = ats[0] if ats else f"Untitled #{a.get('id','')}"

def load_anime_data() -> List[Dict[str, Any]]:
    """Load anime data from file, with backup fallback, cache for future use."""
    global _cache, _index_by_id
    if _cache is None:
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("[WARN] anime_data.json missing or unreadable — attempting to load backup.")
            data_dir = DATA_PATH.parent
            backups = sorted(
                data_dir.glob("anime_data_backup_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if backups:
                latest_backup = backups[0]
                print(f"[INFO] Loading from backup: {latest_backup.name}")
                with open(latest_backup, "r", encoding="utf-8") as f:
                    try:
                        _cache = json.load(f)
                    except json.JSONDecodeError:
                        print("[ERROR] Backup file is also corrupted.")
                        _cache = []
            else:
                print("[ERROR] No backups found.")
                _cache = []

        # <<< Normalize titles here so API never serves null titles
        _normalize_titles_inplace(_cache)

        _index_by_id = {int(a["id"]): a for a in _cache}
    return _cache


def get_by_ids(ids: List[int]) -> List[Dict[str, Any]]:
    # Get anime entries by their IDs
    load_anime_data()
    return [_index_by_id[i] for i in ids if i in _index_by_id]  # type: ignore

def get_by_titles(titles: List[str], threshold: int = 80) -> List[int]:
    data = load_anime_data()
    matched_ids = []

    for title_to_match in titles:
        if not title_to_match or not isinstance(title_to_match, str):
            continue

        t_norm = title_to_match.strip().lower()

        for anime in data:
            all_titles = []
            if anime.get("title"):
                all_titles.append(anime["title"])
            all_titles.extend(anime.get("all_titles", []))

            # Normalize for comparison
            all_titles_lower = [alt.strip().lower() for alt in all_titles if alt]

            # --- Exact match first (case-insensitive) ---
            if t_norm in all_titles_lower:
                matched_ids.append(anime["id"])
                continue

            # --- Fuzzy fallback ---
            for alt in all_titles_lower:
                if fuzz.ratio(t_norm, alt) >= threshold:
                    matched_ids.append(anime["id"])
                    break

    return list(set(matched_ids))
