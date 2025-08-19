import os, json
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Load .env to get DATABASE_URL
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))

# Path to your anime_data.json
DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "anime_data.json"

def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"anime_data.json not found at {DATA_PATH}")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[INFO] Loaded {len(data)} anime entries from JSON")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            upsert_sql = """
            INSERT INTO anime (
                id, title, all_titles, main_picture, tags, synopsis, rating,
                is_nsfw, total_episodes, children_ids, last_updated, embedding
            )
            VALUES (
                %(id)s, %(title)s, %(all_titles)s, %(main_picture)s, %(tags)s,
                %(synopsis)s, %(rating)s, %(is_nsfw)s, %(total_episodes)s,
                %(children_ids)s, %(last_updated)s, %(embedding)s
            )
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title,
              all_titles = EXCLUDED.all_titles,
              main_picture = EXCLUDED.main_picture,
              tags = EXCLUDED.tags,
              synopsis = EXCLUDED.synopsis,
              rating = EXCLUDED.rating,
              is_nsfw = EXCLUDED.is_nsfw,
              total_episodes = EXCLUDED.total_episodes,
              children_ids = EXCLUDED.children_ids,
              last_updated = EXCLUDED.last_updated,
              embedding = EXCLUDED.embedding;
            """

            batch_size = 50
            for i in range(0, len(data), batch_size):
                batch = data[i:i+batch_size]
                rows = []
                for a in batch:
                    row = {
                        "id": int(a["id"]),
                        "title": a.get("title"),
                        "all_titles": list({t for t in (a.get("all_titles") or []) if t}),
                        "main_picture": json.dumps(a.get("main_picture")) if a.get("main_picture") else None,
                        "tags": [t.lower() for t in (a.get("tags") or []) if t],
                        "synopsis": a.get("synopsis"),
                        "rating": a.get("rating"),
                        "is_nsfw": bool(a.get("is_nsfw", False)),
                        "total_episodes": int(a.get("total_episodes") or 0),
                        "children_ids": a.get("children_ids") or [],
                        "last_updated": a.get("last_updated"),
                        "embedding": a.get("embedding") or None
                    }
                    rows.append(row)

                cur.executemany(upsert_sql, rows)
                conn.commit()
                print(f"[INFO] Inserted/updated {i+len(batch)} / {len(data)}")

    print("✅ Import complete!")

if __name__ == "__main__":
    main()
