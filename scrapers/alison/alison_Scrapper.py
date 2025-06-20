#!/usr/bin/env python3
"""
Alison Scraper (CLI-Driven)

Usage:
    python main.py --keyword python

This script will:
  1. Accept a `--keyword` argument.
  2. Scrape Alison courses for that keyword (up to 12 courses).
  3. Scrape up to 10 reviews for each course.
  4. Save JSON outputs into `alison_course_data/` and `alison_reviews_data/` located
     in the same directory as this script.
"""
import os
import json
import time
import logging
import argparse
from urllib.parse import urlencode, urlparse, urlunparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)

# ─── SETUP ──────────────────────────────────────────────────────────────────
# Determine script directory for output paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "alison_course_data")
REVIEWS_DIR = os.path.join(BASE_DIR, "alison_reviews_data")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REVIEWS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─── CLI ARGUMENTS ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Scrape Alison courses and reviews for a given keyword."
)
parser.add_argument(
    "--keyword", required=True,
    help="Search term to scrape (e.g., 'computer', 'python')"
)
args = parser.parse_args()
keyword = args.keyword.strip()
if not keyword:
    logger.error("❌ Please provide a non-empty --keyword argument.")
    exit(1)

# ─── DRIVER INIT ───────────────────────────────────────────────────────────
def init_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Instantiate a Chrome WebDriver matching installed Chrome via webdriver_manager.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    # Disable images for speed
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    return driver

# ─── COURSE SCRAPING ───────────────────────────────────────────────────────
def scrape_courses(
    driver: webdriver.Chrome,
    keyword: str,
    pages_to_fetch: int = 2,
    max_courses: int = 12
) -> list[dict]:
    """
    Scrape up to `max_courses` Alison courses matching `keyword` over `pages_to_fetch` pages.
    """
    base_search_url = "https://alison.com/courses"
    collected = []

    for page in range(1, pages_to_fetch + 1):
        if len(collected) >= max_courses:
            break

        params = {"query": keyword, "page": page}
        url = f"{base_search_url}?{urlencode(params)}"
        logger.info(f"Loading page {page}: {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".card__info"))
            )
        except TimeoutException:
            logger.warning(f"No course cards found on page {page}.")
            continue

        cards = driver.find_elements(By.CSS_SELECTOR, ".card__info")
        logger.info(f" → Found {len(cards)} cards on page {page}.")

        for card in cards:
            if len(collected) >= max_courses:
                break
            try:
                level = card.find_element(By.CSS_SELECTOR, ".course-level").get_attribute("data-id").strip()
                subject = card.find_element(By.CSS_SELECTOR, ".card__top > span:not(.card__accr)").text.strip()
                title = card.find_element(By.CSS_SELECTOR, ".card__top h3").text.strip()
                duration = card.find_element(By.CSS_SELECTOR, ".card__duration").text.strip()
                enrolled = card.find_element(By.CSS_SELECTOR, ".card__enrolled").text.strip()
                try:
                    publisher = card.find_element(By.CSS_SELECTOR, ".card__publisher a").text.replace("By", "").strip()
                except NoSuchElementException:
                    publisher = ""
                outcomes = [
                    o.get_attribute("data-title").strip()
                    for o in card.find_elements(By.CSS_SELECTOR, ".card__outcomes li.visible")
                    if o.get_attribute("data-title").strip()
                ]
                info_url = card.find_element(By.CSS_SELECTOR, "a.card__more--mobile").get_attribute("href").strip()
                start_url = card.find_element(By.CSS_SELECTOR, "a.card__start").get_attribute("href").strip()

                course_obj = {
                    "level": level,
                    "subject": subject,
                    "title": title,
                    "duration": duration,
                    "enrolled": enrolled,
                    "publisher": publisher,
                    "outcomes": outcomes,
                    "info_url": info_url,
                    "start_url": start_url
                }
                collected.append(course_obj)
                logger.info(f"  • Extracted: {title}")
            except Exception as e:
                logger.debug(f"Skip card: {e}")
        time.sleep(1)

    safe_kw = keyword.replace(" ", "_")
    out_file = os.path.join(OUTPUT_DIR, f"{safe_kw}_alison_courses.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)
    logger.info(f"✔️ Saved {len(collected)} courses → {out_file}")
    return collected

# ─── REVIEW SCRAPING ───────────────────────────────────────────────────────
def scrape_course_reviews(
    course_url: str,
    max_reviews: int = 10,
    delay: float = 1.0
) -> list[dict]:
    """
    Scrape up to `max_reviews` reviews from `course_url`.
    """
    driver = init_driver(True)
    wait = WebDriverWait(driver, 20)

    try:
        parsed = urlparse(course_url)
        base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        full = base.rstrip("/") + "#reviews-section"
        logger.info(f"→ Reviews: {full}")
        try:
            driver.get(full)
        except TimeoutException:
            logger.warning(f"Timeout loading {base}. Skipping.")
            return []
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.l-reviews")))
        except TimeoutException:
            logger.warning("No reviews found.")
            return []

        data, seen = [], set()
        while len(data) < max_reviews:
            # load more
            while True:
                before = len(driver.find_elements(By.CSS_SELECTOR, "div.l-review"))
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "div.l-reviews__more.l-but.l-but--center")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                except (NoSuchElementException, StaleElementReferenceException):
                    break
                try:
                    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.l-review")) > before)
                    time.sleep(delay)
                except TimeoutException:
                    break
            # collect
            for elem in driver.find_elements(By.CSS_SELECTOR, "div.l-review")[:max_reviews]:
                rid = elem.get_attribute("data-id") or ""
                if rid and rid not in seen:
                    try:
                        txt = elem.find_element(By.CSS_SELECTOR, ".l-review__content").text.strip()
                    except NoSuchElementException:
                        continue
                    user = elem.find_element(By.CSS_SELECTOR, ".l-review__name").text.strip() if elem.find_elements(By.CSS_SELECTOR, ".l-review__name") else ""
                    rating = elem.find_element(By.CSS_SELECTOR, ".l-review__user-rating").text.strip() if elem.find_elements(By.CSS_SELECTOR, ".l-review__user-rating") else ""
                    data.append({"id": rid, "user": user, "rating": rating, "text": txt})
                    seen.add(rid)
            if len(data) >= max_reviews:
                break
            # next page
            try:
                old = driver.find_elements(By.CSS_SELECTOR, "div.l-review")[0].get_attribute("data-id")
                nxt = driver.find_element(By.CSS_SELECTOR, ".js-pagination .page-link.next:not(.disabled)")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", nxt)
                time.sleep(0.5)
                nxt.click()
                wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "div.l-review")[0].get_attribute("data-id") != old)
                time.sleep(delay)
            except Exception:
                break
        return data[:max_reviews]
    finally:
        driver.quit()

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    courses = scrape_courses(init_driver(True), keyword)
    for course in courses:
        title = course["title"]
        info_url = course["info_url"]
        logger.info(f"--- Extracting reviews for: {title} ---")
        reviews = scrape_course_reviews(info_url, max_reviews=10, delay=1.0)
        safe = title.replace(" ", "_").replace("/", "_")[:50]
        path = os.path.join(REVIEWS_DIR, f"{safe}_reviews.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(reviews, f, indent=2, ensure_ascii=False)
        logger.info(f"✔️ Saved {len(reviews)} reviews for '{title}' → {path}")
