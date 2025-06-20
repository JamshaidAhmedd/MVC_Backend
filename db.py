# db.py
from pymongo import MongoClient
from core.config import settings
from models.user_models import UserInDB

client = MongoClient(settings.MONGO_URI)
db = client["course_app"]
users_col = db["users"]

def get_user_by_username(username: str) -> UserInDB | None:
    doc = users_col.find_one({"username": username})
    return UserInDB(**doc) if doc else None

def get_user_by_id(uid: str) -> UserInDB | None:
    from bson import ObjectId
    doc = users_col.find_one({"_id": ObjectId(uid)})
    return UserInDB(**doc) if doc else None
