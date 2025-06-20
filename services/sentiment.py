#!/usr/bin/env python3
"""
sentiment_enrichment.py

Phase 2 – Data Processing & Enrichment

  1) Score reviews via TextBlob if missing `sentiment_score`.
  2) Compute per‐course metrics with Bayesian smoothing:
       - num_reviews         (int)
       - avg_sentiment       (float)
       - smoothed_sentiment  (float)
  3) Rebuild full‐text index for search.
"""

import sys, logging
from textblob import TextBlob
from pymongo import MongoClient, UpdateOne, TEXT

# ── CONFIG ────────────────────────────────────────────────────────
MONGO_URI    = "mongodb+srv://admin:admin@cluster0.hpskmws.mongodb.net/course_app?retryWrites=true&w=majority"
PSEUDOCOUNT  = 10    # Adjust up to pull 1‐review courses closer to global mean
TEXT_INDEX   = "CourseTextIndex"
# ── END CONFIG ────────────────────────────────────────────────────

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger()

def connect():
    try:
        client = MongoClient(MONGO_URI)
        db     = client["course_app"]
        log.info("✅ Connected to MongoDB Atlas")
        return db["courses"]
    except Exception as e:
        log.error("❌ MongoDB connection failed: %s", e)
        sys.exit(1)

def score_reviews(courses):
    """Step 1: Add sentiment_score to reviews that lack it."""
    log.info("1) Scoring new reviews…")
    pipeline = [
        {"$unwind":"$reviews"},
        {"$match":{"reviews.sentiment_score":{"$exists":False}}},
        {"$project":{"course_id":1,"reviews.review_id":1,"reviews.text":1}}
    ]
    ops, cnt = [], 0
    for doc in courses.aggregate(pipeline):
        cid = doc["course_id"]
        rid = doc["reviews"]["review_id"]
        txt = doc["reviews"]["text"] or ""
        score = TextBlob(txt).sentiment.polarity
        ops.append(UpdateOne(
            {"course_id":cid, "reviews.review_id":rid},
            {"$set":{"reviews.$.sentiment_score": score}}
        ))
        cnt += 1
    if ops:
        res = courses.bulk_write(ops)
        log.info("   • Scored %d reviews → updated %d entries", cnt, res.modified_count)
    else:
        log.info("   • No new reviews to score")

def aggregate(courses):
    """Step 2: Compute num_reviews, avg_sentiment, smoothed_sentiment."""
    log.info("2) Aggregating course metrics…")
    # (a) Global mean
    all_scores = []
    for c in courses.find({},{"reviews.sentiment_score":1}):
        all_scores += [r["sentiment_score"] for r in c.get("reviews",[]) if "sentiment_score" in r]
    m = sum(all_scores)/len(all_scores) if all_scores else 0.0
    log.info("   • Global mean m=%.4f, pseudocount C=%d", m, PSEUDOCOUNT)

    ops = []
    for c in courses.find({},{"course_id":1,"reviews.sentiment_score":1}):
        cid = c["course_id"]
        ss  = [r["sentiment_score"] for r in c.get("reviews",[]) if "sentiment_score" in r]
        n   = len(ss)
        raw = sum(ss)/n if n else 0.0
        smooth = (PSEUDOCOUNT*m + sum(ss)) / (PSEUDOCOUNT + n) if (PSEUDOCOUNT + n) else m
        ops.append(UpdateOne(
            {"course_id":cid},
            {"$set":{
                "num_reviews":         n,
                "avg_sentiment":       raw,
                "smoothed_sentiment":  smooth
            }}
        ))
    if ops:
        res = courses.bulk_write(ops)
        log.info("   • Updated metrics on %d courses", res.modified_count)
    else:
        log.warning("   • No courses found for aggregation")

def rebuild_index(courses):
    """Step 3: Drop & recreate text index on title, description, reviews.text."""
    log.info("3) Rebuilding text index…")
    for idx in courses.list_indexes():
        if any(v=="text" for v in idx["key"].values()):
            courses.drop_index(idx["name"])
            log.info("   • Dropped old index %s", idx["name"])
    courses.create_index(
        [("title",TEXT),("description",TEXT),("reviews.text",TEXT)],
        name=TEXT_INDEX
    )
    log.info("   • Created text index '%s'", TEXT_INDEX)

def main():
    log.info("=== Phase 2 Enrichment Start ===")
    courses = connect()
    score_reviews(courses)
    aggregate(courses)
    rebuild_index(courses)
    log.info("🎉 Phase 2 complete!")
    sys.exit(0)

if __name__=="__main__":
    main()
