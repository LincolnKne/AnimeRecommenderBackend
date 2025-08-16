from typing import List, Dict, Any, Set
import numpy as np

def _tags(anime: Dict[str, Any]) -> Set[str]:
    return {t.lower() for t in (anime.get("tags") or [])}

def _cosine_sim(v1: list[float], v2: list[float]) -> float:
    v1 = np.array(v1)
    v2 = np.array(v2)
    denom = (np.linalg.norm(v1) * np.linalg.norm(v2))
    return float(np.dot(v1, v2) / denom) if denom else 0.0

def score_candidates(
    all_items: List[Dict[str, Any]],
    liked: List[Dict[str, Any]],
    disliked: List[Dict[str, Any]],
    moods: List[str],
    nsfw_ok: bool,
    query_embedding=None,
    tag_weight: float = 0.25,
    liked_weight: float = 0.25,
    query_weight: float = 0.40
) -> List[tuple[Dict[str, Any], float, list[str]]]:

    mood_set = {m.lower() for m in moods}
    liked_tag_pool = set().union(*[_tags(a) for a in liked]) if liked else set()
    disliked_tag_pool = set().union(*[_tags(a) for a in disliked]) if disliked else set()

    # Average embedding for liked anime
    liked_embeddings = [a.get("embedding") for a in liked if a.get("embedding")]
    avg_liked_emb = np.mean(liked_embeddings, axis=0) if liked_embeddings else None

    out = []
    for anime in all_items:
        if (not nsfw_ok) and anime.get("is_nsfw"):
            continue

        tags = _tags(anime)
        if not tags:
            continue

        # Tag score
        overlap = liked_tag_pool & tags
        tag_score = len(overlap) / len(liked_tag_pool) if liked_tag_pool else 0.0

        bad_overlap = disliked_tag_pool & tags
        tag_score -= 0.15 * len(bad_overlap)

        # Mood boost
        tag_score += 0.05 * len({m for m in mood_set if m in tags})

        # Liked anime synopsis score
        liked_synopsis_score = 0.0
        if avg_liked_emb is not None and anime.get("embedding"):
            liked_synopsis_score = _cosine_sim(avg_liked_emb, anime["embedding"])

        # Query synopsis score
        query_synopsis_score = 0.0
        if query_embedding is not None and anime.get("embedding"):
            query_synopsis_score = _cosine_sim(query_embedding, anime["embedding"])

        # Blend scores
        final_score = (
            (tag_score * tag_weight) +
            (liked_synopsis_score * liked_weight) +
            (query_synopsis_score * query_weight)
        )

        if final_score > 0:
            out.append((anime, final_score, sorted(overlap)))

    # Normalize scores
    if out:
        max_score = max(s for _, s, _ in out)
        if max_score > 0:
            out = [(a, s / max_score, ol) for a, s, ol in out]

    out.sort(key=lambda x: x[1], reverse=True)
    return out
