Generate a full pillar content strategy for the given business vertical.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<vertical> [--competitors domain1,domain2] [--pillars N] [--provider anthropic|ollama]`
   - The vertical is required (everything before any -- flags)
   - Extract --competitors, --pillars, --provider if present
2. Run the strategy command using Bash. Build the command from the parsed arguments:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python main.py --vertical "<vertical>"`
   - If --competitors provided: add `--competitors domain1 --competitors domain2` (one flag per domain)
   - If --pillars provided: add `--pillars N`
   - If --provider provided: add `--provider <value>`
3. Show the command you are about to run, then execute it.
4. After it completes, tell the user:
   - The output CSV file path
   - The strategy JSON file path (needed for the next step)
   - How to proceed: run `/briefs <strategy_json_path>` to generate article briefs

Example invocations:
  /strategy B2B SaaS project management
  /strategy ecommerce furniture --competitors wayfair.com ikea.com --pillars 5
  /strategy digital marketing agency --provider ollama
