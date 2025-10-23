# Scraper hardening patch

This patch fixes navigation timeouts on the California DOJ "recently added" roster.

What changed
- Playwright launches Chromium with CI-safe flags and blocks heavy resources.
- Navigation waits for DOMContentLoaded, then bounded network idle, then the actual table.
- Retries with backoff are in place.
- If Playwright still fails, the script parses the HTML statically with requests + BeautifulSoup.
- The workflow installs browsers with `playwright install --with-deps chromium` and removes xvfb.

How to use
1. Drop `update_handguns.py` into your repo root, replacing the old file.
2. Put `.github/workflows/scrape-handguns.yml` into your repo to run the job on schedule or manually.
3. Ensure `requirements.txt` contains at least: playwright, beautifulsoup4, lxml, requests.
4. Run locally for a smoke test:
   ```bash
   pip install playwright beautifulsoup4 lxml requests
   playwright install chromium
   python update_handguns.py
   ```
5. The script writes `sample_handguns.json` in the repo root.
