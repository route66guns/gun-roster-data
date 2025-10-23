# Free Image Resolver Pipeline

This pack removes paid search APIs. It builds a local OEM image index by crawling allowlisted manufacturer sites and then enriches your roster items using that index. No keys required.

## Files

- `oem_indexer.py` crawls allowlisted domains and writes `data/oem_image_index.json` using JSON-LD Product.image or og:image.
- `image_resolver_free.py` looks up images from the index, tries direct product URLs based on brand hints, then retailer heuristics.
- `integrate_images.py` enriches your `sample_handguns.json` with `image_local` and `image_source` while caching into `images/`.
- `config/allowlists.json` includes manufacturer and retailer lists plus per-brand `seed_paths` and URL keywords.
- `config/crawl_rules.json` global knobs for crawl limits and keywords.
- `image_overrides.json` pin tricky items.
- `.github/workflows/oem-image-pipeline.yml` builds the index weekly and enriches daily.
- `requirements.txt` Python deps only.

## Quick start

1. Copy these files into your repo root.
2. `pip install -r requirements.txt`
3. Build the index locally:
   ```bash
   python oem_indexer.py --max-per-site 200
   ```
4. Enrich a small batch for review:
   ```bash
   python integrate_images.py --in sample_handguns.json --out handguns_with_images.json --limit 25
   ```
5. If results look good, commit and enable the GitHub Actions workflow. It will keep `data/oem_image_index.json` fresh weekly and enrich images daily.

## Tuning

- Add brands and domains under `manufacturer_domains` and hints under `brand_hints`.
- Add retailer domains only if they publish clean product pages with og:image or JSON-LD.
- Use `image_overrides.json` to hard-pin any model that still fails matching.

## Why this is reliable

- You pull images directly from OEM or reputable retailer product pages.
- JSON-LD Product.image provides canonical hero images and is widely adopted.
- The resolver rejects tiny or odd-aspect images and saves JPEGs with stripped EXIF for consistent orientation.

## Limitations

- Some OEMs use heavy JavaScript or gated product finders. For those, rely on retailer pages or use overrides.
- The indexer keeps a conservative crawl budget to be polite. Increase `--max-per-site` as needed.
