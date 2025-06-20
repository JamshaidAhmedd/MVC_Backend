"""Course data ingestion pipeline."""

import logging
from datetime import datetime
from typing import Dict, List, Tuple

from pymongo import UpdateOne

from app.core.config import db
from app.utils import category_tagger, keyword_queue, unify_data
from . import sentiment, notification_service

log = logging.getLogger(__name__)


# Placeholder scraper logic -------------------------------------------------

def _scrape_provider(keyword: str) -> Tuple[List[dict], Dict[str, List[dict]]]:
    """Dummy scraper returning empty data."""
    return [], {}


# ---------------------------------------------------------------------------

def run_scrapers_for_pending() -> Dict[str, Dict[str, List]]:
    """Run scrapers for keywords not yet processed."""
    pending = keyword_queue.get_pending_keywords()
    if not pending:
        log.info("No new keywords to scrape")
        return {}
    all_data: Dict[str, Dict[str, List]] = {}
    for kw in pending:
        log.info("Scraping courses for '%s'", kw)
        courses, reviews = _scrape_provider(kw)
        keyword_queue.mark_scraped(kw)
        all_data.setdefault("dummy", {"courses": [], "reviews": {}})
        all_data["dummy"]["courses"].extend(courses)
        for slug, rv in reviews.items():
            all_data["dummy"]["reviews"].setdefault(slug, []).extend(rv)
    return all_data


def unify_and_ingest(scraped: Dict[str, Dict[str, List]]) -> None:
    unified = unify_data.unify_all({provider: (data["courses"], data["reviews"]) for provider, data in scraped.items()})
    if not unified:
        log.info("No new courses to ingest")
        return
    ops = [UpdateOne({"course_id": c["course_id"]}, {"$set": c}, upsert=True) for c in unified]
    if ops:
        res = db["courses"].bulk_write(ops)
        log.info("Upserted %s courses", res.upserted_count + res.modified_count)


def run_ingestion_pipeline() -> None:
    """Execute the full ingestion process."""
    log.info("Starting ingestion pipeline")
    start = datetime.utcnow()
    scraped = run_scrapers_for_pending()
    if scraped:
        unify_and_ingest(scraped)
        category_tagger.retag_all()
        notification_service.process_search_requests()
        sentiment.aggregate_course_metrics()
    elapsed = (datetime.utcnow() - start).total_seconds()
    log.info("Ingestion pipeline finished in %.2f seconds", elapsed)
