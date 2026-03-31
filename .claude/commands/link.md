Build internal links across all articles using an LLM to find anchor opportunities.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<articles_dir> --site-url <url> [--concurrency N] [--min-relevance N] [--dry-run] [--provider anthropic|ollama]`
   - articles_dir is required
   - --site-url is required (your website base URL, e.g. https://yoursite.com)
   - Extract --concurrency (default 5), --min-relevance (default 7), --dry-run flag, --provider
2. Verify articles_dir exists and contains article_*.md files. If not, tell the user and stop.
3. If --site-url is missing, ask the user for it before proceeding.
4. Build and run the linker command:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python linker.py --articles "<dir>" --site-url "<url>"`
   - Add other flags as provided
5. Show the command, then execute it.
6. After completion, summarise:
   - Total links injected across all articles
   - Path to linking_report.csv
   - If --dry-run was used, remind user to re-run without it to apply the links

Example invocations:
  /link articles/ --site-url https://mysite.com
  /link articles/ --site-url https://mysite.com --min-relevance 8 --dry-run
  /link articles/ --site-url https://mysite.com --concurrency 3 --provider ollama
