"""Sentiment analysis utilities for course reviews."""

import logging
from datetime import datetime
from typing import List

from textblob import TextBlob
from pymongo import TEXT, UpdateOne

from core.config import db, settings

log = logging.getLogger(__name__)


def score_new_reviews() -> int:
    """Score reviews that don't yet have sentiment."""
    pipeline = [
        {"$unwind": "$reviews"},
        {"$match": {"reviews.sentiment_score": {"$exists": False}}},
        {"$project": {"course_id": 1, "reviews.review_id": 1, "reviews.text": 1}},
    ]
    updates = []
    for doc in db["courses"].aggregate(pipeline):
        text = doc["reviews"]["text"] or ""
        score = TextBlob(text).sentiment.polarity
        updates.append(
            UpdateOne(
                {"course_id": doc["course_id"], "reviews.review_id": doc["reviews"]["review_id"]},
                {"$set": {"reviews.$.sentiment_score": score}},
            )
        )
    if updates:
        res = db["courses"].bulk_write(updates)
        log.info("Scored %s new reviews", res.modified_count)
        return res.modified_count
    return 0


def aggregate_course_metrics() -> int:
    """Compute average and smoothed sentiment for each course."""
    all_scores: List[float] = []
    for c in db["courses"].find({}, {"reviews.sentiment_score": 1}):
        for r in c.get("reviews", []):
            if "sentiment_score" in r:
                all_scores.append(r["sentiment_score"])
    global_mean = sum(all_scores) / len(all_scores) if all_scores else 0.0
    updates = []
    for course in db["courses"].find({}, {"course_id": 1, "reviews.sentiment_score": 1}):
        scores = [r["sentiment_score"] for r in course.get("reviews", []) if "sentiment_score" in r]
        n = len(scores)
        avg = sum(scores) / n if n else 0.0
        smooth = ((settings.PSEUDOCOUNT * global_mean) + sum(scores)) / (settings.PSEUDOCOUNT + n) if (settings.PSEUDOCOUNT + n) else global_mean
        updates.append(
            UpdateOne(
                {"course_id": course["course_id"]},
                {"$set": {"num_reviews": n, "avg_sentiment": avg, "smoothed_sentiment": smooth}},
            )
        )
    if updates:
        res = db["courses"].bulk_write(updates)
        log.info("Updated sentiment metrics for %s courses", res.modified_count)
        return res.modified_count
    return 0


def rebuild_text_index() -> None:
    """Rebuild the text index on the courses collection."""
    coll = db["courses"]
    for idx in coll.list_indexes():
        if "text" in idx["key"].values():
            coll.drop_index(idx["name"])
    coll.create_index([("title", TEXT), ("description", TEXT), ("reviews.text", TEXT)], name="CourseTextIndex")


def run_sentiment_enrichment() -> None:
    """Run the full sentiment enrichment pipeline."""
    log.info("Starting sentiment enrichment...")
    score_new_reviews()
    aggregate_course_metrics()
    rebuild_text_index()
    log.info("Sentiment enrichment complete")
