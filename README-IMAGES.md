# Image Resolver Add-on

This pack adds a tiered, high-precision image resolver for roster items.
Priority: manufacturer product pages, then trusted retailers, then a restricted image search.

## Quick start

1. Copy everything from this pack into your repo root.
2. Add your Azure **BING_API_KEY** as a GitHub Actions secret.
3. Ensure your scraper outputs `sample_handguns.json` as a list of handgun dicts with at least `brand` and `model`.
4. Run locally:
   ```bash
   pip install -r requirements.txt
   export BING_API_KEY=...   # or set in your shell profile
   python integrate_images.py --in sample_handguns.json --out handguns_with_images.json
   ```
5. Deploy with the provided workflow or call `integrate_images.py` from your existing workflow.

## Mapping

We try to read commonly used keys:
- `brand` or `manufacturer`
- `model` or `model_name`
- optional `caliber`, `sku` or `upc`, and `roster_id` or `doj_id`

## Overrides

If a specific model is tricky, hard pin it in `image_overrides.json`:

```json
{
  "glock-19-gen3-9mm": "https://us.glock.com/-/media/global/images/products/pistols/g19/gen3/g19-gen3.png"
}
```

The key is a slug: `{brand}-{model}-{caliber}` lowercased with non-alphanumerics replaced by dashes.

## Allowlists

Edit `config/allowlists.json` to add or remove manufacturer or retailer domains. Manufacturer pages are preferred because they publish clean SKU hero images via JSON-LD `Product.image` or `og:image`. Retailers are used when OEM pages are missing or blocked. The last resort is a Bing image search restricted to those allowlisted hosts.

## Why this is cleaner

- Canonical images from OEM pages or structured retailer product pages
- Resolution, aspect, and face filters block user photos, thumbnails, and lifestyle shots
- EXIF is stripped on save for consistent orientation
- Local cache to prevent churn

## Notes

- To minimize API calls, use `--limit` during testing.
- If you already have a GH workflow, copy the `Run image enrichment` step and make sure the `images/` folder is tracked in git.
