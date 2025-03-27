
import asyncio
import json
import time
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright
from GoogleImageScraper import GoogleImageScraper

DOJ_URL = "https://oag.ca.gov/firearms/certified-handguns/recently-added"
PLACEHOLDER_IMAGE = "https://raw.githubusercontent.com/route66guns/gun-roster-data/main/images/placeholder.jpg"

webdriver_path = os.path.abspath("chromedriver")
image_path = os.path.abspath("photos")
os.makedirs(image_path, exist_ok=True)

def clean_query(text):
    return re.sub(r'[^a-zA-Z0-9 ]+', '', text)

def fetch_google_image(search_query):
    try:
        image_scraper = GoogleImageScraper(
            webdriver_path=webdriver_path,
            image_path=image_path,
            search_key=search_query,
            number_of_images=1,
            headless=True,
            min_resolution=(320, 240),
            max_resolution=(1920, 1080),
            max_missed=5
        )

        image_urls = image_scraper.find_image_urls()
        if not image_urls or len(image_urls) == 0:
            print(f"⚠️ No image found for: {search_query}")
            return PLACEHOLDER_IMAGE
        return image_urls[0]
    except Exception as e:
        print(f"❌ Google image fetch failed for '{search_query}': {e}")
        return PLACEHOLDER_IMAGE

async def scrape_handguns():
    handguns = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to DOJ page...")
        await page.goto(DOJ_URL, timeout=90000)

        try:
            print("Waiting for DOJ table...")
            await page.wait_for_selector("table.views-table", timeout=90000)
            print("✅ DOJ Table found.")
        except Exception as e:
            print("❌ DOJ Table not found:", e)
            await page.screenshot(path="page_debug.png", full_page=True)
            await browser.close()
            return

        rows = await page.query_selector_all("table.views-table tr")
        for row in rows[1:]:
            cells = await row.query_selector_all("td")
            if len(cells) >= 5:
                manufacturer = await cells[0].inner_text()
                model = await cells[1].inner_text()
                caliber = await cells[2].inner_text()
                gun_type = await cells[3].inner_text()
                barrel_length = await cells[4].inner_text()
                date_added = await cells[5].inner_text() if len(cells) > 5 else ""

                cleaned_manufacturer = clean_query(manufacturer)
                cleaned_model = clean_query(model)
                search_query = f"{cleaned_manufacturer} {cleaned_model} handgun"
                print(f"🔍 Google image search: {search_query}")
                image_url = fetch_google_image(search_query)
                time.sleep(1)

                description = f"The {manufacturer} {model} is a recently certified handgun featuring a {barrel_length} barrel and chambered in {caliber}."
                features = [
                    f"Caliber: {caliber}",
                    f"Type: {gun_type}",
                    f"Barrel Length: {barrel_length}",
                    f"Manufacturer: {manufacturer}"
                ]

                handguns.append({
                    "manufacturer": manufacturer,
                    "model": model,
                    "caliber": caliber,
                    "type": gun_type,
                    "barrel_length": barrel_length,
                    "date_added": date_added,
                    "description": description,
                    "features": features,
                    "image_url": image_url
                })

        await browser.close()

        data = {
            "updated": datetime.now().isoformat(),
            "handguns": handguns
        }

        with open("sample_handguns.json", "w") as f:
            json.dump(data, f, indent=2)

if __name__ == "__main__":
    asyncio.run(scrape_handguns())
