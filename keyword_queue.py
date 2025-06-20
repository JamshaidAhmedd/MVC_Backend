from pymongo import MongoClient, ReturnDocument
import logging
import os
from datetime import datetime

# ── CONFIG ───────────────────────────────────────────────────────
MONGO_URI = "mongodb+srv://admin:admin@cluster0.hpskmws.mongodb.net/course_app?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
kw_coll = client.course_app.keyword_queue
db        = client["course_app"]
reqs_col  = db["search_requests"]
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
# ── END CONFIG ───────────────────────────────────────────────────

def seed_defaults(defaults: list[str]):
    """
    Populate the keyword queue with an initial set of search terms.
    Only inserts those not already present.
    """
    existing = {d["keyword"] for d in kw_coll.find({}, {"keyword":1})}
    to_insert = [{"keyword": kw, "scraped": False} for kw in defaults if kw not in existing]
    if to_insert:
        result = kw_coll.insert_many(to_insert)
        log.info(f"Inserted {len(result.inserted_ids)} new keywords into queue.")
    else:
        log.info("No new keywords to seed.")


def get_all_keywords() -> list[str]:
    """
    Return all keywords (scraped or not) from the queue.
    """
    return [d["keyword"] for d in kw_coll.find({}, {"keyword":1})]


def get_pending_keywords() -> list[str]:
    """
    Return only those keywords not yet scraped.
    """
    return [d["keyword"] for d in kw_coll.find({"scraped": False}, {"keyword":1})]


def mark_scraped(keyword: str):
    """
    Mark a keyword as having been scraped successfully.
    """
    doc = kw_coll.find_one_and_update(
        {"keyword": keyword},
        {"$set": {"scraped": True}},
        return_document=ReturnDocument.AFTER
    )
    if doc:
        log.info(f"Marked '{keyword}' as scraped.")
    else:
        log.warning(f"Keyword '{keyword}' not found in queue.")


def enqueue(keyword: str):
    """
    Add a new keyword to the queue if it does not already exist.
    Returns the document state after upsert.
    """
    doc = kw_coll.find_one_and_update(
        {"keyword": keyword},
        {"$setOnInsert": {"scraped": False}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    log.info(f"Enqueued keyword '{keyword}' (scraped={doc['scraped']}).")
    return doc


def add_request(user_oid, keyword: str):
    # avoid dupes
    if not reqs_col.find_one({"user_id": user_oid, "keyword": keyword, "notified": False}):
        reqs_col.insert_one({
            "user_id": user_oid,
            "keyword": keyword,
            "requested_at": datetime.utcnow(),
            "notified": False
        })


def get_pending():
    return list(reqs_col.find({"notified": False}))


def mark_notified(req_id):
    reqs_col.update_one({"_id": req_id}, {"$set": {"notified": True}})
