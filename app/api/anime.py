from fastapi import APIRouter, HTTPException
from ..services.db_loader import load_anime_data

router = APIRouter()

@router.get("/anime/{anime_id}")
def get_anime(anime_id: int):
    # Load data
    data = load_anime_data()

    # Find anime by ID
    for anime in data:
        if anime["id"] == anime_id:
            return anime

    # Not found
    raise HTTPException(status_code=404, detail="Anime not found")
