from fastapi import APIRouter, Depends

from app.core import security
from app.services import data_ingestion, sentiment, notification_service

router = APIRouter(prefix="/admin/tasks", tags=["admin"])


@router.post("/ingest", status_code=202)
def trigger_ingest(admin=Depends(security.get_current_admin)):
    """Run the ingestion pipeline immediately."""
    data_ingestion.run_ingestion_pipeline()
    return {"status": "ingestion started"}


@router.post("/sentiment", status_code=202)
def trigger_sentiment(admin=Depends(security.get_current_admin)):
    """Run the sentiment enrichment pipeline."""
    sentiment.run_sentiment_enrichment()
    return {"status": "sentiment enrichment started"}


@router.post("/notify", status_code=202)
def trigger_notify(admin=Depends(security.get_current_admin)):
    """Process and dispatch notifications now."""
    notification_service.process_search_requests()
    notification_service.dispatch_notifications()
    return {"status": "notifications dispatched"}
