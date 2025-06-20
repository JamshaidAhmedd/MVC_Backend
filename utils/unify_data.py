#!/usr/bin/env python3
"""
Data Unification

Loads per-provider course JSON and review JSON files,
canonizes their structure, attaches reviews, and writes
one unified file per course into `unified_data/`.  
All slugs are safely sanitized for filenames.
"""
import os
import json
import glob
import logging
import re
from datetime import datetime
from pathlib import Path

# ── CONFIG ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = BASE_DIR.parent / "scrapers"
OUT_DIR = BASE_DIR / "unified_data"
OUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()
# ── END CONFIG ───────────────────────────────────────────────

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def safe_slug(text: str) -> str:
    """
    Turn `text` into a filename-safe slug:
    - Replace spaces with underscores.
    - Replace any non-word (alphanumeric + _) or hyphen with underscore.
    """
    s = text.strip().replace(" ", "_")
    # \w matches [A-Za-z0-9_], keep hyphens too
    return re.sub(r"[^\w\-]", "_", s)

def canon_course(raw, provider, slug):
    return {
        "course_id":    f"{provider}–{slug}",
        "title":        raw.get("title", "").strip(),
        "description":  (raw.get("description") or "").strip(),
        "provider":     provider,
        "url":          raw.get("info_url") or raw.get("link", ""),
        "last_updated": datetime.utcnow().isoformat(),
        "categories":   raw.get("categories", []),
        "reviews":      []
    }

def canon_review(raw, provider, slug, idx):
    return {
        "review_id":  f"{provider}–{slug}–{idx}",
        "text":       raw.get("text") or raw.get("review_text", "") or "",
        "rating":     raw.get("rating") or raw.get("stars") or None,
        "scraped_at": datetime.utcnow().isoformat()
    }

def unify_provider(provider, course_glob, review_glob):
    log.info(f"\n→ Unifying '{provider}' files")
    courses = {}

    # 1) Load course files (could be list or dict)
    for path in glob.glob(course_glob):
        data = load_json(path)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            log.warning(f"  – Skipping unknown format in {path}")
            continue

        for item in items:
            raw_id = item.get("id") or item.get("title", "")
            slug = safe_slug(raw_id)
            courses[slug] = canon_course(item, provider, slug)

    log.info(f"  • Found {len(courses)} courses for {provider}")

    # 2) Attach reviews
    attached = 0
    for path in glob.glob(review_glob):
        raw_list = load_json(path)
        filename = os.path.basename(path)
        # strip suffix and sanitize
        slug = safe_slug(filename.replace("_reviews.json", ""))
        if slug not in courses:
            log.warning(f"  – No course match for review file {filename}")
            continue
        if not isinstance(raw_list, list):
            log.warning(f"  – Expected list in {filename}, got {type(raw_list).__name__}")
            continue

        for idx, raw in enumerate(raw_list):
            courses[slug]["reviews"].append(canon_review(raw, provider, slug, idx))
        attached += 1

    log.info(f"  • Attached reviews for {attached} courses of {provider}")

    # 3) Write unified files
    for slug, doc in courses.items():
        out_path = OUT_DIR / f"{provider}__{slug}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
    log.info(f"  • Wrote {len(courses)} unified files for {provider}")

    return len(courses)

if __name__ == "__main__":
    total = 0
    total += unify_provider(
        "alison",
        str(SCRAPER_DIR / "Alison_scraper" / "alison_course_data" / "*.json"),
        str(SCRAPER_DIR / "Alison_scraper" / "alison_reviews_data" / "*_reviews.json"),
    )
    total += unify_provider(
        "coursera",
        str(SCRAPER_DIR / "Coursera_Scraper" / "course_data" / "*.json"),
        str(SCRAPER_DIR / "Coursera_Scraper" / "reviews_data" / "*_reviews.json"),
    )
    log.info(f"\n🎉 Total unified files: {total}")
