Generate article briefs from a saved content strategy.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<strategy_json_path> [--articles N] [--pillars 1,2,3] [--provider anthropic|ollama]`
   - strategy_json_path is required
   - Extract --articles (default 20), --pillars (comma-separated), --provider if present
2. Verify the strategy JSON file exists. If not, tell the user and stop.
3. Build and run the briefs command:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python briefs.py --strategy "<path>"`
   - If --articles provided: add `--articles N`
   - If --pillars provided: add `--pillars <value>`
   - If --provider provided: add `--provider <value>`
4. Show the command, then execute it.
5. After completion, tell the user:
   - The briefs output directory
   - How to review: open `briefs_overview.csv` to edit titles, keywords, TOC before writing
   - How to proceed: run `/write <briefs_dir> <output_dir>` to write all articles

Example invocations:
  /briefs strategy_20240101_120000.json
  /briefs strategy_20240101_120000.json --articles 10 --pillars 1,2
  /briefs strategy_20240101_120000.json --provider ollama
