from datetime import datetime, timezone
import os
import json
import time
import re
import requests
from mal_token_fetcher import get_access_token
from pathlib import Path

FIELDS = "id,title,main_picture,synopsis,genres,themes,media_type,episodes,status,start_date,end_date,mean,rank,popularity,rating,alternative_titles"
DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
DATA_DIR.mkdir(exist_ok=True)  # make sure folder exists
DB_FILE = DATA_DIR / "anime_data.json"

RANKING_URL = "https://api.myanimelist.net/v2/anime/ranking"
SEASON_URL = "https://api.myanimelist.net/v2/anime/season/{year}/{season}"

relations_cache = {}
episodes_cache = {}
existing_titles = {}
title_cache = {}

# ---------- Load Existing Data ----------
def load_existing_data():
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                return {anime["id"]: anime for anime in json.load(f)}
            except json.JSONDecodeError:
                print("[WARN] anime_data.json is corrupted — falling back to backup.")
    else:
        print("[WARN] anime_data.json not found — attempting to load most recent backup.")

    # Look for most recent backup
    backups = sorted(
        DATA_DIR.glob("anime_data_backup_*.json"),
        key=os.path.getmtime,
        reverse=True
    )
    if backups:
        latest_backup = backups[0]
        print(f"[INFO] Loading from backup: {latest_backup.name}")
        with open(latest_backup, "r", encoding="utf-8") as f:
            try:
                return {anime["id"]: anime for anime in json.load(f)}
            except json.JSONDecodeError:
                print("[ERROR] Backup file is also corrupted.")
                return {}
    else:
        print("[ERROR] No backups found.")
        return {}

# ---------- Backup Existing Data ----------
def backup_existing_data():
    if DB_FILE.exists():
        backup_name = DATA_DIR / f"anime_data_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        DB_FILE.rename(backup_name)
        print(f"[INFO] Backup saved as {backup_name}")

        backups = sorted(
            [f for f in DATA_DIR.glob("anime_data_backup_*.json")],
            key=os.path.getmtime
        )

        if len(backups) > 3:
            for old_file in backups[:-3]:
                old_file.unlink()
                print(f"[INFO] Deleted old backup {old_file}")

# ---------- Text Cleaning ----------
def clean_text(text):
    if text:
        return text.replace('\u2028', ' ').replace('\u2029', ' ').strip()
    return ""

# ---------- NSFW Detection ----------
def is_nsfw(anime):
    rating = (anime.get("rating") or "").lower()
    if "r+" in rating or "rx" in rating:
        return True
    genres = {g["name"].lower() for g in anime.get("genres", [])}
    themes = {t["name"].lower() for t in anime.get("themes", [])}
    nsfw_genres = {"hentai", "ecchi"}
    nsfw_themes = {"sexual content", "adult cast"}
    if nsfw_genres & genres or nsfw_themes & themes:
        return True
    synopsis = anime.get("synopsis", "").lower()
    if re.search(r"\b(fuck|sex|intercourse|rape|orgasm|ejaculate|seduce|nudity)\b", synopsis):
        return True
    return False

# ---------- Clean Title ----------
def clean_title(title):
    title = re.sub(r'\s*Season\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*Part\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(Movie\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(TV\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(OVA\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(ONA\)', '', title, flags=re.IGNORECASE)
    return title.strip()

# ---------- Fetch Ranking ----------
def fetch_ranking(ranking_type, limit, token):
    headers = {"Authorization": f"Bearer {token}"}
    all_anime = []
    for offset in range(0, limit, 100):
        params = {"ranking_type": ranking_type, "limit": 100, "offset": offset, "fields": FIELDS}
        print(f"[INFO] Fetching {ranking_type} offset {offset}...")
        r = requests.get(RANKING_URL, headers=headers, params=params)
        if r.status_code == 200:
            all_anime.extend([entry["node"] for entry in r.json().get("data", [])])
        else:
            print(f"[ERROR] {r.status_code} - {r.text}")
            break
        time.sleep(0.5)
    return all_anime

# ---------- Fetch Seasonal ----------
def fetch_season(year, season, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"fields": FIELDS, "limit": 100}
    all_anime = []
    url = SEASON_URL.format(year=year, season=season)
    while url:
        print(f"[INFO] Fetching season {year} {season}...")
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 200:
            data = r.json()
            all_anime.extend([entry["node"] for entry in data.get("data", [])])
            url = data.get("paging", {}).get("next")
            params = {}
        else:
            print(f"[ERROR] {r.status_code} - {r.text}")
            break
        time.sleep(0.5)
    return all_anime

# ---------- Find Root Anime ----------
def find_root_anime(anime_id, token, visited=None, anime_title=None, retries=3):
    if visited is None:
        visited = set()
    if anime_id in visited:
        return anime_id
    visited.add(anime_id)

    if anime_id in relations_cache:
        related_anime = relations_cache[anime_id]
    else:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.myanimelist.net/v2/anime/{anime_id}?fields=related_anime"
        related_anime = []
        for attempt in range(1, retries + 1):
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                related_anime = data.get("related_anime", [])
                break
            else:
                print(f"[WARN] Could not fetch related_anime for {anime_id} ({r.status_code}) - attempt {attempt}/{retries}")
                time.sleep(2 * attempt)
        relations_cache[anime_id] = related_anime
        if related_anime:
            time.sleep(1)

    for rel in related_anime:
        if rel.get("relation_type", "").lower() == "prequel":
            return find_root_anime(rel["node"]["id"], token, visited)

    if anime_title:
        base_title = clean_title(anime_title)
        for aid in existing_titles:
            if aid != anime_id and clean_title(existing_titles[aid]) == base_title:
                return aid
    return anime_id

# ---------- Get Episodes Count ----------
def get_episodes_count(anime_id, token, retries=3):
    if anime_id in episodes_cache:
        return episodes_cache[anime_id]

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.myanimelist.net/v2/anime/{anime_id}?fields=num_episodes"
    for attempt in range(1, retries + 1):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            episodes = r.json().get("num_episodes") or 0
            episodes_cache[anime_id] = episodes
            time.sleep(0.5)
            return episodes
        else:
            print(f"[WARN] Could not fetch episodes for {anime_id} - attempt {attempt}")
            time.sleep(1.5 * attempt)
    episodes_cache[anime_id] = 0
    return 0

# ---------- Build Grouped DB ----------
def build_grouped_db(new_data, existing_data, token):
    grouped_data = {}
    total = len(new_data)

    for i, anime in enumerate(new_data, start=1):
        anime_id = anime["id"]
        anime_title = anime["title"]
        existing_titles[anime_id] = anime_title
        root_id = find_root_anime(anime_id, token, anime_title=anime_title)

        if root_id not in grouped_data:
            # Collect alternative titles
            all_titles = []
            if anime.get("title"):
                all_titles.append(anime["title"])

            alts = anime.get("alternative_titles", {})
            if isinstance(alts, dict):
                if alts.get("en"):
                    all_titles.append(alts["en"])
                if alts.get("ja"):
                    all_titles.append(alts["ja"])
                if isinstance(alts.get("synonyms"), list):
                    all_titles.extend(alts["synonyms"])

            # Remove duplicates and blanks
            all_titles = list({t.strip() for t in all_titles if t and t.strip()})

            # Decide initial title
            initial_title = anime_title if anime_id == root_id else None
            if not initial_title and all_titles:
                initial_title = all_titles[0]  # fallback to first alternative title

            grouped_data[root_id] = existing_data.get(root_id, {
                "id": root_id,
                "title": initial_title,
                "all_titles": all_titles,
                "main_picture": anime.get("main_picture"),
                "tags": [g["name"] for g in anime.get("genres", [])],
                "synopsis": clean_text(anime.get("synopsis")),
                "rating": anime.get("rating"),
                "is_nsfw": is_nsfw(anime),
                "total_episodes": 0,
                "children_ids": [],
                "last_updated": datetime.now(timezone.utc).isoformat()
            })

        if anime_id not in grouped_data[root_id]["children_ids"]:
            grouped_data[root_id]["children_ids"].append(anime_id)

        if grouped_data[root_id]["title"] is None and anime_id == root_id:
            grouped_data[root_id]["title"] = anime_title or (all_titles[0] if all_titles else None)

        if i % 10 == 0 or i == total:
            print(f"[INFO] Processed {i}/{total} anime ({(i/total)*100:.1f}%)")

    root_list = list(grouped_data.items())
    total_roots = len(root_list)

    for i, (root_id, entry) in enumerate(root_list, start=1):
        all_child_ids = entry["children_ids"]
        for cid in all_child_ids:
            get_episodes_count(cid, token)
        entry["total_episodes"] = sum(episodes_cache[cid] for cid in all_child_ids)
        existing_data[root_id] = entry

        if i % 10 == 0 or i == total_roots:
            print(f"[INFO] Episode counts updated for {i}/{total_roots} roots ({(i / total_roots) * 100:.1f}%)")

    return existing_data

# ---------- Main ----------
if __name__ == "__main__":
    existing_data = load_existing_data()
    print(f"[INFO] Loaded {len(existing_data)} existing grouped entries.")
    backup_existing_data()
    token = get_access_token()

    fetched = []
    fetched.extend(fetch_ranking("bypopularity", 2000, token))
    fetched.extend(fetch_ranking("airing", 500, token))

    current_year = datetime.now().year
    current_month = datetime.now().month
    current_season = "winter" if current_month <= 3 else "spring" if current_month <= 6 else "summer" if current_month <= 9 else "fall"
    prev_season = "fall" if current_season == "winter" else "winter" if current_season == "spring" else "spring" if current_season == "summer" else "summer"
    prev_year = current_year - 1 if current_season == "winter" else current_year

    fetched.extend(fetch_season(current_year, current_season, token))
    fetched.extend(fetch_season(prev_year, prev_season, token))

    fetched_unique = {a["id"]: a for a in fetched if a["id"] not in existing_data}
    print(f"[INFO] {len(fetched_unique)} new anime to process.")

    updated_data = build_grouped_db(fetched_unique.values(), existing_data, token)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(updated_data.values()), f, indent=2, ensure_ascii=False)

    entry_count = len(updated_data)
    file_size_mb = os.path.getsize(DB_FILE) / (1024 * 1024)
    print(f"[INFO] Saved {entry_count} grouped anime entries to {DB_FILE} ({file_size_mb:.2f} MB)")

