"""Notification processing and dispatch utilities."""

import logging
import time
from datetime import datetime

from bson import ObjectId

from app.core.config import db
from app.models.notification import PyObjectId
from app.utils import keyword_queue

log = logging.getLogger(__name__)


def process_search_requests() -> None:
    """Create notifications for pending search requests if results now exist."""
    pending = keyword_queue.get_pending()
    for req in pending:
        kw = req["keyword"]
        user_id = req["user_id"]
        if db["courses"].count_documents({"$text": {"$search": kw}}) > 0:
            note = {
                "_id": PyObjectId(),
                "message": f"New courses are now available for '{kw}'.",
                "created_at": datetime.utcnow(),
                "read": False,
                "sent": False,
            }
            db["users"].update_one({"_id": user_id}, {"$push": {"notifications": note}})
            keyword_queue.mark_notified(req["_id"])
            log.info("Queued notification for user %s keyword '%s'", user_id, kw)


def dispatch_notifications() -> None:
    """Dispatch unsent notifications (stdout placeholder)."""
    pipeline = [
        {"$unwind": "$notifications"},
        {"$match": {"notifications.sent": False}},
        {"$project": {"user_id": "$_id", "notification": "$notifications"}},
    ]
    for doc in db["users"].aggregate(pipeline):
        user_id = doc["user_id"]
        note = doc["notification"]
        log.info("Dispatching notification to user %s: %s", user_id, note["message"])
        db["users"].update_one(
            {"_id": user_id, "notifications._id": note["_id"]},
            {"$set": {"notifications.$.sent": True}},
        )


def watch_notifications(interval_hours: int = 4) -> None:
    """Continuously process and dispatch notifications."""
    while True:
        process_search_requests()
        dispatch_notifications()
        time.sleep(interval_hours * 3600)
