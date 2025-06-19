try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
from pymongo import MongoClient

class Settings(BaseSettings):
    MONGO_URI: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_HOURS: int = 4
    ALPHA: float = 0.7  # Text relevance weight
    BETA: float = 0.2   # Popularity weight
    TAG_THRESHOLD: float = 0.2  # Category tagging threshold
    PSEUDOCOUNT: int = 10  # For Bayesian smoothing
    # Optionally other settings like DB_NAME, etc.

    class Config:
        env_file = ".env"

settings = Settings()

# MongoDB client and database
client = MongoClient(settings.MONGO_URI)
db = client["course_app"]  # database name is fixed as 'course_app'
