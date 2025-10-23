# integrate_images.py
# Uses the free resolver that relies on your local OEM index. No paid API required.
# Usage:
#   python integrate_images.py --in sample_handguns.json --out handguns_with_images.json --limit 25
import json, argparse, time, sys, pathlib
from image_resolver_free import GunRecord, resolve_image

def load_json(p): return json.loads(pathlib.Path(p).read_text())
def save_json(p, data): pathlib.Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    items = load_json(args.inp)
    if not isinstance(items, list):
        print("Input must be a list of handgun dicts")
        sys.exit(1)

    out = []
    ok = 0
    miss = 0
    for i, h in enumerate(items):
        if args.limit and i >= args.limit: break
        brand = h.get("brand") or h.get("manufacturer") or ""
        model = h.get("model") or h.get("model_name") or ""
        g = GunRecord(
            brand=brand,
            model=model,
            caliber=h.get("caliber"),
            sku=h.get("sku") or h.get("upc"),
            roster_id=h.get("roster_id") or h.get("doj_id"),
        )
        local, src = resolve_image(g)
        h["image_local"] = str(local.as_posix()) if local else None
        h["image_source"] = src
        out.append(h)
        ok += 1 if local else 0
        miss += 1 if not local else 0
        time.sleep(args.sleep)

    save_json(args.outp, out)
    print(f"Resolved: {ok}  Missed: {miss}  Total: {len(out)}")

if __name__ == "__main__":
    main()
