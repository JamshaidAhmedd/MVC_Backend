"""Utility functions for tagging courses with categories."""

import logging
import time
from typing import List
from pymongo import TEXT

from app.core.config import db, settings

TEXT_INDEX = "CourseTextIndex"
log = logging.getLogger(__name__)


def ensure_text_index() -> None:
    """Ensure the text index on the courses collection exists."""
    coll = db["courses"]
    for idx in coll.list_indexes():
        if "text" in idx["key"].values() and idx["name"] != TEXT_INDEX:
            coll.drop_index(idx["name"])
    coll.create_index(
        [("title", TEXT), ("description", TEXT), ("reviews.text", TEXT)],
        name=TEXT_INDEX,
    )
    log.info("Ensured text index '%s' exists", TEXT_INDEX)


def retag_all() -> None:
    """Recompute category tags for all courses."""
    ensure_text_index()
    coll_courses = db["courses"]
    for cat in db["categories"].find():
        name = cat["name"]
        keywords: List[str] = cat.get("keywords", [])
        if not keywords:
            continue
        search = " ".join(keywords)
        cursor = coll_courses.find({"$text": {"$search": search}}, {"score": {"$meta": "textScore"}})
        docs = list(cursor)
        if not docs:
            continue
        max_score = max(d.get("score", 0.0) for d in docs) or 1.0
        threshold = settings.TAG_THRESHOLD * max_score
        ids = [d["_id"] for d in docs if d.get("score", 0.0) >= threshold]
        if ids:
            coll_courses.update_many({"_id": {"$in": ids}}, {"$addToSet": {"categories": name}})
    log.info("Category retagging complete")


def watch_changes(poll_interval: int = 60) -> None:
    """Poll for new courses and tag them."""
    ensure_text_index()
    coll = db["courses"]
    last_count = coll.count_documents({})
    while True:
        time.sleep(poll_interval)
        new_count = coll.count_documents({})
        if new_count > last_count:
            retag_all()
            last_count = new_count
