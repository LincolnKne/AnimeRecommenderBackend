from fastapi import APIRouter, HTTPException
from time import time
import json
from ..models.schemas import RecommendRequest, ScoredAnime, Anime, RecommendReason
from ..services.data_loader import load_anime_data, get_by_ids, get_by_titles
from ..services.openai_preference_parser import parse_preferences
from ..recommender.hybrid_recommender import score_candidates
from sentence_transformers import SentenceTransformer
import numpy as np
from sentence_transformers import SentenceTransformer
_model = None  # global cache

router = APIRouter()
_recommend_cache = {}
CACHE_TTL = 60  # seconds

def get_model():
    global _model
    if _model is None:
        print("Loading SentenceTransformer model...", flush=True)
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Model loaded.", flush=True)
    return _model

@router.post("/recommend", response_model=list[ScoredAnime])
def recommend(req: RecommendRequest):
    return _generate_recommendations(req, endpoint="recommend")

@router.post("/recommend/more", response_model=list[ScoredAnime])
def recommend_more(req: RecommendRequest):
    return _generate_recommendations(req, endpoint="recommend_more")

def _generate_recommendations(req: RecommendRequest, endpoint: str):
    cache_key = f"{endpoint}:{json.dumps(req.dict(), sort_keys=True)}"
    now = time()

    # Cache hit
    if cache_key in _recommend_cache:
        ts, cached_result = _recommend_cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached_result

    all_anime = load_anime_data()
    all_ids = {a["id"] for a in all_anime}

    # ------------ Handle free-text query with OpenAI ------------
    if req.query:
        parsed = parse_preferences(req.query, nsfw_ok=req.nsfw_ok)

        # Titles are now plain strings, get_by_titles handles matching against all_titles
        liked_ids_from_titles = get_by_titles(parsed.get("liked_titles", []))
        disliked_ids_from_titles = get_by_titles(parsed.get("disliked_titles", []))

        req.liked_ids = list(set(req.liked_ids + liked_ids_from_titles))
        req.disliked_ids = list(set(req.disliked_ids + disliked_ids_from_titles))
        req.moods = list(set(req.moods + parsed.get("mapped_tags", [])))
        req.semantic_query = " ".join(parsed.get("semantic_moods", []))

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

    # ----------- Blend semantic moods into embedding similarity ------------
    query_embedding = None
    if req.semantic_query:
        model = get_model()
        query_embedding = model.encode(req.semantic_query)

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
    return response
