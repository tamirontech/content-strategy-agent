# Content Strategy Agent

An AI-powered content operations pipeline that takes a business vertical and produces a full SEO content strategy — from keyword research and pillar planning through article writing, auditing, internal linking, and content refresh.

## Overview

```
Business Vertical
       │
       ▼
  Strategy Agent          ← pillar topics + keyword clusters (DataForSEO)
       │
       ▼
  Competitor Analysis     ← gap keywords from rival domains
       │
       ▼
  Brief Generator         ← 20 article briefs per pillar (title, TOC, keywords)
       │
       ▼
  Writing Orchestrator    ← parallel agents write all articles (Claude / Ollama)
       │
       ▼
  SEO Audit               ← 10-check scoring engine + auto-fix
       │
       ▼
  Quality Check           ← grammar (LanguageTool), readability (Hemingway), Grammarly API
       │
       ▼
  Internal Linking        ← LLM finds anchor opportunities + injects links safely
       │
       ▼
  Content Refresh         ← GSC identifies page-2 rankings → rewrites with Claude
```

## Features

- **Dual LLM support** — Anthropic Claude (`claude-opus-4-6`) or any local Ollama model
- **Real keyword data** — DataForSEO Google Ads API for keyword ideas and competitor analysis
- **State persistence** — all workflows resume from where they left off after interruption
- **Parallel execution** — configurable concurrency across all agent workflows
- **CI/CD gate** — `audit.py` exits with code 1 if articles fall below quality threshold

## Installation

```bash
git clone https://github.com/tamirontech/content-strategy-agent
cd content-strategy-agent
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | No | `anthropic` (default) or `ollama` |
| `LLM_MODEL` | No | Model override (default: `claude-opus-4-6`) |
| `ANTHROPIC_API_KEY` | Yes* | Required when using Anthropic |
| `OLLAMA_HOST` | No | Ollama server URL (default: `http://localhost:11434`) |
| `DATAFORSEO_LOGIN` | Yes* | Required for keyword research |
| `DATAFORSEO_PASSWORD` | Yes* | Required for keyword research |
| `GSC_SERVICE_ACCOUNT_FILE` | Yes* | Required for content refresh |
| `GSC_SITE_URL` | Yes* | Your site URL in Google Search Console |
| `LANGUAGETOOL_URL` | No | Self-hosted LanguageTool instance URL |
| `GRAMMARLY_CLIENT_ID` | No | Grammarly enterprise API client ID |
| `GRAMMARLY_CLIENT_SECRET` | No | Grammarly enterprise API client secret |

\* Required only for the relevant workflow step.

## Claude Code Skills

If you open this project in [Claude Code](https://claude.ai/code), seven slash commands are available that wrap the full pipeline. No need to remember CLI flags — just describe what you want.

### Quick start

```
/pipeline "B2B SaaS project management" --site-url https://mysite.com
```

That single command runs the entire pipeline: strategy → briefs → write → audit → link.

### Individual skills

| Command | Description |
|---------|-------------|
| `/strategy <vertical> [--competitors domain1,domain2] [--pillars N]` | Generate pillar strategy + keyword research |
| `/briefs <strategy_json> [--articles N] [--pillars 1,2,3]` | Create article briefs from saved strategy |
| `/write <briefs_dir> <output_dir> [--concurrency N] [--audit]` | Write all articles in parallel |
| `/audit <path> [--grammar] [--readability] [--grammarly] [--fix]` | Score articles + optional quality checks |
| `/link <articles_dir> --site-url <url> [--dry-run]` | Build internal links across all articles |
| `/refresh <articles_dir> [--dry-run]` | Refresh page-2 GSC rankings with Claude |
| `/pipeline <vertical> [--competitors ...] [--site-url url]` | Full end-to-end pipeline in one command |

All skills accept `--provider anthropic|ollama` and `--model <name>` to switch LLM backends.

### Example workflow

```
# Step 1 — build strategy with competitor gap analysis
/strategy ecommerce furniture --competitors wayfair.com ikea.com --pillars 5

# Step 2 — generate 20 briefs per pillar, review briefs_overview.csv before writing
/briefs strategy_20240101_120000.json --articles 20

# Step 3 — write all 100 articles with SEO audit gate
/write briefs/ articles/ --concurrency 5 --audit --min-score 75

# Step 4 — deep quality audit with grammar + readability annotation files
/audit articles/ --grammar --readability --review-files

# Step 5 — inject internal links
/link articles/ --site-url https://mysite.com

# Later, once articles are live and indexed — refresh page-2 rankings
/refresh articles/ --dry-run   # preview targets first
/refresh articles/              # run the refresh
```

---

## Usage (CLI)

### 1. Generate a Content Strategy

```bash
python main.py --vertical "B2B SaaS project management" --output strategy.csv
```

With competitor analysis:

```bash
python main.py \
  --vertical "B2B SaaS project management" \
  --competitors asana.com monday.com clickup.com \
  --output strategy.csv
```

Options:
```
--vertical TEXT       Business vertical or industry  [required]
--competitors TEXT    Competitor domains (repeatable)
--pillars INT         Number of content pillars (default: 5)
--keywords INT        Keywords per pillar (default: 20)
--output PATH         Output CSV path
--provider TEXT       LLM provider: anthropic or ollama
--model TEXT          Model override
```

### 2. Generate Article Briefs

```bash
python briefs.py --strategy strategy_*.json --articles 20
```

Produces a `briefs/` directory with:
- `briefs_overview.csv` — all briefs in one spreadsheet for review
- `pillar_N/article_NN.json` — individual brief files for the writer

Options:
```
--strategy PATH       Strategy JSON saved by main.py  [required]
--articles INT        Articles per pillar (default: 20)
--pillars TEXT        Comma-separated pillar numbers to generate (default: all)
--provider TEXT       LLM provider
--model TEXT          Model override
```

### 3. Write Articles

```bash
python orchestrator.py --briefs briefs/ --output articles/ --concurrency 3
```

Resumes automatically — already-written articles are skipped.

With built-in SEO audit gate:

```bash
python orchestrator.py --briefs briefs/ --output articles/ --audit --min-score 75
```

Options:
```
--briefs PATH         Directory of brief JSON files  [required]
--output PATH         Output directory for articles  [required]
--concurrency INT     Parallel writers (default: 3)
--audit               Run SEO audit after each article is written
--min-score INT       Minimum audit score to pass (default: 70)
--provider TEXT       LLM provider
--model TEXT          Model override
```

### 4. Audit Articles

```bash
python audit.py articles/
```

With grammar and readability checks:

```bash
python audit.py articles/ --grammar --readability --review-files
```

With auto-fix for failing articles:

```bash
python audit.py articles/ --min-score 80 --fix
```

Options:
```
PATH                  Article file or directory  [required]
--min-score INT       Passing threshold (default: 70)
--fix                 Auto-fix failing articles with Claude
--grammar             Run LanguageTool grammar check
--readability         Run Hemingway-style readability analysis
--grammarly           Run Grammarly Writing Score API
--review-files        Write article_NN.review.md annotation files
--output PATH         CSV report path
--provider TEXT       LLM provider (used with --fix)
--model TEXT          Model override (used with --fix)
```

The audit scores 10 checks totalling 100 points:

| Check | Points |
|-------|--------|
| Keyword density (3–8 per 1000 words) | 15 |
| Word count vs. target | 15 |
| Title contains primary keyword | 10 |
| Keyword in introduction | 10 |
| Heading structure (H2/H3 hierarchy) | 10 |
| Meta description (140–160 chars) | 10 |
| Secondary keyword coverage | 10 |
| FAQ section present | 10 |
| Internal links (≥2) | 10 |
| CTA present near end | 5 |

### 5. Internal Linking

```bash
python linker.py --articles articles/ --site-url https://yoursite.com
```

Options:
```
--articles PATH       Articles directory  [required]
--site-url TEXT       Base URL for internal links  [required]
--concurrency INT     Parallel link agents (default: 5)
--min-relevance INT   Minimum relevance score 1–10 (default: 7)
--dry-run             Show opportunities without injecting
```

Produces `linking_report.csv` with before/after link counts per article.

### 6. Content Refresh

Identifies page-2 Google rankings (positions 11–20) and rewrites those articles to target page 1.

```bash
python refresh.py --articles-dir articles/
```

Options:
```
--articles-dir PATH   Articles directory  [required]
--min-position FLOAT  Lower bound for target range (default: 11)
--max-position FLOAT  Upper bound for target range (default: 20)
--days INT            GSC data lookback window (default: 90)
--min-impressions INT Minimum impressions threshold (default: 50)
--concurrency INT     Parallel refresh agents (default: 2)
--retry-failed        Retry previously failed refreshes
--dry-run             Show targets without modifying files
```

## Quality Checks

### LanguageTool (free, `--grammar`)

Uses the [LanguageTool REST API](https://languagetool.org/http-api/) for grammar, spelling, and style errors. No account required for the public API (rate-limited). For high volume, run a self-hosted instance:

```bash
docker run -p 8010:8010 erikvl87/languagetool
# Then set: LANGUAGETOOL_URL=http://localhost:8010
```

### Hemingway Metrics (free, `--readability`)

Algorithmic analysis — no external API:

- Flesch-Kincaid grade level and reading ease score
- Passive voice detection
- Adverb flagging
- Hard / very-hard sentence identification
- Complex word suggestions

### Grammarly Writing Score API (`--grammarly`)

Requires a [Grammarly Enterprise](https://developer.grammarly.com/) account. Returns an overall writing score (0–100) with correctness, clarity, engagement, and delivery breakdowns.

### Review Files (`--review-files`)

When enabled, writes an `article_NN.review.md` alongside each article with:
- Summary metrics table
- Categorised inline annotations (grammar, spelling, style, readability)
- Severity indicators (error / warning / suggestion)
- Suggested replacements

## Article Format

Articles are written as Markdown with YAML front matter:

```markdown
---
title: "Your Article Title"
slug: "your-article-slug"
primary_keyword: "target keyword"
secondary_keywords: "keyword one | keyword two | keyword three"
meta_description: "150-character meta description with primary keyword"
word_count_target: 2000
cta: "Start your free trial"
pillar: "Pillar Name"
---

# Your Article Title

...
```

## Using Ollama (Local Models)

```bash
# Pull a model
ollama pull llama3.1:8b

# Run any workflow with Ollama
python main.py --vertical "SaaS" --provider ollama --model llama3.1:8b
python orchestrator.py --briefs briefs/ --output articles/ --provider ollama --model llama3.1:8b
```

Or set in `.env`:
```
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
```

## Project Structure

```
content-strategy-agent/
├── .claude/
│   └── commands/
│       ├── pipeline.md  # /pipeline — full end-to-end skill
│       ├── strategy.md  # /strategy skill
│       ├── briefs.md    # /briefs skill
│       ├── write.md     # /write skill
│       ├── audit.md     # /audit skill
│       ├── link.md      # /link skill
│       └── refresh.md   # /refresh skill
├── main.py              # Strategy + keyword research CLI
├── agent.py             # Pillar strategy generation agent
├── keywords.py          # DataForSEO keyword API client
├── competitors.py       # DataForSEO competitor analysis
├── writer.py            # CSV output formatter
├── briefs.py            # Content brief generation CLI
├── brief_generator.py   # Article brief LLM agent
├── brief_writer.py      # Brief CSV + JSON file writer
├── orchestrator.py      # Parallel writing orchestrator
├── article_writer.py    # Article writing LLM agent
├── audit.py             # SEO audit CLI
├── auditor.py           # Algorithmic SEO scoring engine
├── audit_report.py      # Audit CSV/JSON report writer
├── quality_check.py     # Grammar + readability quality checks
├── linker.py            # Internal linking CLI
├── content_map.py       # Article content map builder
├── link_finder.py       # LLM anchor opportunity finder
├── link_injector.py     # Safe Markdown link injector
├── refresh.py           # Content refresh CLI
├── refresh_agent.py     # Article refresh LLM agent
├── gsc.py               # Google Search Console API client
├── llm.py               # Unified LLM abstraction (Anthropic + Ollama)
├── requirements.txt
└── .env.example
```

## License

MIT
