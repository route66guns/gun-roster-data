# image_resolver_free.py
# Free resolver that does not use search APIs.
# Order:
#   1) Consult local data/oem_image_index.json (built by oem_indexer.py)
#   2) If missing, try direct product URL heuristics from allowlists (brand_hints.seed_paths)
#   3) If still missing, try retailer domains from allowlists with simple path guesses
#   4) As a last resort, do nothing; rely on image_overrides.json
#
import os, re, json, pathlib, urllib.parse, io, time
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import requests
from bs4 import BeautifulSoup

try:
    import extruct
    from w3lib.html import get_base_url
    EXTRACT_OK = True
except Exception:
    EXTRACT_OK = False

try:
    from PIL import Image, ImageOps
    PIL_OK = True
except Exception:
    PIL_OK = False

try:
    import cv2, numpy as np
    OPENCV_OK = True
except Exception:
    OPENCV_OK = False

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
IMAGES_DIR = REPO_ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)
INDEX_PATH = DATA_DIR / "oem_image_index.json"
ALLOWLISTS_PATH = REPO_ROOT / "config" / "allowlists.json"
OVERRIDES_PATH = REPO_ROOT / "image_overrides.json"

MIN_EDGE = 900

@dataclass
class GunRecord:
    brand: str
    model: str
    caliber: Optional[str] = None
    sku: Optional[str] = None
    roster_id: Optional[str] = None

def _slugify(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t

def _hash(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]

def _strip_exif_and_save(content: bytes, dest_path: pathlib.Path) -> bool:
    try:
        dest_path.write_bytes(content)
        if PIL_OK:
            im = Image.open(io.BytesIO(content)).convert("RGB")
            im = ImageOps.exif_transpose(im)
            im.save(dest_path, format="JPEG", quality=92, optimize=True)
        return True
    except Exception:
        return False

def _download_and_validate(url: str, dest_path: pathlib.Path) -> bool:
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    content = r.content
    if len(content) < 30_000:
        return False
    if OPENCV_OK:
        try:
            arr = np.frombuffer(content, dtype='uint8')
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                return False
            h, w = img.shape[:2]
            if min(h, w) < MIN_EDGE:
                return False
            aspect = w / max(h, 1)
            if aspect < 0.8 or aspect > 2.2:
                return False
        except Exception:
            return False
    return _strip_exif_and_save(content, dest_path)

def _extract_from_page(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        r = requests.get(url, timeout=25)
        if r.status_code != 200:
            return None, None
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        # JSON-LD Product
        if EXTRACT_OK:
            base = get_base_url(html, url)
            try:
                data = extruct.extract(html, base_url=base, syntaxes=["json-ld"])
                for blob in data.get("json-ld", []):
                    if isinstance(blob, dict):
                        t = blob.get("@type")
                        if t == "Product" or (isinstance(t, list) and "Product" in t):
                            img = blob.get("image")
                            name = blob.get("name")
                            if isinstance(img, list) and img:
                                img = img[0]
                            if isinstance(img, str):
                                return urllib.parse.urljoin(url, img), name
            except Exception:
                pass
        # og:image fallback
        tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        img = tag["content"].strip() if tag and tag.get("content") else None
        name = title["content"].strip() if title and title.get("content") else None
        return img, name
    except Exception:
        return None, None

def _load_json(p: pathlib.Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default

def resolve_image(g: GunRecord) -> Tuple[Optional[pathlib.Path], Optional[str]]:
    overrides = _load_json(OVERRIDES_PATH, {})
    index = _load_json(INDEX_PATH, {})
    allowlists = _load_json(ALLOWLISTS_PATH, {})
    brand = (g.brand or "").strip()
    model = (g.model or "").strip()
    if not brand or not model:
        return None, None

    slug = _slugify(f"{brand}-{model}-{g.caliber or ''}-{g.sku or ''}-{g.roster_id or ''}")
    filename = f"{slug}-{_hash(brand + model)}.jpg"
    dest = IMAGES_DIR / filename

    # Overrides first
    ov_key = _slugify(f"{brand}-{model}-{g.caliber or ''}")
    if ov_key in overrides:
        if _download_and_validate(overrides[ov_key], dest):
            return dest, overrides[ov_key]

    # Index lookup
    key = f"{brand.lower()}::{model.lower()}"
    # Fuzzy: try normalized collapse of spaces
    if key not in index:
        # walk keys to find close match
        for k in list(index.keys()):
            if k.startswith(brand.lower() + "::") and model.lower() in k:
                key = k
                break
    rec = index.get(key)
    if rec and rec.get("image"):
        if _download_and_validate(rec["image"], dest):
            return dest, rec["image"]

    # Heuristic direct tries on allowlisted domains
    manu = allowlists.get("manufacturer_domains", {})
    brand_hints = allowlists.get("brand_hints", {})
    domains = manu.get(brand.lower()) or []
    hints = brand_hints.get(brand.lower(), {})
    try_paths = hints.get("seed_paths", [])
    for d in domains:
        for p in try_paths:
            # Replace wildcards with model tokens
            candidate = p.replace("{model}", _slugify(model)).replace("{model_raw}", model.replace(" ", "-"))
            url = urllib.parse.urljoin(f"https://{d}", candidate)
            img, _ = _extract_from_page(url)
            if img and _download_and_validate(img, dest):
                return dest, img

    # Retailer heuristics
    retailers = allowlists.get("retailer_domains", [])
    retailer_paths = allowlists.get("retailer_paths", ["/product/{model}", "/shop/{model}"])
    for d in retailers:
        for p in retailer_paths:
            candidate = p.replace("{model}", _slugify(model)).replace("{model_raw}", model.replace(" ", "-"))
            url = urllib.parse.urljoin(f"https://{d}", candidate)
            img, _ = _extract_from_page(url)
            if img and _download_and_validate(img, dest):
                return dest, img

    return None, None
