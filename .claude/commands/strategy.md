Generate a full pillar content strategy for the given business vertical.

User input: $ARGUMENTS

Instructions:
1. Parse the arguments. Expected format: `<vertical> [--competitors domain1,domain2] [--pillars N] [--provider anthropic|ollama]`
   - The vertical is required (everything before any -- flags)
   - Extract --competitors, --pillars, --provider if present
2. Run the strategy command using Bash. Build the command from the parsed arguments:
   - Base: `cd /Users/tamiralbalkhi/content-strategy-agent && python3 main.py "<vertical>"`
   - If --competitors provided: add `--competitors "domain1,domain2,domain3"` (comma-separated, single flag)
   - If --max-keywords provided: add `--max-keywords N`
   - If --location provided: add `--location <value>` (us, uk, ca, au, global)
   - If --provider provided: add `--provider <value>`
3. Show the command you are about to run, then execute it.
4. After it completes, tell the user:
   - The output CSV file path
   - The strategy JSON file path (needed for the next step)
   - How to proceed: run `/briefs <strategy_json_path>` to generate article briefs

Example invocations:
  /strategy B2B SaaS project management
  /strategy ecommerce furniture --competitors wayfair.com,ikea.com --max-keywords 50
  /strategy digital marketing agency --provider ollama --location uk
