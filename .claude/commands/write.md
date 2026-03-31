Run the parallel writing orchestrator to write all articles from briefs.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<briefs_dir> <output_dir> [--concurrency N] [--audit] [--min-score N] [--provider anthropic|ollama]`
   - briefs_dir is required (directory containing pillar_N/article_NN.json files)
   - output_dir is required (where written articles will be saved)
   - Extract --concurrency (default 3), --audit flag, --min-score (default 70), --provider
2. Verify briefs_dir exists and contains brief JSON files. If not, tell the user and stop.
3. Build and run the orchestrator command:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python orchestrator.py --briefs "<briefs_dir>" --output "<output_dir>"`
   - If --concurrency provided: add `--concurrency N`
   - If --audit flag present: add `--audit`
   - If --min-score provided: add `--min-score N`
   - If --provider provided: add `--provider <value>`
4. Show the command, then execute it. Warn the user this may take a while for large batches.
5. After completion, show the summary (completed / failed / skipped counts) and tell the user:
   - The output directory with written articles
   - How to proceed: run `/audit <output_dir>` to score all articles
   - If any articles need review: run `/audit <output_dir> --fix` to auto-fix them

Example invocations:
  /write briefs/ articles/
  /write briefs/ articles/ --concurrency 5 --audit --min-score 75
  /write briefs/ articles/ --provider ollama --concurrency 2
