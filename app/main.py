from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import recommend, search, anime, tags, metadata, config
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Anime Recommender API", version="0.1.0")

origins = [
    "https://animerecommend.com", 
    "https://www.animerecommend.com", 
    "https://animerecommenderbackend.onrender.com",  # optional, for testing
]

# Allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Change to frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register endpoints
app.include_router(recommend.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(anime.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(metadata.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
