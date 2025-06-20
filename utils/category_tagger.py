#!/usr/bin/env python3
"""
category_tagger.py

Score-thresholded category tagger:

  • Only tag courses whose textScore ≥ TAG_THRESHOLD × max_score
  • Backfill all categories in one pass
  • Watch for category changes and re-tag incrementally
"""

import os
import logging
from pymongo import MongoClient, TEXT
from pymongo.errors import OperationFailure

# ── CONFIG ────────────────────────────────────────────────────────────────
MONGO_URI      = os.getenv(
    "MONGO_URI",
    "mongodb+srv://admin:admin@cluster0.hpskmws.mongodb.net/course_app?retryWrites=true&w=majority"
)
TEXT_INDEX     = "CourseTextIndex"
# how “deep” into the relevance list to go (0.2 = top 20%)
TAG_THRESHOLD  = float(os.getenv("TAG_THRESHOLD", "0.2"))
# ── END CONFIG ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("category_tagger")


def ensure_text_index():
    """
    Ensure a consistent text-index on courses(title, description, reviews.text).
    Any other text indexes are dropped first.
    """
    client = MongoClient(MONGO_URI)
    coll   = client["course_app"]["courses"]

    # drop old text indexes
    for idx in coll.list_indexes():
        # if any key in the index is of type text, and it's not our desired one, drop it
        if any(v == "text" for v in idx["key"].values()) and idx["name"] != TEXT_INDEX:
            try:
                coll.drop_index(idx["name"])
                log.info(f"Dropped old text index: {idx['name']}")
            except OperationFailure as e:
                log.warning(f"Could not drop {idx['name']}: {e}")

    # create our canonical index
    coll.create_index(
        [("title", TEXT), ("description", TEXT), ("reviews.text", TEXT)],
        name=TEXT_INDEX
    )
    log.info(f"Ensured text index '{TEXT_INDEX}'")


def retag_all():
    """
    Backfill categories: for each category, re-compute which courses
    have textScore ≥ TAG_THRESHOLD × max_score and tag only those.
    """
    log.info(f"Backfilling categories with score threshold {TAG_THRESHOLD:.2f}…")
    client     = MongoClient(MONGO_URI)
    db         = client["course_app"]
    courses    = db["courses"]
    categories = db["categories"]

    ensure_text_index()

    for cat in categories.find():
        name = cat.get("name")
        kws  = cat.get("keywords", [])
        if not name or not kws:
            continue

        # 1) clear old tags
        courses.update_many({}, {"$pull": {"categories": name}})

        # 2) text-search on all keywords
        search_str = " ".join(kws)
        cursor = courses.find(
            {"$text": {"$search": search_str}},
            {"score": {"$meta": "textScore"}, "course_id": 1}
        ).sort([("score", {"$meta": "textScore"})])

        docs = list(cursor)
        if not docs:
            log.info(f" • No matches for '{name}'")
            continue

        max_score = docs[0]["score"]
        thresh    = TAG_THRESHOLD * max_score
        tagged    = 0

        for d in docs:
            if d["score"] < thresh:
                break
            courses.update_one(
                {"course_id": d["course_id"]},
                {"$addToSet": {"categories": name}}
            )
            tagged += 1

        log.info(f" • Tagged {tagged} of {len(docs)} courses under '{name}'")

    log.info("Backfill complete.")


def watch_changes():
    """
    Watch `categories` change-stream and re-tag incrementally.
    Applies the same score-threshold logic.
    """
    log.info("Starting category change-stream watcher…")
    client     = MongoClient(MONGO_URI)
    db         = client["course_app"]
    courses    = db["courses"]
    categories = db["categories"]

    pipeline = [
        {"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}
    ]

    try:
        stream = categories.watch(pipeline)
    except Exception as e:
        log.error(f"Could not open change stream (is this a replica set?): {e}")
        return

    with stream:
        for change in stream:
            cid = change["documentKey"]["_id"]
            cat = categories.find_one({"_id": cid})
            if not cat:
                continue

            name = cat.get("name")
            kws  = cat.get("keywords", [])
            if not name:
                continue

            # 1) clear old tags
            courses.update_many({}, {"$pull": {"categories": name}})

            if not kws:
                continue

            # 2) text-search and threshold-tag
            search_str = " ".join(kws)
            cursor = courses.find(
                {"$text": {"$search": search_str}},
                {"score": {"$meta": "textScore"}, "course_id": 1}
            ).sort([("score", {"$meta": "textScore"})])

            docs = list(cursor)
            if not docs:
                continue

            max_score = docs[0]["score"]
            thresh    = TAG_THRESHOLD * max_score
            count     = 0

            for d in docs:
                if d["score"] < thresh:
                    break
                courses.update_one(
                    {"course_id": d["course_id"]},
                    {"$addToSet": {"categories": name}}
                )
                count += 1

            log.info(f"Re-tagged {count} courses for category '{name}'")