from pydantic import BaseModel
from typing import List, Optional

class Review(BaseModel):
    review_id: str
    text: str
    rating: Optional[float] = None
    sentiment_score: Optional[float] = None

class CourseDetail(BaseModel):
    course_id: str
    title: str
    description: str
    provider: str
    url: str
    categories: List[str]
    num_reviews: int
    avg_sentiment: float
    smoothed_sentiment: float
    reviews: List[Review]

class CourseSummary(BaseModel):
    course_id: str
    title: str
    ranking_score: float
    text_norm: float
    sent_norm: float
    pop_weight: float
    num_reviews: int
    smoothed_sentiment: float

