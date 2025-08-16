import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load .env to get OPENAI_API_KEY
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Path to your anime data
DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "anime_data.json"

BATCH_SIZE = 100  # number of synopses per request

def chunks(lst, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def main():
    print("Loading anime data...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Collect synopses safely
    synopses = []
    for i, a in enumerate(data):
        synopsis = a.get("synopsis") or ""
        synopsis = synopsis.strip()
        if not synopsis:
            synopsis = "N/A"  # avoid empty input
        synopses.append((i, synopsis))

    print(f"Generating embeddings for {len(synopses)} anime in batches of {BATCH_SIZE}...")

    for batch_num, batch in enumerate(chunks(synopses, BATCH_SIZE), 1):
        texts = [s for _, s in batch]

        try:
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=texts
            )
        except Exception as e:
            print(f"❌ Error on batch {batch_num}: {e}")
            continue

        # Assign embeddings back into data
        for (idx, _), emb in zip(batch, resp.data):
            data[idx]["embedding"] = emb.embedding

        print(f"✅ Processed batch {batch_num} ({len(batch)} items)")

    # Save updated dataset
    print("Saving updated dataset with OpenAI embeddings...")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("🎉 Done! Rebuilt embeddings for", len(data), "anime.")

if __name__ == "__main__":
    main()
