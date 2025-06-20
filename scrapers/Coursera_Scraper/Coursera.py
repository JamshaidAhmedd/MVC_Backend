#!/usr/bin/env python3
"""
Combined Coursera Scraper (Part 1 & 2)

Accepts --keyword from CLI instead of interactive input.
Usage:
    python main.py --keyword python
"""
import argparse
import asyncio
import json
import os
import logging
from playwright.async_api import async_playwright

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Parse CLI arguments
parser = argparse.ArgumentParser(description="Scrape Coursera courses and reviews for a given keyword.")
parser.add_argument(
    "--keyword", required=True, help="Search term to scrape (e.g., 'python', 'data science')"
)
args = parser.parse_args()
keyword = args.keyword.strip()
if not keyword:
    logger.error("No keyword provided. Use --keyword to specify a search term.")
    exit(1)

# Directory for saving course and reviews data
OUTPUT_DIR = "course_data"
REVIEWS_OUTPUT_DIR = "reviews_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REVIEWS_OUTPUT_DIR, exist_ok=True)

async def scrape_courses(keyword):
    """
    Fetches course data from Coursera based on a keyword and saves to a JSON file.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Use headless=False for debugging
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        search_url = f"https://www.coursera.org/courses?query={keyword}"
        logger.info(f"Navigating to {search_url}")
        await page.goto(search_url)

        # Wait for course cards to load
        await page.wait_for_selector('li.cds-9.css-0')  # Main container for courses

        # Query course elements
        courses = await page.query_selector_all('li.cds-9.css-0')

        course_data = []

        for course_element in courses:
            try:
                # Extract title
                title_element = await course_element.query_selector('h3.cds-CommonCard-title')
                title = await title_element.inner_text() if title_element else "N/A"

                # Extract link
                link_element = await course_element.query_selector('a.cds-119')
                link_href = await link_element.get_attribute('href') if link_element else "N/A"
                full_link = f"https://www.coursera.org{link_href}" if link_href else "N/A"

                # Extract description
                description_element = await course_element.query_selector('div.cds-ProductCard-body')
                description = await description_element.inner_text() if description_element else "N/A"

                # Extract rating (e.g., "4.7")
                rating_element = await course_element.query_selector('span.css-6ecy9b')
                rating = await rating_element.inner_text() if rating_element else "N/A"

                # Extract number of reviews (e.g., "1.2K reviews")
                reviews_element = await course_element.query_selector('div.css-vac8rf')
                reviews = await reviews_element.inner_text() if reviews_element else "N/A"

                # Create course object
                course = {
                    "title": title.strip(),
                    "link": full_link.strip(),
                    "description": description.strip(),
                    "rating": rating.strip(),
                    "reviews": reviews.strip(),
                }

                # Add course data to list
                course_data.append(course)

                logger.info(f"Extracted course: {course['title']}")

            except Exception as e:
                logger.error(f"Error extracting a course: {e}")

        # Save to JSON file
        output_file = os.path.join(OUTPUT_DIR, f"{keyword}_courses.json")
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(course_data, file, indent=4)
        
        logger.info(f"Saved course data to {output_file}")

        await browser.close()
        return course_data


async def extract_reviews(course_link, course_title):
    """
    Fetches reviews for a specific course and saves to a JSON file.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Debugging mode
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        logger.info(f"Navigating to course reviews link: {course_link}")
        await page.goto(course_link)

        # Click "View more reviews" button if available
        try:
            view_more_button = await page.query_selector('a[data-track-component="reviews_module_view_more_cta"]')
            if view_more_button:
                logger.info("Clicking 'View more reviews' button...")
                await view_more_button.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            logger.warning(f"'View more reviews' button not found: {e}")

        # Extract reviews
        reviews = []
        try:
            review_containers = await page.query_selector_all('div.rc-ReviewsList > div')  # Generalized selector
            for review_container in review_containers[:10]:  # Limit to 10 reviews
                try:
                    # Extract review text (all paragraphs)
                    review_text_elements = await review_container.query_selector_all('div.reviewText span span')
                    review_text = "\n".join([
                        await paragraph.inner_text() for paragraph in review_text_elements
                    ]) if review_text_elements else "N/A"

                    # Extract reviewer name
                    name_element = await review_container.query_selector('p.reviewerName span')
                    name = await name_element.inner_text() if name_element else "N/A"

                    # Extract review date
                    date_element = await review_container.query_selector('p.dateOfReview')
                    date = await date_element.inner_text() if date_element else "N/A"

                    # Extract star rating
                    stars_container = await review_container.query_selector('div._1mzojlvw')  # Stars container
                    filled_stars = await stars_container.query_selector_all('svg[style*="fill:#F2D049"]') if stars_container else []
                    star_rating = len(filled_stars)

                    # Append to reviews list
                    reviews.append({
                        "review_text": review_text.strip(),
                        "name": name.strip(),
                        "date": date.strip(),
                        "stars": star_rating,
                    })

                except Exception as e:
                    logger.error(f"Error extracting review details: {e}")

        except Exception as e:
            logger.error(f"Error extracting reviews: {e}")

        # Save reviews to a JSON file
        output_file = os.path.join(REVIEWS_OUTPUT_DIR, f"{course_title.replace(' ', '_')}_reviews.json")
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(reviews, file, indent=4)

        logger.info(f"Saved reviews for {course_title} to {output_file}")

        await browser.close()


async def main():
    # Use keyword from CLI
    # Already parsed above
    courses = await scrape_courses(keyword)

    # Step 2: Extract reviews for each course
    for course in courses:
        course_title = course['title']
        course_link = course['link'] + "/reviews"
        await extract_reviews(course_link, course_title)


if __name__ == "__main__":
    asyncio.run(main())
