from apscheduler.schedulers.blocking import BlockingScheduler
from app.services import data_ingestion, sentiment, notification_service

sched = BlockingScheduler(timezone="UTC")
# Job: run full ingestion pipeline every 4 hours
sched.add_job(data_ingestion.run_ingestion_pipeline, "interval", hours=4, id="ingest_job", max_instances=1, next_run_time=None)
# Job: run notification dispatch every 4 hours (offset by a few minutes after ingestion)
sched.add_job(notification_service.dispatch_notifications, "interval", hours=4, id="notify_job", max_instances=1, next_run_time=None, minutes=5)
# Job: run sentiment enrichment daily at 2:00 AM
sched.add_job(sentiment.run_sentiment_enrichment, "cron", hour=2, minute=0, id="sentiment_job", max_instances=1)


if __name__ == "__main__":
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
