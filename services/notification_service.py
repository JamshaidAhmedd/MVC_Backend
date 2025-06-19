def process_search_requests():
    pending = keyword_queue.get_pending()  # get all requests with notified=False
    for req in pending:
        kw = req["keyword"]
        user_id = req["user_id"]
        # Check if any course now matches the keyword (using text search on courses)
        if db["courses"].count_documents({"$text": {"$search": kw}}) > 0:
            message = f"New courses are now available for '{kw}'."
            notification = {
                "_id": PyObjectId(),  # generate a new ObjectId for the notification
                "message": message,
                "created_at": datetime.utcnow(),
                "read": False,
                "sent": False
            }
            # Push the notification to the user's notifications array
            db["users"].update_one({"_id": user_id}, {"$push": {"notifications": notification}})
            # Mark the search request as notified
            keyword_queue.mark_notified(req["_id"])
            log.info(f"Notification queued for user {user_id} on keyword '{kw}'")


def dispatch_notifications():
    # Find all notifications that have not been sent yet
    pipeline = [
        {"$unwind": "$notifications"},
        {"$match": {"notifications.sent": False}},
        {"$project": {"user_id": "$_id", "notification": "$notifications"}}
    ]
    for doc in db["users"].aggregate(pipeline):
        user_id = doc["user_id"]
        note = doc["notification"]  # contains _id, message, etc.
        # "Send" the notification (here we just log it; in real case, send email or push)
        log.info(f"Dispatching notification to user {user_id}: {note['message']}")
        # Mark as sent
        db["users"].update_one(
            {"_id": user_id, "notifications._id": note["_id"]},
            {"$set": {"notifications.$.sent": True}}
        )



def watch_notifications(interval_hours=4):
    while True:
        process_search_requests()
        dispatch_notifications()
        time.sleep(interval_hours * 3600)
