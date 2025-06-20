try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
from pymongo import MongoClient
import logging
import os

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

# Configure basic logging to logs directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log")),
        logging.StreamHandler(),
    ],
)
