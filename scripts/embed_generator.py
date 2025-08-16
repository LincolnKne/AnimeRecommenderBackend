import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load env variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Path to your anime data
DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "anime_data.json"

BATCH_SIZE = 100  # safe batch size for OpenAI

def main():
    print("Loading anime data...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Scanning for missing embeddings...")
    to_embed = [(idx, a["synopsis"]) for idx, a in enumerate(data)
                if not a.get("embedding") and a.get("synopsis")]

    print(f"Found {len(to_embed)} anime needing embeddings.")

    for i in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[i:i+BATCH_SIZE]
        texts = [s for _, s in batch]

        print(f"Embedding batch {i//BATCH_SIZE+1} of {len(to_embed)//BATCH_SIZE+1} "
              f"({len(texts)} items)...")

        try:
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=texts
            )
            embeddings = [e.embedding for e in resp.data]

            # Save embeddings back into dataset
            for (idx, _), emb in zip(batch, embeddings):
                data[idx]["embedding"] = emb

        except Exception as e:
            print(f"[ERROR] Failed batch {i//BATCH_SIZE+1}: {e}")

    # Save dataset with new embeddings
    print("Saving updated dataset...")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Done! Updated embeddings for missing entries only.")

if __name__ == "__main__":
    main()
