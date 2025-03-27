
import asyncio
from playwright.async_api import async_playwright
import json
from datetime import datetime

async def scrape_handguns():
    url = "https://oag.ca.gov/firearms/certified-handguns/recent"
    handguns = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_selector("table")  # Wait for the table to load

        rows = await page.query_selector_all("table tr")

        for row in rows[1:]:  # Skip header row
            cells = await row.query_selector_all("td")
            if len(cells) >= 5:
                manufacturer = await cells[0].inner_text()
                model = await cells[1].inner_text()
                caliber = await cells[2].inner_text()
                gun_type = await cells[3].inner_text()
                barrel_length = await cells[4].inner_text()
                date_added = await cells[5].inner_text() if len(cells) > 5 else ""

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
                    "image_url": "https://via.placeholder.com/150x100?text=" + model.replace(" ", "+")
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
