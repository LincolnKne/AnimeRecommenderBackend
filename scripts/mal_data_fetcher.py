from datetime import datetime, timezone
import os, re, time, json
import requests
import psycopg
from requests.exceptions import RequestException, SSLError
from psycopg.rows import dict_row
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from mal_token_fetcher import get_access_token

# -------------------
# Setup
# -------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_FILE = DATA_DIR / f"anime_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

FIELDS = "id,title,main_picture,synopsis,genres,themes,media_type,episodes,status,start_date,end_date,mean,rank,popularity,rating,alternative_titles"
RANKING_URL = "https://api.myanimelist.net/v2/anime/ranking"
SEASON_URL = "https://api.myanimelist.net/v2/anime/season/{year}/{season}"

relations_cache = {}
episodes_cache = {}
existing_titles = {}

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
    synopsis = (anime.get("synopsis") or "").lower()
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
        try:
            r = requests.get(RANKING_URL, headers=headers, params=params, timeout=45)
            if r.status_code == 200:
                all_anime.extend([entry["node"] for entry in r.json().get("data", [])])
            else:
                print(f"[ERROR] {r.status_code} - {r.text}")
                break
        except (RequestException, SSLError) as e:
            print(f"[WARN] Network/SSL error during fetch_ranking offset {offset}: {e}")
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
        try:
            r = requests.get(url, headers=headers, params=params, timeout=45)
            if r.status_code == 200:
                data = r.json()
                all_anime.extend([entry["node"] for entry in data.get("data", [])])
                url = data.get("paging", {}).get("next")
                params = {}
            else:
                print(f"[ERROR] {r.status_code} - {r.text}")
                break
        except (RequestException, SSLError) as e:
            print(f"[WARN] Network/SSL error during fetch_season {year} {season}: {e}")
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
            try:
                r = requests.get(url, headers=headers, timeout=45)
                if r.status_code == 200:
                    data = r.json()
                    related_anime = data.get("related_anime", [])
                    break
                else:
                    print(f"[WARN] Could not fetch related_anime for {anime_id} "
                          f"({r.status_code}) attempt {attempt}/{retries}")
            except (RequestException, SSLError) as e:
                print(f"[WARN] Network/SSL error for {anime_id} attempt {attempt}/{retries}: {e}")
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
        try:
            r = requests.get(url, headers=headers, timeout=45)
            if r.status_code == 200:
                episodes = r.json().get("num_episodes") or 0
                episodes_cache[anime_id] = episodes
                time.sleep(0.5)
                return episodes
            else:
                print(f"[WARN] Could not fetch episodes for {anime_id} "
                      f"({r.status_code}) attempt {attempt}/{retries}")
        except (RequestException, SSLError) as e:
            print(f"[WARN] Network/SSL error for {anime_id} attempt {attempt}/{retries}: {e}")
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
                if alts.get("en"): all_titles.append(alts["en"])
                if alts.get("ja"): all_titles.append(alts["ja"])
                if isinstance(alts.get("synonyms"), list):
                    all_titles.extend(alts["synonyms"])
            all_titles = list({t.strip() for t in all_titles if t and t.strip()})

            grouped_data[root_id] = existing_data.get(root_id, {
                "id": root_id,
                "title": anime_title if anime_id == root_id else None,
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
            grouped_data[root_id]["title"] = anime_title

        if i % 50 == 0 or i == total:
            print(f"[INFO] Processed {i}/{total} anime ({(i/total)*100:.1f}%)")

    for root_id, entry in grouped_data.items():
        all_child_ids = entry["children_ids"]
        for cid in all_child_ids:
            get_episodes_count(cid, token)
        entry["total_episodes"] = sum(episodes_cache[cid] for cid in all_child_ids)
        existing_data[root_id] = entry

    return existing_data

# ---------- Embeddings ----------
def embed_batch(texts):
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [e.embedding for e in resp.data]

# ---------- Main ----------
if __name__ == "__main__":
    token = get_access_token()

    # Load existing DB
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        existing_data = {row["id"]: row for row in conn.execute("SELECT * FROM anime")}

    print(f"[INFO] Loaded {len(existing_data)} existing entries from DB.")

    # Fetch MAL
    fetched = []
    fetched.extend(fetch_ranking("bypopularity", 2000, token))

    now = datetime.now()
    current_year = now.year
    current_month = now.month
    current_season = "winter" if current_month <= 3 else "spring" if current_month <= 6 else "summer" if current_month <= 9 else "fall"
    prev_season = "fall" if current_season == "winter" else "winter" if current_season == "spring" else "spring" if current_season == "summer" else "summer"
    prev_year = current_year - 1 if current_season == "winter" else current_year

    fetched.extend(fetch_season(current_year, current_season, token))
    fetched.extend(fetch_season(prev_year, prev_season, token))

    print(f"[INFO] Total fetched {len(fetched)} entries")

    # Filter: new or airing
    fetched_unique = {}
    for a in fetched:
        aid = a["id"]
        status = (a.get("status") or "").lower()
        if aid not in existing_data or status == "currently_airing":
            fetched_unique[aid] = a

    print(f"[INFO] {len(fetched_unique)} anime need update (new or airing).")

    # Build + merge
    updated_data = build_grouped_db(fetched_unique.values(), existing_data, token)
    anime_list = [updated_data[aid] for aid in fetched_unique]

    # Embeddings
    print("[INFO] Generating embeddings...")
    batch_size = 100
    for i in range(0, len(anime_list), batch_size):
        batch = anime_list[i:i+batch_size]
        texts = [a.get("synopsis") or "N/A" for a in batch]
        try:
            embeddings = embed_batch(texts)
            for a, emb in zip(batch, embeddings):
                a["embedding"] = emb
        except Exception as e:
            print(f"[ERROR] Embedding batch {i//batch_size+1}: {e}")

    # Upsert into Postgres
    upsert_sql = """
    INSERT INTO anime (id, title, all_titles, main_picture, tags, synopsis, rating,
                       is_nsfw, total_episodes, embedding)
    VALUES (%(id)s, %(title)s, %(all_titles)s, %(main_picture)s, %(tags)s,
            %(synopsis)s, %(rating)s, %(is_nsfw)s, %(total_episodes)s, %(embedding)s)
    ON CONFLICT (id) DO UPDATE SET
      title = EXCLUDED.title,
      all_titles = EXCLUDED.all_titles,
      main_picture = EXCLUDED.main_picture,
      tags = EXCLUDED.tags,
      synopsis = EXCLUDED.synopsis,
      rating = EXCLUDED.rating,
      is_nsfw = EXCLUDED.is_nsfw,
      total_episodes = EXCLUDED.total_episodes,
      embedding = EXCLUDED.embedding;
    """

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for i in range(0, len(anime_list), 50):
                cur.executemany(upsert_sql, anime_list[i:i+50])
                conn.commit()
                print(f"[INFO] Upserted {i+50}/{len(anime_list)}")

    # Save backup JSON snapshot
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(list(updated_data.values()), f, indent=2, ensure_ascii=False)
    print(f"[INFO] Backup JSON saved to {BACKUP_FILE}")

    print(f"Finished update: {len(fetched_unique)} anime updated/inserted, {len(existing_data)-len(fetched_unique)} skipped.")
