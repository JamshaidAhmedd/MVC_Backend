def run_scrapers_for_pending():
    pending_keywords = keyword_queue.get_pending_keywords()
    if not pending_keywords:
        log.info("No new keywords to scrape.")
        return False
    for kw in pending_keywords:
        log.info(f"Scraping courses for keyword: '{kw}'")
        # Run Alison scraper
        scraped_courses_alison, scraped_reviews_alison = alison_scraper.scrape(kw)
        # Run Coursera scraper
        scraped_courses_coursera, scraped_reviews_coursera = coursera_scraper.scrape(kw)
        # (The scraper modules provide data in Python lists/dicts instead of writing files)
        # Mark keyword as scraped in queue
        keyword_queue.mark_scraped(kw)
        # Accumulate scraped data
        all_data["alison"]["courses"].extend(scraped_courses_alison)
        all_data["alison"]["reviews"].update(scraped_reviews_alison)
        all_data["coursera"]["courses"].extend(scraped_courses_coursera)
        all_data["coursera"]["reviews"].update(scraped_reviews_coursera)
    return True


def unify_and_ingest(all_data):
    # Use unify_data utility to get unified course docs for all providers
    unified_docs = unify_data.unify_all({
        "alison": (all_data["alison"]["courses"], all_data["alison"]["reviews"]),
        "coursera": (all_data["coursera"]["courses"], all_data["coursera"]["reviews"])
    })
    if not unified_docs:
        log.warning("No new courses to ingest.")
        return False
    # Prepare bulk upsert operations
    ops = []
    for doc in unified_docs:
        ops.append(UpdateOne({"course_id": doc["course_id"]}, {"$set": doc}, upsert=True))
    result = db["courses"].bulk_write(ops)
    log.info(f"Upserted {result.upserted_count} new courses, modified {result.modified_count} existing courses.")
    return True
def run_ingestion_pipeline():
    log.info("Starting ingestion pipeline...")
    start_time = datetime.utcnow()
    any_scraped = run_scrapers_for_pending()
    if not any_scraped:
        log.info("Ingestion pipeline finished (nothing to scrape).")
        return
    unify_and_ingest(all_scraped_data)
    # After ingestion, update categories for all courses
    category_tagger.retag_all()
    # Process any search requests that can now be fulfilled
    notification_service.process_search_requests()
    elapsed = datetime.utcnow() - start_time
    log.info(f"Ingestion pipeline completed in {elapsed.total_seconds():.2f} seconds.")



