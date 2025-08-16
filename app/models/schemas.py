from pydantic import BaseModel
from typing import List, Optional

class Anime(BaseModel):
    id: int
    title: Optional[str]
    main_picture: Optional[dict] = None
    tags: List[str] = []
    synopsis: Optional[str] = None
    rating: Optional[str] = None
    is_nsfw: bool = False
    total_episodes: int = 0

class RecommendRequest(BaseModel):
    liked_ids: List[int] = []
    disliked_ids: List[int] = []
    moods: List[str] = []
    exclude_ids: List[int] = []
    nsfw_ok: bool = False
    limit: int = 10
    query: Optional[str] = None           # The free-text user query
    semantic_query: Optional[str] = None  # Internal field populated by parser

class RecommendReason(BaseModel):
    overlap_tags: List[str] = []
    note: Optional[str] = None

class ScoredAnime(BaseModel):
    anime: Anime
    score: float
    reason: RecommendReason
