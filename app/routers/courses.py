from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
import math
from app.core import security
from app.core.config import db, settings
from app.models.course import CourseSummary, CourseDetail, Review
from app.utils import keyword_queue
from app.services import data_ingestion
import threading

router = APIRouter(tags=["courses"])

@router.get("/search", response_model=List[CourseSummary])
def search_courses(
    query: str = Query(..., min_length=1),
    category: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    top_k: int = Query(10, ge=1, le=100),
    current_user: Optional[dict] = Depends(security.get_current_user),
):
    """Search courses with optional category/provider filters."""

    filter_query: Dict[str, Any] = {"$text": {"$search": query}}
    if category:
        filter_query["categories"] = category
    if provider:
        filter_query["provider"] = provider

    cursor = db["courses"].find(
        filter_query,
        {
            "score": {"$meta": "textScore"},
            "course_id": 1,
            "title": 1,
            "smoothed_sentiment": 1,
            "num_reviews": 1,
        },
    ).sort([("score", {"$meta": "textScore"})]).limit(top_k * 5)
    docs = list(cursor)
    if not docs:
        keyword_queue.enqueue(query)
        if current_user:
            keyword_queue.add_request(current_user["_id"], query)
        threading.Thread(target=data_ingestion.run_ingestion_pipeline, daemon=True).start()
        return []
    # Compute max text score for normalization
    max_score = max(d.get("score", 0) for d in docs) or 1.0
    results = []
    for d in docs:
        text_norm = d["score"] / max_score
        sent = float(d.get("smoothed_sentiment") or 0.0)
        sent_norm = (sent + 1.0) / 2.0
        n = int(d.get("num_reviews") or 0)
        pop_weight = math.log(1 + n)
        # Weighted ranking formula combining text relevance, sentiment, and popularity
        ranking = settings.ALPHA * text_norm + (1 - settings.ALPHA) * sent_norm + settings.BETA * pop_weight
        results.append(CourseSummary(
            course_id=d["course_id"], title=d["title"],
            ranking_score=round(ranking, 4),
            text_norm=round(text_norm, 4),
            sent_norm=round(sent_norm, 4),
            pop_weight=round(pop_weight, 4),
            num_reviews=n,
            smoothed_sentiment=round(sent, 4)
        ))
    # Sort by our composite score and return top_k
    results.sort(key=lambda c: c.ranking_score, reverse=True)
    return results[:top_k]

@router.get("/course/{course_id}", response_model=CourseDetail)
def get_course(course_id: str):
    doc = db["courses"].find_one({"course_id": course_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Course '{course_id}' not found")
    # Convert embedded reviews to Review Pydantic models (ensuring types)
    reviews = []
    for r in doc.get("reviews", []):
        rating_val = r.get("rating")
        try:
            rating = float(rating_val) if rating_val is not None else None
        except (TypeError, ValueError):
            rating = None

        sentiment_val = r.get("sentiment_score")
        try:
            sentiment_score = float(sentiment_val) if sentiment_val is not None else None
        except (TypeError, ValueError):
            sentiment_score = None

        reviews.append(
            Review(
                review_id=r.get("review_id", ""),
                text=r.get("text", ""),
                rating=rating,
                sentiment_score=sentiment_score,
            )
        )
    return CourseDetail(
        course_id=doc["course_id"],
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        provider=doc.get("provider", ""),
        url=doc.get("url", ""),
        categories=doc.get("categories", []),
        num_reviews=int(doc.get("num_reviews", 0)),
        avg_sentiment=float(doc.get("avg_sentiment", 0.0)),
        smoothed_sentiment=float(doc.get("smoothed_sentiment", 0.0)),
        reviews=reviews
    )


