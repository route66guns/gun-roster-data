# image_resolver.py
# High-precision, tiered image resolver for firearm product images.
# Priority: Manufacturer page -> Trusted retailer page -> Bing Image API fallback.
# Uses JSON-LD Product.image or og:image where possible.
#
# Env:
#   BING_API_KEY  Azure Cognitive Services key for Bing Web/Image Search v7
#
# Files (optional):
#   config/allowlists.json     Override or extend manufacturer and retailer allowlists
#   image_overrides.json       Hard pin a specific image per model slug
#
# Output:
#   images/<slug>-<hash>.jpg   Cached image files
#
# Public API:
#   resolve_image(GunRecord) -> (pathlib.Path|None, str|None)

import os, re, json, time, hashlib, pathlib, urllib.parse, io
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import requests
from bs4 import BeautifulSoup

# JSON-LD extraction
try:
    import extruct
    from w3lib.html import get_base_url
except Exception as e:
    extruct = None
    get_base_url = None

# CV and image utils
try:
    import cv2
    import numpy as np
    OPENCV_OK = True
except Exception:
    OPENCV_OK = False
    np = None

try:
    from PIL import Image, ImageOps
    PIL_OK = True
except Exception:
    PIL_OK = False

BING_API_KEY = os.getenv("BING_API_KEY")
BING_ENDPOINT_IMAGE = "https://api.bing.microsoft.com/v7.0/images/search"
BING_ENDPOINT_WEB = "https://api.bing.microsoft.com/v7.0/search"

REPO_ROOT = pathlib.Path(__file__).resolve().parent
IMAGES_DIR = (REPO_ROOT / "images")
IMAGES_DIR.mkdir(exist_ok=True)

ALLOWLISTS_PATH = REPO_ROOT / "config" / "allowlists.json"
OVERRIDES_PATH = REPO_ROOT / "image_overrides.json"

# Built-in defaults; file can extend or override
DEFAULT_ALLOW_MANUFACTURERS = {
    "glock": ["us.glock.com", "glock.com"],
    "smith & wesson": ["www.smith-wesson.com"],
    "s&w": ["www.smith-wesson.com"],
    "sig sauer": ["www.sigsauer.com"],
    "springfield": ["www.springfield-armory.com"],
    "ruger": ["www.ruger.com", "ruger.com"],
    "cz": ["cz-usa.com", "www.cz-usa.com", "czub.cz"],
    "beretta": ["www.beretta.com", "www.beretta.com/en-us/"],
    "kimber": ["www.kimberamerica.com"],
    "walther": ["www.waltherarms.com", "waltherarms.com"],
    "fn": ["www.fnamerica.com", "fnamerica.com"],
    "heckler & koch": ["hk-usa.com", "www.hk-usa.com"],
    "taurus": ["www.taurususa.com"],
    "canik": ["www.canikusa.com"],
    "shadow systems": ["shadowsystemscorp.com"],
    "springfield armory": ["www.springfield-armory.com"],
    "stoeger": ["www.stoegerindustries.com"],
    "savage": ["www.savagearms.com"],
    "smith and wesson": ["www.smith-wesson.com"]
}

DEFAULT_ALLOW_RETAILERS = [
    "www.budsgunshop.com", "www.galleryofguns.com", "www.sportsmans.com",
    "www.brownells.com", "palmettostatearmory.com", "www.cabelas.com",
    "www.academy.com", "www.turners.com", "www.basspro.com",
    "gun.deals", "www.eurooptic.com", "www.scheels.com"
]

def _load_allowlists():
    allow_manu = dict(DEFAULT_ALLOW_MANUFACTURERS)
    allow_retail = list(DEFAULT_ALLOW_RETAILERS)
    if ALLOWLISTS_PATH.exists():
        try:
            data = json.loads(ALLOWLISTS_PATH.read_text())
            if isinstance(data, dict):
                if "manufacturer_domains" in data:
                    # Merge by brand keys; allow overriding or extending lists
                    for k, v in data["manufacturer_domains"].items():
                        if isinstance(v, list):
                            allow_manu[k.lower()] = v
                if "retailer_domains" in data and isinstance(data["retailer_domains"], list):
                    allow_retail = data["retailer_domains"]
        except Exception:
            pass
    return allow_manu, allow_retail

def _load_overrides():
    if OVERRIDES_PATH.exists():
        try:
            return json.loads(OVERRIDES_PATH.read_text())
        except Exception:
            return {}
    return {}

@dataclass
class GunRecord:
    brand: str
    model: str
    caliber: Optional[str] = None
    sku: Optional[str] = None
    roster_id: Optional[str] = None

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]

def _headers() -> Dict[str, str]:
    return {"Ocp-Apim-Subscription-Key": BING_API_KEY}

def _jsonld_images(html: str, url: str) -> List[str]:
    if not extruct or not get_base_url:
        return []
    base = get_base_url(html, url)
    try:
        data = extruct.extract(html, base_url=base, syntaxes=["json-ld"])
    except Exception:
        return []
    out = []
    for blob in data.get("json-ld", []):
        if isinstance(blob, dict):
            t = blob.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                img = blob.get("image")
                if isinstance(img, str):
                    out.append(img)
                elif isinstance(img, list):
                    out.extend([i for i in img if isinstance(i, str)])
    return out

def _og_image(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    return tag["content"].strip() if tag and tag.get("content") else None

def _strip_exif_and_save(content: bytes, dest_path: pathlib.Path) -> bool:
    # Save bytes; if PIL available, strip EXIF and re-save as JPEG
    try:
        dest_path.write_bytes(content)
        if PIL_OK:
            im = Image.open(io.BytesIO(content)).convert("RGB")
            # Remove EXIF by re-saving
            im = ImageOps.exif_transpose(im)
            im.save(dest_path, format="JPEG", quality=92, optimize=True)
        return True
    except Exception:
        return False

def _download_and_validate(url: str, dest_path: pathlib.Path) -> bool:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    content = r.content
    if len(content) < 30_000:  # avoid tiny thumbs
        return False
    # Basic shape checks with OpenCV if available
    if OPENCV_OK and np is not None:
        try:
            arr = np.frombuffer(content, dtype='uint8')
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                return False
            h, w = img.shape[:2]
            if min(h, w) < 900:  # resolution threshold
                return False
            aspect = w / max(h, 1)
            if aspect < 0.8 or aspect > 2.2:
                # Allow 1:1 to landscape; reject extremes
                return False
            # Face rejection
            try:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                face_cascade = cv2.CascadeClassifier(cascade_path)
                faces = face_cascade.detectMultiScale(gray, 1.1, 5)
                if len(faces) > 0:
                    return False
            except Exception:
                pass
        except Exception:
            return False
    return _strip_exif_and_save(content, dest_path)

def _pick_first_valid(urls: List[str], dest: pathlib.Path) -> Optional[str]:
    seen = set()
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        try:
            if _download_and_validate(u, dest):
                return u
        except Exception:
            continue
    return None

def _bing_web_search(query: str, sites: List[str]) -> List[str]:
    if not BING_API_KEY:
        return []
    if not sites:
        return []
    # restrict with site: filters OR-ed together
    site_filter = " (" + " OR ".join([f"site:{s}" for s in sites]) + ")"
    q = query + site_filter
    r = requests.get(
        BING_ENDPOINT_WEB,
        headers=_headers(),
        params={"q": q, "count": 12, "responseFilter": "Webpages", "mkt": "en-US"},
        timeout=30
    )
    r.raise_for_status()
    j = r.json()
    urls = []
    for item in j.get("webPages", {}).get("value", []):
        url = item.get("url")
        if not url:
            continue
        host = urllib.parse.urlparse(url).netloc
        if host in sites:
            urls.append(url)
    return urls

def _extract_page_image(url: str) -> List[str]:
    try:
        h = requests.get(url, timeout=35)
        h.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(h.text, "html.parser")
    imgs = _jsonld_images(h.text, url)
    if not imgs:
        og = _og_image(soup)
        if og:
            imgs = [og]
    # normalize to absolute URLs
    abs_urls = []
    for u in imgs:
        abs_urls.append(urllib.parse.urljoin(url, u))
    return abs_urls

def _bing_image_search(query: str, allow_hosts: List[str]) -> List[str]:
    if not BING_API_KEY:
        return []
    params = {
        "q": query,
        "count": 30,
        "imageType": "Photo",
        "size": "Large",
        "safeSearch": "Moderate",
        "color": "Color",
        "mkt": "en-US",
    }
    r = requests.get(BING_ENDPOINT_IMAGE, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    out = []
    allow = set(allow_hosts or [])
    for v in j.get("value", []):
        host = urllib.parse.urlparse(v.get("hostPageUrl") or "").netloc
        if allow and host not in allow:
            continue
        content_url = v.get("contentUrl") or v.get("thumbnailUrl")
        if content_url:
            out.append(content_url)
    return out

def resolve_image(g: GunRecord) -> Tuple[Optional[pathlib.Path], Optional[str]]:
    allow_manu, allow_retail = _load_allowlists()
    overrides = _load_overrides()

    # normalized query variants
    brand = (g.brand or "").strip()
    model = (g.model or "").strip()
    if not brand or not model:
        return None, None

    slug = _slugify(f"{brand}-{model}-{g.caliber or ''}-{g.sku or ''}-{g.roster_id or ''}")
    base_query = f"{brand} {model}"
    filename = f"{slug}-{_hash(base_query)}.jpg"
    dest = IMAGES_DIR / filename

    # Overrides
    override_key = _slugify(f"{brand}-{model}-{g.caliber or ''}")
    ov = overrides.get(override_key)
    if ov:
        if _pick_first_valid([ov], dest):
            return dest, ov

    # Pass 1: Manufacturer pages
    manu_sites = []
    brand_lc = brand.lower()
    for key, domains in allow_manu.items():
        if key in brand_lc:
            manu_sites.extend(domains)
    manu_sites = list(dict.fromkeys(manu_sites))  # unique preserve order
    if manu_sites:
        urls = _bing_web_search(f"{brand} {model}", manu_sites)
        for page_url in urls:
            candidates = _extract_page_image(page_url)
            chosen = _pick_first_valid(candidates, dest)
            if chosen:
                return dest, chosen

    # Pass 2: Retailers
    retailer_pages = _bing_web_search(f"{brand} {model}", allow_retail)
    for page_url in retailer_pages:
        candidates = _extract_page_image(page_url)
        chosen = _pick_first_valid(candidates, dest)
        if chosen:
            return dest, chosen

    # Pass 3: Image search (restricted to allowlist hosts)
    image_candidates = _bing_image_search(f"{brand} {model}", allow_hosts=list(set(allow_retail + sum(allow_manu.values(), []))))
    chosen = _pick_first_valid(image_candidates, dest)
    if chosen:
        return dest, chosen

    return None, None
