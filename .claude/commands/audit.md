Audit SEO quality of written articles with optional grammar and readability checks.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<path> [--min-score N] [--fix] [--grammar] [--readability] [--grammarly] [--review-files] [--provider anthropic|ollama]`
   - path is required (single article .md file or articles directory)
   - Extract all flags: --min-score (default 70), --fix, --grammar, --readability, --grammarly, --review-files, --provider
2. Verify the path exists. If not, tell the user and stop.
3. If --grammarly is requested, check that GRAMMARLY_CLIENT_ID and GRAMMARLY_CLIENT_SECRET are set in .env. Warn if missing.
4. Build and run the audit command:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python audit.py "<path>"`
   - Add flags as provided
5. Show the command, then execute it.
6. After completion, summarise:
   - Pass/fail counts and overall score distribution
   - If review files were written, remind user to check article_NN.review.md files
   - If articles still failing, suggest running with --fix

The 10 SEO checks (100 points total):
  keyword_density (15), word_count (15), title_has_keyword (10), keyword_in_intro (10),
  heading_structure (10), meta_description (10), secondary_keywords (10), faq_section (10),
  internal_links (10), cta_present (5)

Quality check penalties (when --grammar or --readability used):
  Grammar errors: up to -10pts | Readability grade >12: up to -5pts

Example invocations:
  /audit articles/
  /audit articles/ --min-score 80 --grammar --readability --review-files
  /audit articles/pillar_1/article_03.md --fix
  /audit articles/ --grammarly --review-files
