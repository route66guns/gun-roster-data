#!/usr/bin/env python3
# update_handguns.py
# Hardened scraper for the California DOJ "Recently Added" handgun roster.
# Key changes:
# - Reliable Chromium launch flags for CI
# - wait_until="domcontentloaded" then bounded "networkidle"
# - Specific selector wait for the data table
# - Resource blocking for speed and stability
# - Retries with backoff
# - Static HTML fallback using requests + BeautifulSoup
#
# Output:
#   sample_handguns.json  (list of dicts)
#
# You can adapt PARSE_COLUMNS to your exact fields later if the DOJ page adds or reorders columns.

import asyncio, json, os, re, sys
from typing import List, Dict, Any

DOJ_URL = "https://oag.ca.gov/firearms/certified-handguns/recently-added"
NAV_TIMEOUT_MS = 120_000
REQ_TIMEOUT_MS = 45_000
TABLE_SELECTOR = "table"  # Tighten if the table has an id or unique signature

REALISTIC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

# Map visible column names to our JSON keys
PARSE_COLUMNS = {
    "manufacturer": ["manufacturer", "make", "brand"],
    "model": ["model", "model name"],
    "caliber": ["caliber", "calibre"],
    "type": ["type", "action"],
    "barrel": ["barrel", "barrel length"],
    "finish": ["finish"],
    "notes": ["notes"],
    "added": ["date added", "added", "date"],
    "roster id": ["roster id", "cert number", "cert", "id"],
}

def normalize_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())

def pick_key(header: str) -> str:
    h = normalize_header(header)
    for key, aliases in PARSE_COLUMNS.items():
        if h == key or h in aliases:
            return key
    return h  # default raw header

async def make_context(pw):
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context = await browser.new_context(
        user_agent=REALISTIC_UA,
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 900},
        java_script_enabled=True,
        locale="en-US",
    )

    async def route_handler(route):
        rtype = route.request.resource_type
        if rtype in ("image", "media", "font"):
            return await route.abort()
        return await route.continue_()

    await context.route("**/*", route_handler)
    page = await context.new_page()
    page.set_default_timeout(REQ_TIMEOUT_MS)
    return browser, context, page

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

async def safe_goto(page, url, attempts=3):
    last_err = None
    for i in range(attempts):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except PWTimeout:
                pass
            await page.wait_for_selector(TABLE_SELECTOR, timeout=30_000)
            return
        except Exception as e:
            last_err = e
            await page.wait_for_timeout(2_000 * (i + 1))
    raise last_err if last_err else RuntimeError("Navigation failed without exception")

async def extract_table_with_playwright(page) -> List[Dict[str, Any]]:
    # Try to find the first visible table and parse it generically.
    table = await page.query_selector(TABLE_SELECTOR)
    if not table:
        return []
    # Headers
    header_cells = await table.query_selector_all("thead tr th")
    if not header_cells:
        header_cells = await table.query_selector_all("tr th")
    if not header_cells:
        # Try first row as header
        header_cells = await table.query_selector_all("tr:first-child td")
    headers = [pick_key((await cell.inner_text()).strip()) for cell in header_cells]

    # Rows
    body_rows = await table.query_selector_all("tbody tr")
    if not body_rows:
        # fallback for tables without <tbody>
        body_rows = await table.query_selector_all("tr")[1:]
    items = []
    for r in body_rows:
        cells = await r.query_selector_all("td")
        if not cells:
            continue
        values = [((await c.inner_text()) or "").strip() for c in cells]
        row = {}
        for i, v in enumerate(values):
            if i < len(headers):
                row[headers[i]] = v
        # Basic normalization
        item = {
            "brand": row.get("manufacturer") or row.get("brand") or "",
            "model": row.get("model") or "",
            "caliber": row.get("caliber") or "",
            "type": row.get("type") or "",
            "barrel": row.get("barrel") or "",
            "finish": row.get("finish") or "",
            "notes": row.get("notes") or "",
            "date_added": row.get("added") or row.get("date"),
            "roster_id": row.get("roster id") or row.get("cert number") or row.get("id"),
        }
        if item["brand"] or item["model"]:
            items.append(item)
    return items

# Static fallback
import requests
from bs4 import BeautifulSoup

def extract_table_with_bs4(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(TABLE_SELECTOR)
    if not table:
        return []
    # headers
    header_cells = table.select("thead tr th")
    if not header_cells:
        header_cells = table.select("tr th")
    if not header_cells:
        header_cells = table.select("tr:first-child td")
    headers = [pick_key(h.get_text(strip=True)) for h in header_cells]
    # rows
    body_rows = table.select("tbody tr")
    if not body_rows:
        trs = table.select("tr")
        body_rows = trs[1:] if len(trs) > 1 else []
    items = []
    for tr in body_rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        values = [td.get_text(strip=True) for td in tds]
        row = {}
        for i, v in enumerate(values):
            if i < len(headers):
                row[headers[i]] = v
        item = {
            "brand": row.get("manufacturer") or row.get("brand") or "",
            "model": row.get("model") or "",
            "caliber": row.get("caliber") or "",
            "type": row.get("type") or "",
            "barrel": row.get("barrel") or "",
            "finish": row.get("finish") or "",
            "notes": row.get("notes") or "",
            "date_added": row.get("added") or row.get("date"),
            "roster_id": row.get("roster id") or row.get("cert number") or row.get("id"),
        }
        if item["brand"] or item["model"]:
            items.append(item)
    return items

def static_fallback(url: str) -> List[Dict[str, Any]]:
    resp = requests.get(url, timeout=60, headers={"User-Agent": REALISTIC_UA})
    resp.raise_for_status()
    return extract_table_with_bs4(resp.text)

async def scrape_handguns() -> List[Dict[str, Any]]:
    print("Navigating to DOJ page...")
    async with async_playwright() as pw:
        browser, context, page = await make_context(pw)
        try:
            await safe_goto(page, DOJ_URL, attempts=3)
            data = await extract_table_with_playwright(page)
            if data:
                return data
            print("Playwright extracted no rows. Falling back to static parse of current HTML...")
            html = await page.content()
            data = extract_table_with_bs4(html)
            if data:
                return data
            print("Static parse from Playwright content failed. Trying requests fallback...")
            return static_fallback(DOJ_URL)
        finally:
            await context.close()
            await browser.close()

def write_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    items = asyncio.run(scrape_handguns())
    out_path = "sample_handguns.json"
    write_json(out_path, items)
    print(f"Wrote {len(items)} items to {out_path}")
