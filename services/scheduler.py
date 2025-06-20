#!/usr/bin/env python3
"""
scheduler.py

Runs:
  - ingestion.py every 4 hours
  - sentiment_enrichment.py daily at 2 AM
  - notification_dispatcher.py every 4 hours after ingestion
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from services.data_ingestion import run_ingestion_pipeline
from services.sentiment import run_sentiment_enrichment
from services.notification_service import run_notify

# ── SETUP LOGGING ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger()

# ── SCHEDULER ───────────────────────────────────────────────────────
sched = BlockingScheduler()


def log_and_run(name, fn):
    log.info(f"→ Starting {name}")
    try:
        fn()
        log.info(f"✓ {name} succeeded")
    except Exception as e:
        log.error(f"✗ {name} failed: {e}")


# ── JOBS ───────────────────────────────────────────────────────────

# Every 4 hours: full scrape → unify → ingest → enrich → notify
sched.add_job(
    lambda: log_and_run("Ingestion pipeline", run_ingestion_pipeline),
    trigger="interval",
    hours=4,
    id="ingest_job",
    max_instances=1,
    next_run_time=None
)
sched.add_job(
    lambda: log_and_run("Notification dispatch", run_notify),
    trigger="interval",
    hours=4,
    id="notify_job",
    max_instances=1,
    # start 5 minutes after the ingestion job
    start_date=datetime.now() + timedelta(minutes=5)
)

# Daily at 02:00: sentiment scoring & aggregation
sched.add_job(
    lambda: log_and_run("Sentiment enrichment", run_sentiment_enrichment),
    trigger="cron",
    hour=2,
    minute=0,
    id="enrich_job",
    max_instances=1
)

if __name__ == "__main__":
    log.info("=== Scheduler started ===")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user")
