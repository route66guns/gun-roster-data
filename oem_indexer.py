# oem_indexer.py
# Build a local image index by crawling allowlisted manufacturer and retailer sites.
# No search engine APIs are used. We rely on sitemaps and constrained link walking.
#
# Output:
#   data/oem_image_index.json
#
# Strategy:
# 1) Load allowlisted domains and optional hints from config/allowlists.json
# 2) For each domain, try to find /sitemap.xml; parse all product-like URLs
# 3) Filter URLs using per-brand keywords and global keywords
# 4) For each candidate URL, fetch HTML and extract Product image via JSON-LD or og:image
# 5) Normalize brand + model name tokens and store canonical image URL
#
# Run:
#   python oem_indexer.py --brands "glock,smith & wesson" --max-per-site 300

import argparse, pathlib, re, json, time, urllib.parse
from typing import List, Dict, Any, Optional, Tuple
import requests
from bs4 import BeautifulSoup

try:
    import extruct
    from w3lib.html import get_base_url
    EXTRACT_OK = True
except Exception:
    EXTRACT_OK = False

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
ALLOWLISTS_PATH = REPO_ROOT / "config" / "allowlists.json"
CRAWL_RULES_PATH = REPO_ROOT / "config" / "crawl_rules.json"
INDEX_PATH = DATA_DIR / "oem_image_index.json"

DEFAULT_GLOBAL_KEYWORDS = ["pistol", "handgun", "revolver", "semi-auto", "semi auto"]

def load_json(p: pathlib.Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default

def get_sitemaps(base: str) -> List[str]:
    urls = []
    for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"]:
        url = urllib.parse.urljoin(f"https://{base}", path)
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and ("<urlset" in r.text or "<sitemapindex" in r.text):
                urls.append(url)
        except Exception:
            continue
    return urls

def parse_sitemap(xml_text: str) -> List[str]:
    # naive parsing to keep deps low
    urls = re.findall(r"<loc>(.*?)</loc>", xml_text, flags=re.I)
    return [u.strip() for u in urls if u.strip().startswith("http")]

def jsonld_images(html: str, url: str) -> Tuple[Optional[str], Optional[str]]:
    if not EXTRACT_OK:
        return None, None
    base = get_base_url(html, url)
    try:
        data = extruct.extract(html, base_url=base, syntaxes=["json-ld"])
    except Exception:
        return None, None
    best = None
    name = None
    for blob in data.get("json-ld", []):
        if isinstance(blob, dict):
            t = blob.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                img = blob.get("image")
                nm = blob.get("name")
                if isinstance(img, str):
                    best = img
                elif isinstance(img, list) and img:
                    best = img[0]
                if isinstance(nm, str):
                    name = nm
                if best:
                    break
    return best, name

def og_image_and_title(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
    img = og_img["content"].strip() if og_img and og_img.get("content") else None
    title = og_title["content"].strip() if og_title and og_title.get("content") else None
    if not title:
        ttag = soup.find("title")
        if ttag and ttag.text:
            title = ttag.text.strip()
    return img, title

def normalize_model(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", " ", t)
    # strip brand tokens and generic words
    return t.strip()

def brand_key(brand: str) -> str:
    return brand.lower().strip()

def should_keep(url: str, brand: str, brand_keywords: List[str], global_keywords: List[str]) -> bool:
    u = url.lower()
    if any(tok in u for tok in brand_keywords):
        return True
    if any(tok in u for tok in global_keywords):
        return True
    return False

def crawl_domain(domain: str, brand: str, hints: Dict[str, Any], max_per_site: int, delay: float) -> List[Tuple[str, str, str]]:
    # returns list of (model_name, image_url, page_url)
    out = []
    sitemaps = get_sitemaps(domain)
    urls = []
    for sm in sitemaps:
        try:
            txt = requests.get(sm, timeout=25).text
            urls.extend(parse_sitemap(txt))
        except Exception:
            continue
    # fallbacks: use seed paths if provided
    for seed in hints.get("seed_paths", []):
        urls.append(urllib.parse.urljoin(f"https://{domain}", seed))

    # uniq
    seen = set()
    urls = [u for u in urls if urllib.parse.urlparse(u).netloc == domain]
    brand_keywords = [brand.lower()] + hints.get("url_keywords", [])
    global_keywords = hints.get("global_keywords", DEFAULT_GLOBAL_KEYWORDS)

    candidates = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        if should_keep(u, brand, brand_keywords, global_keywords):
            candidates.append(u)
        if len(candidates) >= max_per_site:
            break

    for u in candidates[:max_per_site]:
        try:
            r = requests.get(u, timeout=25)
            if r.status_code != 200 or "<html" not in r.text.lower():
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            img, name = jsonld_images(r.text, u)
            if not img:
                img, name2 = og_image_and_title(soup)
                if not name and name2:
                    name = name2
            if img and name:
                out.append((name, img, u))
                time.sleep(delay)
        except Exception:
            continue
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", type=str, default="")
    ap.add_argument("--max-per-site", type=int, default=250)
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()

    allowlists = load_json(ALLOWLISTS_PATH, {})
    rules = load_json(CRAWL_RULES_PATH, {})
    manu = allowlists.get("manufacturer_domains", {})
    brand_hints = allowlists.get("brand_hints", {})
    if args.brands:
        wanted = set([b.strip().lower() for b in args.brands.split(",") if b.strip()])
        manu = {k: v for k, v in manu.items() if k.lower() in wanted}

    index = load_json(INDEX_PATH, {})
    total_hits = 0

    for brand, domains in manu.items():
        hints = brand_hints.get(brand.lower(), {})
        for d in domains:
            print(f"[{brand}] crawling {d}")
            triples = crawl_domain(d, brand, hints, args.max_per_site, args.delay)
            for name, img, page in triples:
                key = f"{brand.lower()}::{normalize_model(name)}"
                index[key] = {"brand": brand, "name": name, "image": img, "page": page, "domain": d}
                total_hits += 1
            print(f"[{brand}] {d} -> {len(triples)} items")

    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"Indexed {total_hits} products across {len(manu)} brands")
    print(f"Wrote {INDEX_PATH}")

if __name__ == "__main__":
    main()
