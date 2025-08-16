import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Path to your anime data
DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "anime_data.json"

def main():
    print("Loading anime data...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Loading embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    updated = []
    for anime in data:
        synopsis = anime.get("synopsis") or ""
        # Create vector embedding for the synopsis
        embedding = model.encode(synopsis).tolist()
        anime["embedding"] = embedding
        updated.append(anime)

    print("Saving updated dataset with embeddings...")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print("Done! Added embeddings for", len(updated), "anime.")

if __name__ == "__main__":
    main()
