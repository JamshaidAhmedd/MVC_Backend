"""Utilities for unifying scraped course data from different providers."""

from datetime import datetime
from typing import Dict, List, Tuple, Iterable


def _unify_course(provider: str, raw_course: dict) -> dict:
    """Convert a raw course dict to the common format."""
    slug = raw_course.get("id") or raw_course.get("slug") or raw_course.get("title", "").lower().replace(" ", "-")
    return {
        "course_id": f"{provider}-{slug}",
        "title": raw_course.get("title", "").strip(),
        "description": (raw_course.get("description") or "").strip(),
        "provider": provider,
        "url": raw_course.get("url") or raw_course.get("link") or raw_course.get("info_url", ""),
        "last_updated": datetime.utcnow(),
        "categories": raw_course.get("categories", []),
        "reviews": [],
    }


def _unify_review(provider: str, slug: str, idx: int, raw_review: dict) -> dict:
    """Convert a raw review dict to the common format."""
    return {
        "review_id": f"{provider}-{slug}-{idx}",
        "text": raw_review.get("text") or raw_review.get("review_text", "") or "",
        "rating": raw_review.get("rating") or raw_review.get("stars"),
        "scraped_at": datetime.utcnow(),
    }


def unify_all(provider_data: Dict[str, Tuple[Iterable[dict], Dict[str, List[dict]]]]) -> List[dict]:
    """Unify scraped data from multiple providers.

    `provider_data` is a mapping of provider name to a tuple of
    (course_list, reviews_dict) where `reviews_dict` maps a course slug
    to a list of raw review dicts.
    """
    unified: List[dict] = []
    for provider, (courses, reviews) in provider_data.items():
        for raw_course in courses:
            course = _unify_course(provider, raw_course)
            slug = raw_course.get("id") or raw_course.get("slug") or course["course_id"].split("-", 1)[-1]
            raw_reviews = reviews.get(slug, [])
            for idx, r in enumerate(raw_reviews):
                course["reviews"].append(_unify_review(provider, slug, idx, r))
            unified.append(course)
    return unified
