from typing import List, Dict, Any
from datetime import datetime
from bson import ObjectId
from core.config import db

# Collections
kw_coll = db["keyword_queue"]
reqs_coll = db["search_requests"]

def seed_defaults(default_keywords: List[str]):
    """Seed the queue with default keywords if not already present"""
    for keyword in default_keywords:
        kw_coll.update_one(
            {"keyword": keyword},
            {"$setOnInsert": {"keyword": keyword, "scraped": False, "created_at": datetime.utcnow()}},
            upsert=True
        )

def get_all_keywords() -> List[Dict[str, Any]]:
    """Retrieve all keywords in the queue"""
    return list(kw_coll.find())

def get_pending_keywords() -> List[str]:
    """Retrieve keywords that haven't been scraped yet"""
    cursor = kw_coll.find({"scraped": False}, {"keyword": 1})
    return [doc["keyword"] for doc in cursor]

def mark_scraped(keyword: str):
    """Mark a keyword as scraped"""
    kw_coll.update_one(
        {"keyword": keyword},
        {"$set": {"scraped": True, "scraped_at": datetime.utcnow()}}
    )

def enqueue(keyword: str) -> Dict[str, Any]:
    """Add a new keyword to the queue (upsert)"""
    result = kw_coll.find_one_and_update(
        {"keyword": keyword},
        {"$setOnInsert": {"keyword": keyword, "scraped": False, "created_at": datetime.utcnow()}},
        upsert=True,
        return_document=True
    )
    return result

def add_request(user_id: ObjectId, keyword: str):
    """Log that a user searched for a keyword but got no results"""
    # Check if there's already a pending request for this user/keyword
    existing = reqs_coll.find_one({
        "user_id": user_id,
        "keyword": keyword,
        "notified": False
    })
    
    if not existing:
        reqs_coll.insert_one({
            "user_id": user_id,
            "keyword": keyword,
            "requested_at": datetime.utcnow(),
            "notified": False
        })

def get_pending() -> List[Dict[str, Any]]:
    """Retrieve all search requests that haven't been notified yet"""
    return list(reqs_coll.find({"notified": False}))

def mark_notified(request_id: ObjectId):
    """Mark a search request as notified"""
    reqs_coll.update_one(
        {"_id": request_id},
        {"$set": {"notified": True, "notified_at": datetime.utcnow()}}
    )
