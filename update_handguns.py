import asyncio
import json
import time
import re
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.async_api import async_playwright

DOJ_URL = "https://oag.ca.gov/firearms/certified-handguns/recently-added"
PLACEHOLDER_IMAGE = "https://raw.githubusercontent.com/route66guns/gun-roster-data/main/images/placeholder.jpg"

def clean_query(text):
    return re.sub(r'[^a-zA-Z0-9 ]+', '', text)

def enhance_bing_image_url(url, width=800, height=600):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["w"] = [str(width)]
    query["h"] = [str(height)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

async def fetch_bing_image(page, search_query):
    try:
        await page.goto(f"https://www.bing.com/images/search?q={search_query.replace(' ', '+')}&form=HDRSC2")
        await page.wait_for_selector("img.mimg", timeout=10000)
        image = await page.query_selector("img.mimg")
        src = await image.get_attribute("src")
        if src and src.startswith("http"):
            high_res_url = enhance_bing_image_url(src)
            return high_res_url
    except Exception as e:
        print(f"❌ Bing image fetch failed for '{search_query}': {e}")
    return PLACEHOLDER_IMAGE

async def scrape_handguns():
    handguns = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        doj_page = await context.new_page()
        print("Navigating to DOJ page...")
        await doj_page.goto(DOJ_URL, timeout=90000)

        try:
            print("Waiting for DOJ table...")
            await doj_page.wait_for_selector("table.views-table", timeout=90000)
            print("✅ DOJ Table found.")
        except Exception as e:
            print("❌ DOJ Table not found:", e)
            await doj_page.screenshot(path="page_debug.png", full_page=True)
            await browser.close()
            return

        row_count = await doj_page.locator("table.views-table tr").count()

        bing_page = await context.new_page()

        for i in range(1, row_count):  # Skip header row
            row = doj_page.locator("table.views-table tr").nth(i)
            cells = row.locator("td")
            cell_count = await cells.count()

            if cell_count >= 5:
                manufacturer = await cells.nth(0).inner_text()
                model = await cells.nth(1).inner_text()
                caliber = await cells.nth(2).inner_text()
                gun_type = await cells.nth(3).inner_text()
                barrel_length = await cells.nth(4).inner_text()
                date_added = await cells.nth(5).inner_text() if cell_count > 5 else ""

                cleaned_manufacturer = clean_query(manufacturer)
                cleaned_model = clean_query(model)
                search_query = f"{cleaned_manufacturer} {cleaned_model} handgun"
                print(f"🔍 Bing image search: {search_query}")
                image_url = await fetch_bing_image(bing_page, search_query)
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
