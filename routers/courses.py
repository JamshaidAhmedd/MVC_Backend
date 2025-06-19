from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
import math
from core import security
from core.config import db, settings
from models.course import CourseSummary, CourseDetail, Review
from utils import keyword_queue

router = APIRouter(tags=["courses"])

@router.get("/search", response_model=List[CourseSummary])
def search_courses(query: str = Query(..., min_length=1), top_k: int = Query(10, ge=1, le=100),
                   current_user: Optional[dict] = Depends(security.get_current_user)):
    # Use MongoDB text index to find matching courses
    cursor = db["courses"].find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"}, "course_id": 1, "title": 1,
         "smoothed_sentiment": 1, "num_reviews": 1}
    ).sort([("score", {"$meta": "textScore"})]).limit(top_k * 5)
    docs = list(cursor)
    if not docs:
        # If no courses found, and user is logged in, record the search for future notifications
        if current_user:
            keyword_queue.add_request(current_user["_id"], query)
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
        reviews.append(Review(
            review_id=r.get("review_id", ""),
            text=r.get("text", ""),
            rating=(float(r["rating"]) if r.get("rating") is not None else None),
            sentiment_score=(float(r["sentiment_score"]) if r.get("sentiment_score") is not None else None)
        ))
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


