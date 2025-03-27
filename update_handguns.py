
import asyncio
import json
import time
import re
import aiohttp
from datetime import datetime
from urllib.parse import quote
from playwright.async_api import async_playwright

DOJ_URL = "https://oag.ca.gov/firearms/certified-handguns/recently-added"
PLACEHOLDER_IMAGE = "https://raw.githubusercontent.com/route66guns/gun-roster-data/main/images/placeholder.jpg"

def clean_query(text):
    return re.sub(r'[^a-zA-Z0-9 ]+', '', text)

async def fetch_duckduckgo_image_api(search_query):
    query = quote(search_query)
    token_url = f"https://duckduckgo.com/?q={query}&iax=images&ia=images"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(token_url) as resp:
                html = await resp.text()
                await asyncio.sleep(1)
                vqd_match = re.search(r"vqd=['\"]?([a-zA-Z0-9-]+)['\"]?", html)
                if not vqd_match:
                    print(f"❌ Couldn't extract vqd token for '{search_query}'")
                    return PLACEHOLDER_IMAGE
                vqd = vqd_match.group(1)

            api_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={query}&vqd={vqd}"
            async with session.get(api_url) as api_resp:
                raw_text = await api_resp.text()
                data = json.loads(raw_text)
                if "results" in data and len(data["results"]) > 0:
                    return data["results"][0]["image"]
    except Exception as e:
        print(f"❌ API image fetch failed for '{search_query}': {e}")
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
                print(f"🔍 API image search: {search_query}")
                image_url = await fetch_duckduckgo_image_api(search_query)
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
