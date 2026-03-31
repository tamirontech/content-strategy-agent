Identify underperforming pages via Google Search Console and refresh them with Claude.

Targets pages ranking in positions 11–20 (page 2) — highest ROI for content refresh.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<articles_dir> [--min-position N] [--max-position N] [--days N] [--min-impressions N] [--concurrency N] [--retry-failed] [--dry-run] [--provider anthropic|ollama]`
   - articles_dir is required
   - Defaults: --min-position 11, --max-position 20, --days 90, --min-impressions 50, --concurrency 2
2. Check that GSC_SERVICE_ACCOUNT_FILE and GSC_SITE_URL are set in .env. If missing, tell the user what to configure and stop.
3. If --dry-run is not specified and the batch is large, suggest running with --dry-run first to preview targets.
4. Build and run the refresh command:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python refresh.py --articles-dir "<dir>"`
   - Add flags as provided
5. Show the command, then execute it.
6. After completion, summarise:
   - Pages found in target position range
   - Refreshed / failed / skipped counts
   - Word count changes (before vs. after)
   - State file location (for resume on next run)

Requirements:
  GSC_SERVICE_ACCOUNT_FILE — path to Google Cloud service account JSON key
  GSC_SITE_URL             — your property URL in Google Search Console

Example invocations:
  /refresh articles/ --dry-run
  /refresh articles/
  /refresh articles/ --min-position 8 --max-position 25 --days 60
  /refresh articles/ --retry-failed
