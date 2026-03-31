import os
import sys
from pathlib import Path
from datetime import datetime

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

import llm
from brief_generator import generate_pillar_briefs
from brief_writer import write_briefs_csv, write_briefs_json, load_strategy, load_keywords

load_dotenv(Path(__file__).parent / ".env")
console = Console()


@click.command()
@click.argument("strategy_file", type=click.Path(exists=True))
@click.option(
    "--keywords-file", "-k",
    default=None,
    type=click.Path(exists=True),
    help="Keywords JSON saved by main.py. Auto-detected if in same directory.",
)
@click.option(
    "--articles", "-n",
    default=20,
    type=int,
    show_default=True,
    help="Number of content briefs to generate per pillar.",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    help="Directory to write JSON briefs and overview CSV. Defaults to ./briefs_<timestamp>/",
)
@click.option(
    "--pillars",
    default=None,
    help="Comma-separated pillar numbers to generate (e.g. 1,3,5). Defaults to all.",
)
@click.option("--provider", default=None, help="LLM provider: anthropic (default) or ollama.")
@click.option("--model", default=None, help="Model override (e.g. llama3.2, mistral).")
def main(strategy_file: str, keywords_file: str, articles: int, output_dir: str, pillars: str, provider: str, model: str):
    """
    Generate content briefs from a saved strategy JSON file.

    Produces an overview CSV (for human review) and individual JSON files
    per article (for a writing agent to consume).

    \b
    Run main.py first, then:
      python briefs.py strategy_b2b_hr_software_20240101_120000.json
      python briefs.py strategy.json --articles 20 --output-dir ./briefs
      python briefs.py strategy.json --pillars 1,2  # only specific pillars
    """
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    # Load strategy
    strategy = load_strategy(strategy_file)

    # Auto-detect keywords file if not provided
    if keywords_file is None:
        strategy_path = Path(strategy_file)
        candidate = strategy_path.parent / strategy_path.name.replace("strategy_", "keywords_")
        if candidate.exists():
            keywords_file = str(candidate)
            console.print(f"[dim]Auto-detected keywords file: {candidate.name}[/dim]")
        else:
            console.print(
                "[yellow]Warning:[/yellow] No keywords file found. "
                "Briefs will use pillar seed keywords only.\n"
                "Pass --keywords-file to include DataForSEO keyword data."
            )

    keyword_data = load_keywords(keywords_file) if keywords_file else {}

    # Filter pillars if requested
    all_pillars = strategy["pillars"]
    if pillars:
        selected = {int(p.strip()) for p in pillars.split(",")}
        all_pillars = [p for p in all_pillars if p["number"] in selected]
        if not all_pillars:
            console.print(f"[red]Error:[/red] No matching pillars for --pillars={pillars}")
            sys.exit(1)

    # Output directory
    if output_dir is None:
        slug = strategy.get("vertical_summary", "strategy")[:30].lower().replace(" ", "_").strip("_")
        output_dir = f"briefs_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / "briefs_overview.csv"

    total_articles = len(all_pillars) * articles

    console.print()
    console.rule("[bold cyan]Content Brief Generator[/bold cyan]")
    console.print(f"  Strategy   : [bold]{strategy.get('vertical_summary', strategy_file)}[/bold]")
    console.print(f"  LLM        : {llm.provider_label()}")
    console.print(f"  Pillars    : {len(all_pillars)}")
    console.print(f"  Articles   : {articles} per pillar = [bold]{total_articles} total[/bold]")
    console.print(f"  Output dir : {output_dir}")
    console.print()

    all_briefs = []

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating briefs...", total=len(all_pillars))

        for pillar in all_pillars:
            progress.update(
                task,
                description=f"[bold green]Pillar {pillar['number']}/{len(all_pillars)}[/bold green] — {pillar['title'][:50]}",
            )

            pillar_keywords = keyword_data.get(pillar["number"], [])

            # Fall back to seed keywords if no DataForSEO data available
            if not pillar_keywords:
                pillar_keywords = [
                    {"keyword": kw, "monthly_volume": 0, "keyword_type": "seed"}
                    for kw in pillar.get("seed_keywords", [])
                ]

            briefs = generate_pillar_briefs(pillar, pillar_keywords, num_articles=articles)
            all_briefs.extend(briefs)
            progress.advance(task)

    # Write outputs
    with console.status("Writing CSV overview...", spinner="dots"):
        rows = write_briefs_csv(all_briefs, str(csv_path))

    with console.status("Writing JSON brief files...", spinner="dots"):
        files = write_briefs_json(all_briefs, str(output_path))

    console.print(f"[green]✓[/green] Wrote [bold]{rows}[/bold] rows to [cyan]{csv_path}[/cyan]")
    console.print(f"[green]✓[/green] Wrote [bold]{files}[/bold] JSON brief files to [cyan]{output_dir}/[/cyan]")
    console.print()

    # Summary table
    table = Table(title="Brief Summary", show_header=True, header_style="bold cyan", box=None)
    table.add_column("#", style="dim", width=3)
    table.add_column("Pillar", width=40)
    table.add_column("Articles", justify="right", width=10)
    table.add_column("Avg Word Count", justify="right", width=15)

    for pillar in all_pillars:
        pillar_briefs = [b for b in all_briefs if b["pillar_number"] == pillar["number"]]
        if pillar_briefs:
            avg_wc = sum(b["word_count_target"] for b in pillar_briefs) // len(pillar_briefs)
        else:
            avg_wc = 0
        table.add_row(
            str(pillar["number"]),
            pillar["title"][:38],
            str(len(pillar_briefs)),
            f"{avg_wc:,}",
        )

    console.print(table)
    console.print()
    console.print(
        f"[bold green]Done![/bold green]  "
        f"Review [cyan]{csv_path.name}[/cyan], edit any titles/keywords, "
        f"then point your writing agent at [cyan]{output_dir}/pillar_*/article_*.json[/cyan]\n"
    )


if __name__ == "__main__":
    main()
