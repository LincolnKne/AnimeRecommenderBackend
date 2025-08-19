import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from .db_loader import load_anime_data

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load tags dynamically from anime_data.json
def load_known_tags(nsfw_ok=False):
    data = load_anime_data()
    tags_map = {}
    NSFW_TAGS = {"hentai", "ecchi", "magical sex shift", "erotica"}
    for anime in data:
        for tag in anime.get("tags", []):
            tag_clean = tag.strip()
            tag_lower = tag_clean.lower()
            if not nsfw_ok and tag_lower in NSFW_TAGS:
                continue
            if tag_lower not in tags_map:
                tags_map[tag_lower] = tag_clean
    return sorted(tags_map.values(), key=lambda t: t.lower())

def parse_preferences(user_query: str, nsfw_ok=False):
    known_tags = load_known_tags(nsfw_ok)
    
    system_prompt = f"""
    You are an anime preference translator. You understand any language.
    Map the user's description into:
    - liked_titles: list of plain strings for each anime mentioned as liked
    - disliked_titles: list of plain strings for each anime mentioned as disliked
    - mapped_tags: closest known tags from this list: {', '.join(known_tags)}
    - semantic_moods: original abstract moods for semantic matching (always include at least one, even if guessed from context)

    Rules:
    - Do NOT translate titles into other languages.
    - Use exactly what the user wrote for titles (even if not in English).
    - Only output valid JSON, no explanations or extra text.
    """

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        temperature=0.3,
        max_tokens=250
    )

    try:
        parsed = json.loads(resp.choices[0].message.content)

        # --- Fallback: if GPT didn’t produce semantic_moods, use the full query ---
        if not parsed.get("semantic_moods"):
            parsed["semantic_moods"] = [user_query]

        return parsed
    except json.JSONDecodeError:
        return {
            "liked_titles": [],
            "disliked_titles": [],
            "mapped_tags": [],
            "semantic_moods": [user_query]  # always embed something
        }
