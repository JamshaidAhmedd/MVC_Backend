{
    "course_id": f"{provider}–{slug}",
    "title": raw_course.get("title", "").strip(),
    "description": (raw_course.get("description") or "").strip(),
    "provider": provider,
    "url": raw_course.get("link") or raw_course.get("info_url", ""),
    "last_updated": datetime.utcnow(),
    "categories": raw_course.get("categories", []),
    "reviews": []
}

{
    "review_id": f"{provider}–{slug}–{idx}",
    "text": raw_review.get("text") or raw_review.get("review_text", "") or "",
    "rating": raw_review.get("rating") or raw_review.get("stars"),
    "scraped_at": datetime.utcnow()
}
