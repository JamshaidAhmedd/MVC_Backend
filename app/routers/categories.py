from fastapi import APIRouter
from typing import List
import math
from app.core.config import db, settings
from app.models.category import CategoryOut
from app.models.course import CourseSummary

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("", response_model=List[CategoryOut])
def list_categories():
    categories = []
    for cat in db["categories"].find():
        categories.append(CategoryOut(
            id=str(cat["_id"]),
            name=cat["name"],
            description=cat.get("description", ""),
            keywords=cat.get("keywords", [])
        ))
    return categories


@router.get("/{name}/courses", response_model=List[CourseSummary])
def get_courses_by_category(name: str):
    cursor = db["courses"].find(
        {"categories": name},
        {"course_id": 1, "title": 1, "smoothed_sentiment": 1, "num_reviews": 1}
    )
    results = []
    for doc in cursor:
        # Compute a basic ranking score for category listing:
        # Here text relevance isn't applicable (all these match the category exactly),
        # so we rank by sentiment and popularity only.
        sent = float(doc.get("smoothed_sentiment", 0.0))
        sent_norm = (sent + 1.0) / 2.0
        n = int(doc.get("num_reviews", 0))
        pop_weight = math.log(1 + n)
        score = (1 - settings.ALPHA) * sent_norm + settings.BETA * pop_weight
        results.append(CourseSummary(
            course_id=doc["course_id"],
            title=doc["title"],
            ranking_score=round(score, 4),
            text_norm=0.0,
            sent_norm=round(sent_norm, 4),
            pop_weight=round(pop_weight, 4),
            num_reviews=n,
            smoothed_sentiment=round(sent, 4)
        ))
    results.sort(key=lambda c: c.ranking_score, reverse=True)
    return results


