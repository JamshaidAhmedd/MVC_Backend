#!/usr/bin/env python3
"""
ingestion.py

Phase 1 – Scrape, unify, ingest, and categorize courses.

Pipeline steps:
  1) Scrape new keywords from keyword_queue
  2) Unify raw JSON via unify.py
  3) Bulk-upsert unified docs into MongoDB
  4) Retag all courses per category using category_tagger.retag_all()
"""

import sys
import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient, UpdateOne, TEXT
from pymongo.errors import PyMongoError

from utils import category_tagger, keyword_queue
from services import notification_service

# ── CONFIG ───────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.resolve()
ALISON_SCRIPT   = BASE_DIR / "Alison_scraper"   / "main.py"
COURSERA_SCRIPT = BASE_DIR / "Coursera_Scraper" / "Coursera.py"
UNIFY_SCRIPT    = BASE_DIR / "unify.py"
UNIFIED_DIR     = BASE_DIR / "unified_data"
MONGO_URI       = "mongodb+srv://admin:admin@cluster0.hpskmws.mongodb.net/course_app?retryWrites=true&w=majority"
LOG_DIR         = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE        = LOG_DIR / "ingest.log"
# ── END CONFIG ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("ingestion")


def run_step(name, cmd, cwd):
    log.info(f"→ {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for line in proc.stdout or []:
        log.info(f"[{name}] {line.rstrip()}")
    if proc.wait() != 0:
        log.error(f"✗ {name} failed")
        return False
    log.info(f"✓ {name} succeeded")
    return True


def step_scrapers():
    """Run scrapers for each pending keyword."""
    try:
        import keyword_queue as kq
    except ImportError:
        log.warning("keyword_queue not found; skipping scrapers")
        return True

    pending = kq.get_pending_keywords()
    if not pending:
        log.info("✔ No pending keywords to scrape.")
        return True

    for kw in pending:
        log.info(f"\n=== Scraping '{kw}' ===")
        if not run_step("Alison scraper", ["python", str(ALISON_SCRIPT), "--keyword", kw], cwd=ALISON_SCRIPT.parent):
            return False
        if not run_step("Coursera scraper", ["python", str(COURSERA_SCRIPT), "--keyword", kw], cwd=COURSERA_SCRIPT.parent):
            return False
        try:
            kq.mark_scraped(kw)
        except Exception as e:
            log.warning(f"Could not mark '{kw}' scraped: {e}")
    return True


def step_unify():
    """Merge raw JSON into unified_data/ via unify.py."""
    return run_step("Data unification", ["python", str(UNIFY_SCRIPT)], cwd=BASE_DIR)


def step_ingest():
    """Bulk-upsert unified JSON docs into MongoDB."""
    log.info("→ Connecting to MongoDB")
    client     = MongoClient(MONGO_URI)
    collection = client["course_app"]["courses"]

    files = sorted(UNIFIED_DIR.glob("*.json"))
    if not files:
        log.warning("⚠ No unified JSON files found.")
        return False

    ops = []
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            ops.append(UpdateOne(
                {"course_id": doc["course_id"]},
                {"$set": doc},
                upsert=True
            ))
        except Exception as e:
            log.error(f"Failed to parse {path.name}: {e}")

    if not ops:
        log.error("✗ No documents to ingest.")
        return False

    try:
        res = collection.bulk_write(ops)
        log.info(f"✓ Upsert: inserted={res.upserted_count}, modified={res.modified_count}")
        return True
    except PyMongoError as e:
        log.error(f"MongoDB bulk write error: {e}")
        return False


def run_ingestion_pipeline() -> bool:
    """Execute the full ingestion pipeline without exiting."""
    log.info("=== Ingestion Pipeline Start ===")
    start = datetime.now()

    if not step_scrapers():
        return False
    if not step_unify():
        return False
    if not step_ingest():
        return False

    # Retag all courses according to categories
    category_tagger.retag_all()

    # Process any outstanding notification requests
    notification_service.process_search_requests()
    notification_service.dispatch_notifications()

    elapsed = datetime.now() - start
    log.info(f"🎉 Pipeline finished in {elapsed}")
    return True


def main() -> None:
    """Entry point when executed as a script."""
    success = run_ingestion_pipeline()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
