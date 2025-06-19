def score_new_reviews():
    pipeline = [
        {"$unwind": "$reviews"},
        {"$match": {"reviews.sentiment_score": {"$exists": False}}},
        {"$project": {"course_id": 1, "reviews.review_id": 1, "reviews.text": 1}}
    ]
    updates = []
    count = 0
    for doc in db["courses"].aggregate(pipeline):
        review_text = doc["reviews"]["text"] or ""
        score = TextBlob(review_text).sentiment.polarity
        updates.append(UpdateOne(
            {"course_id": doc["course_id"], "reviews.review_id": doc["reviews"]["review_id"]},
            {"$set": {"reviews.$.sentiment_score": score}}
        ))
        count += 1
    if updates:
        res = db["courses"].bulk_write(updates)
        log.info(f"Assigned sentiment_score for {count} new reviews (documents updated: {res.modified_count})")
    else:
        log.info("No new reviews to score.")

def aggregate_course_metrics():
    # Compute global average sentiment across all reviews (for smoothing)
    all_scores = []
    for c in db["courses"].find({}, {"reviews.sentiment_score": 1}):
        for r in c.get("reviews", []):
            if "sentiment_score" in r:
                all_scores.append(r["sentiment_score"])
    global_mean = sum(all_scores)/len(all_scores) if all_scores else 0.0
    log.info(f"Global sentiment mean = {global_mean:.4f}")
    updates = []
    for course in db["courses"].find({}, {"course_id": 1, "reviews.sentiment_score": 1}):
        scores = [r["sentiment_score"] for r in course.get("reviews", []) if "sentiment_score" in r]
        n = len(scores)
        avg = sum(scores)/n if n else 0.0
        # Bayesian smoothing: weight with global_mean and PSEUDOCOUNT
        smooth = ((PSEUDOCOUNT * global_mean) + sum(scores)) / (PSEUDOCOUNT + n) if (PSEUDOCOUNT + n) else global_mean
        updates.append(UpdateOne(
            {"course_id": course["course_id"]},
            {"$set": {"num_reviews": n, "avg_sentiment": avg, "smoothed_sentiment": smooth}}
        ))
    if updates:
        res = db["courses"].bulk_write(updates)
        log.info(f"Updated sentiment metrics for {res.modified_count} courses.")
    else:
        log.info("No courses found to update metrics.")


def rebuild_text_index():
    coll = db["courses"]
    for idx in coll.list_indexes():
        if "text" in idx["key"].values():
            coll.drop_index(idx["name"])
    coll.create_index([("title", TEXT), ("description", TEXT), ("reviews.text", TEXT)], name="CourseTextIndex")
    log.info("Rebuilt text index on courses.")
def run_sentiment_enrichment():
    log.info("Starting sentiment enrichment...")
    score_new_reviews()
    aggregate_course_metrics()
    rebuild_text_index()
    log.info("Sentiment enrichment complete.")


