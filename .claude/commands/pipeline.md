Run the full content strategy pipeline end-to-end for a business vertical.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<vertical> [--competitors domain1,domain2] [--pillars N] [--articles N] [--site-url url] [--provider anthropic|ollama] [--dry-run]`
   - vertical is required
   - All other arguments are optional
2. Explain to the user what the full pipeline will do:
   Step 1: Generate content strategy + keywords
   Step 2: Generate article briefs (N articles × N pillars)
   Step 3: Write all articles in parallel
   Step 4: Audit all articles (SEO + readability)
   Step 5: Build internal links (if --site-url provided)
3. If --dry-run is specified, run only Step 1 with --dry-run and show what would happen.
4. Otherwise, execute each step in sequence using Bash. Pass --provider through to every step.
   Use these output paths:
   - Strategy:  ./output/strategy.csv  (and strategy_*.json)
   - Briefs:    ./output/briefs/
   - Articles:  ./output/articles/
   - Audit:     ./output/articles/audit_report.csv
5. After each step completes successfully, confirm it and move to the next.
6. If any step fails, stop and tell the user what failed and how to resume from that step
   using the individual skill commands (/strategy, /briefs, /write, /audit, /link).
7. After all steps complete, show a final summary:
   - Pillars created
   - Total articles written and audit pass rate
   - Internal links injected (if applicable)
   - Suggested next step: /refresh after articles go live and accumulate GSC data

Example invocations:
  /pipeline B2B SaaS project management
  /pipeline ecommerce furniture --competitors wayfair.com ikea.com --articles 10 --site-url https://mysite.com
  /pipeline digital marketing agency --provider ollama --dry-run
