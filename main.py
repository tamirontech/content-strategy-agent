import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import llm
from agent import generate_strategy
from competitors import get_competitor_keywords, build_overlap_map, find_gap_keywords
from keywords import DataForSEOClient, expand_keywords_for_pillars
from writer import write_csv

console = Console()

# DataForSEO location codes for common markets
LOCATION_CODES = {
    "us": 2840,
    "united states": 2840,
    "uk": 2826,
    "united kingdom": 2826,
    "gb": 2826,
    "canada": 2124,
    "ca": 2124,
    "australia": 2036,
    "au": 2036,
    "global": None,
}


@click.command()
@click.argument("vertical")
@click.option(
    "--output", "-o",
    default=None,
    help="Output CSV file path. Defaults to auto-generated name.",
)
@click.option(
    "--location", "-l",
    default="us",
    show_default=True,
    help="Target location for keyword data: us, uk, ca, au, global.",
)
@click.option(
    "--language",
    default="en",
    show_default=True,
    help="Language code for keyword data.",
)
@click.option(
    "--max-keywords", "-k",
    default=50,
    type=int,
    show_default=True,
    help="Max keywords to fetch per pillar from DataForSEO.",
)
@click.option(
    "--competitors", "-c",
    default=None,
    help="Comma-separated competitor domains to analyse (e.g. hubspot.com,bamboohr.com).",
)
@click.option(
    "--provider",
    default=None,
    help="LLM provider: anthropic (default) or ollama.",
)
@click.option(
    "--model",
    default=None,
    help="Model override (e.g. llama3.2, mistral, claude-haiku-4-5).",
)
def main(vertical: str, output: str, location: str, language: str, max_keywords: int, competitors: str, provider: str, model: str):
    """Generate a pillar content strategy with real keyword data for a business VERTICAL.

    \b
    Examples:
      python main.py "dental clinic"
      python main.py "B2B HR software" --location us --max-keywords 100
      python main.py "e-commerce fashion" --location uk -o fashion_strategy.csv
      python main.py "B2B HR software" -c "hubspot.com,bamboohr.com,gusto.com"
    """
    # Apply provider/model overrides before any LLM calls
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    # Validate required env vars
    missing = []
    if llm.get_provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("DATAFORSEO_LOGIN"):
        missing.append("DATAFORSEO_LOGIN")
    if not os.getenv("DATAFORSEO_PASSWORD"):
        missing.append("DATAFORSEO_PASSWORD")
    if missing:
        console.print(f"[red]Error:[/red] Missing environment variables: {', '.join(missing)}")
        console.print("Copy [bold].env.example[/bold] to [bold].env[/bold] and fill in your credentials.")
        sys.exit(1)

    # Resolve location code
    location_code = LOCATION_CODES.get(location.lower().strip())
    if location.lower().strip() not in LOCATION_CODES:
        console.print(
            f"[yellow]Warning:[/yellow] Unknown location '{location}'. "
            "Use: us, uk, ca, au, or global. Defaulting to global."
        )
        location_code = None

    # Auto-generate output path if not provided
    if output is None:
        slug = vertical.lower().replace(" ", "_")[:30].strip("_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"content_strategy_{slug}_{timestamp}.csv"

    console.print()
    console.rule("[bold cyan]Content Strategy Agent[/bold cyan]")
    competitor_list = [d.strip() for d in competitors.split(",")] if competitors else []

    console.print(f"  Vertical  : [bold]{vertical}[/bold]")
    console.print(f"  LLM       : {llm.provider_label()}")
    console.print(f"  Location  : {location.upper()}")
    console.print(f"  Language  : {language}")
    console.print(f"  Keywords  : up to {max_keywords} per pillar")
    if competitor_list:
        console.print(f"  Competitors: {', '.join(competitor_list)}")
    console.print(f"  Output    : {output}")
    console.print()

    # --- Step 1: Claude generates pillars + seed keywords ---
    with console.status(
        "[bold green]Step 1/3[/bold green] — Analyzing vertical and generating pillars with Claude...",
        spinner="dots",
    ):
        strategy = generate_strategy(vertical)

    console.print(
        f"[green]✓[/green] Generated [bold]{len(strategy['pillars'])} pillars[/bold] "
        f"— {strategy['vertical_summary']}"
    )
    for p in strategy["pillars"]:
        console.print(f"  [dim]{p['number']}.[/dim] {p['title']}  [dim]({p['search_intent']})[/dim]")
    console.print()

    # --- Step 2: DataForSEO expands keywords for each pillar ---
    dataforseo = DataForSEOClient(
        login=os.environ["DATAFORSEO_LOGIN"],
        password=os.environ["DATAFORSEO_PASSWORD"],
    )

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task(
            "[bold green]Step 2/3[/bold green] — Fetching keyword data from Google via DataForSEO...",
            total=None,
        )
        keyword_data = expand_keywords_for_pillars(
            dataforseo,
            strategy["pillars"],
            location_code=location_code,
            language_code=language,
            max_keywords=max_keywords,
        )
        progress.update(task, completed=True)

    total_kw = sum(len(v) for v in keyword_data.values())
    console.print(f"[green]✓[/green] Fetched [bold]{total_kw} keywords[/bold] across {len(keyword_data)} pillars")
    console.print()

    # --- Step 3 (optional): Competitor analysis ---
    overlap_map = {}
    gap_keywords = []

    if competitor_list:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task(
                f"[bold green]Step 3/4[/bold green] — Analysing {len(competitor_list)} competitor(s)...",
                total=None,
            )
            competitor_keywords = get_competitor_keywords(
                dataforseo,
                competitor_list,
                location_code=location_code,
                language_code=language,
            )
            progress.update(task, completed=True)

        overlap_map = build_overlap_map(competitor_keywords)
        strategy_kw_set = {
            kw["keyword"].lower()
            for kws in keyword_data.values()
            for kw in kws
        }
        gap_keywords = find_gap_keywords(competitor_keywords, strategy_kw_set)

        comp_total = sum(len(v) for v in competitor_keywords.values())
        console.print(
            f"[green]✓[/green] Found [bold]{comp_total} competitor keywords[/bold], "
            f"[bold]{len(gap_keywords)} gaps[/bold] not in your strategy"
        )
        console.print()

    step_label = "Step 4/4" if competitor_list else "Step 3/3"

    # --- Final Step: Write CSV + save JSON for briefs.py ---
    stem = Path(output).stem  # e.g. "content_strategy_b2b_hr_software_20240101_120000"
    strategy_json_path = Path(output).parent / f"strategy_{stem.removeprefix('content_strategy_')}.json"
    keywords_json_path = Path(output).parent / f"keywords_{stem.removeprefix('content_strategy_')}.json"

    with console.status(f"[bold green]{step_label}[/bold green] — Writing CSV and JSON...", spinner="dots"):
        rows_written = write_csv(strategy, keyword_data, output, overlap_map, gap_keywords)

        # Save strategy + keywords JSON for use by briefs.py
        strategy_export = {**strategy, "vertical": vertical, "generated_at": datetime.now().isoformat()}
        with strategy_json_path.open("w", encoding="utf-8") as f:
            json.dump(strategy_export, f, indent=2, ensure_ascii=False)

        with keywords_json_path.open("w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in keyword_data.items()}, f, indent=2, ensure_ascii=False)

    gap_note = f" + {len(gap_keywords)} gap keywords" if gap_keywords else ""
    console.print(f"[green]✓[/green] Wrote [bold]{rows_written} rows[/bold]{gap_note} to [cyan]{output}[/cyan]")
    console.print(f"[green]✓[/green] Saved [cyan]{strategy_json_path.name}[/cyan] and [cyan]{keywords_json_path.name}[/cyan]")
    console.print()

    # Summary table
    table = Table(title="Strategy Summary", show_header=True, header_style="bold cyan", box=None)
    table.add_column("#", style="dim", width=3)
    table.add_column("Pillar Title", width=45)
    table.add_column("Intent", width=15)
    table.add_column("Keywords", justify="right", width=10)
    if competitor_list:
        table.add_column("w/ Competitor Overlap", justify="right", width=22)

    for pillar in strategy["pillars"]:
        pillar_kws = keyword_data.get(pillar["number"], [])
        row = [
            str(pillar["number"]),
            pillar["title"][:43],
            pillar["search_intent"],
            str(len(pillar_kws)),
        ]
        if competitor_list:
            overlap_count = sum(
                1 for kw in pillar_kws
                if overlap_map.get(kw["keyword"].lower())
            )
            row.append(str(overlap_count))
        table.add_row(*row)

    console.print(table)
    console.print()
    console.print(
        f"\n[bold green]Done![/bold green]  "
        f"Review [cyan]{output}[/cyan], then run:\n"
        f"  [bold]python briefs.py {strategy_json_path.name} -k {keywords_json_path.name}[/bold]\n"
    )


if __name__ == "__main__":
    main()
