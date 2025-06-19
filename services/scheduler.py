#!/usr/bin/env python3
"""
scheduler.py

Runs:
  - ingestion.py every 4 hours
  - sentiment_enrichment.py daily at 2 AM
  - notification_dispatcher.py every 4 hours after ingestion
"""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from ingestion import main as run_ingest
from sentiment_enrichment import main as run_enrich
from notification_dispatcher import run_notify

# ── SETUP LOGGING ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger()

# ── SCHEDULER ─────────────────────────────────────────────────────────────────
sched = BlockingScheduler()

def log_and_run(name, fn):
    log.info(f"→ Starting {name}")
    try:
        fn()
        log.info(f"✓ {name} succeeded")
    except Exception as e:
        log.error(f"✗ {name} failed: {e}")

# Every 4 hours: full scrape → unify → ingest → enrich → notify
sched.add_job(
    lambda: log_and_run("Ingestion pipeline", run_ingest),
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
    # offset notify slightly after ingestion
    next_run_time=None
)

# Daily at 02:00: sentiment scoring & aggregation
sched.add_job(
    lambda: log_and_run("Sentiment enrichment", run_enrich),
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
