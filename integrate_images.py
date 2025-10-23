# integrate_images.py
# Enriches your scraped handguns JSON with vetted images using image_resolver.
# Usage:
#   python integrate_images.py --in sample_handguns.json --out handguns_with_images.json
# Optional:
#   --limit 50          Process only first N items during testing
#   --sleep 0.7         Sleep between network calls to be polite
# Env:
#   BING_API_KEY        Required for Bing lookups

import json, argparse, time, sys, pathlib, os
from typing import Dict, Any
from image_resolver import GunRecord, resolve_image

def load_json(p: pathlib.Path):
    return json.loads(p.read_text())

def save_json(p: pathlib.Path, data):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.6)
    args = ap.parse_args()

    inp = pathlib.Path(args.inp)
    outp = pathlib.Path(args.outp)

    handguns = load_json(inp)
    if not isinstance(handguns, list):
        print("Input must be a list of handgun dicts")
        sys.exit(1)

    out = []
    hits = 0
    miss = 0
    for i, h in enumerate(handguns):
        if args.limit and i >= args.limit:
            break
        brand = h.get("brand") or h.get("manufacturer") or ""
        model = h.get("model") or h.get("model_name") or ""
        caliber = h.get("caliber") or h.get("calibre")
        sku = h.get("sku") or h.get("upc")
        rid = h.get("roster_id") or h.get("doj_id")

        g = GunRecord(brand=brand, model=model, caliber=caliber, sku=sku, roster_id=rid)
        local_path, source_url = resolve_image(g)

        h["image_local"] = str(local_path.as_posix()) if local_path else None
        h["image_source"] = source_url
        out.append(h)

        if local_path:
            hits += 1
        else:
            miss += 1

        time.sleep(args.sleep)

    save_json(outp, out)
    print(f"Images resolved. OK: {hits}  MISS: {miss}")
    print(f"Wrote {len(out)} records to {outp}")

if __name__ == "__main__":
    main()
