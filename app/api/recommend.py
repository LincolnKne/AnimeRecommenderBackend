from fastapi import APIRouter, HTTPException
from time import time
import json
import numpy as np
from openai import OpenAI

from ..models.schemas import RecommendRequest, ScoredAnime, Anime, RecommendReason
from ..services.db_loader import load_anime_data, get_by_ids, get_by_titles
from ..services.openai_preference_parser import parse_preferences
from ..recommender.hybrid_recommender import score_candidates

router = APIRouter()
_recommend_cache = {}
CACHE_TTL = 60  # seconds

client = OpenAI()

@router.post("/recommend", response_model=list[ScoredAnime])
def recommend(req: RecommendRequest):
    return _generate_recommendations(req, endpoint="recommend")

@router.post("/recommend/more", response_model=list[ScoredAnime])
def recommend_more(req: RecommendRequest):
    return _generate_recommendations(req, endpoint="recommend_more")

def _generate_recommendations(req: RecommendRequest, endpoint: str):
    cache_key = f"{endpoint}:{json.dumps(req.dict(), sort_keys=True)}"
    now = time()

    if cache_key in _recommend_cache:
        ts, cached_result = _recommend_cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached_result

    all_anime = load_anime_data()
    all_ids = {a["id"] for a in all_anime}

    # ------------ Handle free-text query with OpenAI ------------
    if req.query:
        parsed = parse_preferences(req.query, nsfw_ok=req.nsfw_ok)

        # TEMP LOGS
        print("=== Parsed Preferences ===", flush=True)
        print(json.dumps(parsed, indent=2), flush=True)

        liked_ids_from_titles = get_by_titles(parsed.get("liked_titles", []))
        disliked_ids_from_titles = get_by_titles(parsed.get("disliked_titles", []))

        # TEMP LOGS
        print(f"Liked title matches → {liked_ids_from_titles}", flush=True)
        print(f"Disliked title matches → {disliked_ids_from_titles}", flush=True)

        req.liked_ids = list(set(req.liked_ids + liked_ids_from_titles))
        req.disliked_ids = list(set(req.disliked_ids + disliked_ids_from_titles))
        req.moods = list(set(req.moods + parsed.get("mapped_tags", [])))
        req.semantic_query = " ".join(parsed.get("semantic_moods", []))

        # TEMP LOG
        print(f"Final semantic query: '{req.semantic_query}'", flush=True)

    # Validate IDs
    invalid_ids = [i for i in req.liked_ids + req.disliked_ids if i not in all_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid anime IDs: {invalid_ids}"
        )

    # Remove excluded titles from candidates
    exclude_ids = set(req.liked_ids) | set(req.disliked_ids) | set(req.exclude_ids)
    candidates = [a for a in all_anime if a["id"] not in exclude_ids]

    liked = get_by_ids(req.liked_ids)
    disliked = get_by_ids(req.disliked_ids)

    # ----------- Query Embedding (via OpenAI embeddings) ------------
    query_embedding = None
    if req.semantic_query:
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=req.semantic_query
            )
            query_embedding = np.array(response.data[0].embedding, dtype=float)

            # TEMP LOG
            print(f"Query embedding length: {len(query_embedding)}", flush=True)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    scored = score_candidates(
        all_items=candidates,
        liked=liked,
        disliked=disliked,
        moods=req.moods,
        nsfw_ok=req.nsfw_ok,
        query_embedding=query_embedding,
        tag_weight=0.35,
        liked_weight=0.25,
        query_weight=0.40
    )

    response: list[ScoredAnime] = []
    for anime, score, overlap in scored[:req.limit]:
        response.append(
            ScoredAnime(
                anime=Anime(**{k: anime.get(k) for k in [
                    "id", "title", "all_titles", "main_picture", "tags", "synopsis",
                    "rating", "is_nsfw", "total_episodes"
                ]}),
                score=round(float(score), 4),
                reason=RecommendReason(
                    overlap_tags=overlap,
                    note="Matched using tag overlap, liked anime similarity, and query similarity."
                )
            )
        )

    _recommend_cache[cache_key] = (now, response)

    # TEMP LOG
    print(f"Returned {len(response)} recommendations", flush=True)

    return response
