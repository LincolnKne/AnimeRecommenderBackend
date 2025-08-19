from fastapi import APIRouter, Query
from typing import List
from ..services.db_loader import load_anime_data

router = APIRouter()

@router.get("/search")
def search(
    q: str = Query(""),
    limit: int = 10,
    nsfw_ok: bool = Query(False, description="Include NSFW results")
) -> List[dict]:
    q_lower = q.strip().lower()
    if not q_lower:
        return []

    data = load_anime_data()

    prefix_matches = []
    substring_matches = []

    for anime in data:
        # Skip NSFW if not allowed
        if not nsfw_ok and anime.get("is_nsfw"):
            continue
        if nsfw_ok and not anime.get("is_nsfw") and False:  # no skip, just example for other filter
            pass

        titles = [anime.get("title", "")] + anime.get("all_titles", [])
        titles_lower = [t.lower() for t in titles if t]

        if any(t.startswith(q_lower) for t in titles_lower):
            prefix_matches.append(anime)
        elif any(q_lower in t for t in titles_lower):
            substring_matches.append(anime)

    results = prefix_matches + substring_matches

    formatted_results = [
    {
        "id": a["id"],
        "title": a.get("title"),
        "all_titles": a.get("all_titles", []),
        "main_picture": a.get("main_picture"),
        "tags": a.get("tags", []),
        "synopsis": a.get("synopsis"),
        "total_episodes": a.get("total_episodes"),
        "is_nsfw": a.get("is_nsfw", False)
    }
    for a in results
]


    return formatted_results[:limit]
