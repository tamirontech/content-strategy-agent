import asyncio
import csv
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

import llm
from content_map import build_content_map, load_content_map, mark_links_added, save_content_map
from link_finder import find_link_opportunities
from link_injector import inject_links

load_dotenv(Path(__file__).parent / ".env")
console = Console()


async def _process_article(
    article: dict,
    content_map: list,
    min_relevance: float,
    dry_run: bool,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        opportunities = await find_link_opportunities(article, content_map, min_relevance)

        if not opportunities:
            return {"file": article["file"], "title": article["title"], "injected": [], "skipped": []}

        if dry_run:
            return {
                "file": article["file"],
                "title": article["title"],
                "injected": opportunities,
                "skipped": [],
                "dry_run": True,
            }

        result = inject_links(article["file"], opportunities)
        if result["injected"]:
            mark_links_added(
                str(Path(article["file"]).parent.parent),
                article["file"],
                [l["url"] for l in result["injected"]],
            )

        return {"file": article["file"], "title": article["title"], **result}


def _write_report(results: list, output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["File", "Title", "Links Injected", "Links Skipped", "Details"])
        writer.writeheader()
        for r in results:
            injected_str = " | ".join(f"{l['anchor']} → {l['url']}" for l in r.get("injected", []))
            skipped_str = " | ".join(f"{l['anchor']} ({l.get('reason','')})" for l in r.get("skipped", []))
            writer.writerow({
                "File": Path(r["file"]).name,
                "Title": r["title"],
                "Links Injected": len(r.get("injected", [])),
                "Links Skipped": len(r.get("skipped", [])),
                "Details": injected_str,
            })


@click.command()
@click.argument("articles_dir", type=click.Path(exists=True))
@click.option("--base-url", "-u", required=True, help="Site base URL (e.g. https://yoursite.com).")
@click.option("--min-relevance", default=0.6, show_default=True, help="Minimum relevance score to insert a link (0.0–1.0).")
@click.option("--concurrency", "-n", default=5, show_default=True, help="Parallel articles to process.")
@click.option("--dry-run", is_flag=True, default=False, help="Show proposed links without modifying files.")
@click.option("--rebuild-map", is_flag=True, default=False, help="Force rebuild of content_map.json.")
@click.option("--provider", default=None, help="LLM provider: anthropic or ollama.")
@click.option("--model", default=None, help="Model override.")
def main(articles_dir, base_url, min_relevance, concurrency, dry_run, rebuild_map, provider, model):
    """
    Scan articles and inject internal links using Claude to find opportunities.

    Reads from and updates content_map.json in ARTICLES_DIR.

    \b
    Examples:
      python linker.py articles/ --base-url https://yoursite.com
      python linker.py articles/ --base-url https://yoursite.com --dry-run
      python linker.py articles/ --base-url https://yoursite.com --min-relevance 0.75
    """
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    if llm.get_provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    # Build or load content map
    map_path = Path(articles_dir) / "content_map.json"
    if rebuild_map or not map_path.exists():
        with console.status("Building content map...", spinner="dots"):
            content_map = build_content_map(articles_dir, base_url)
            save_content_map(content_map, articles_dir)
        console.print(f"[green]✓[/green] Content map built: {len(content_map)} articles")
    else:
        content_map = load_content_map(articles_dir)
        console.print(f"[dim]Loaded content map: {len(content_map)} articles[/dim]")

    if not content_map:
        console.print("[red]Error:[/red] No articles found.")
        sys.exit(1)

    report_path = str(Path(articles_dir) / "linking_report.csv")

    console.print()
    console.rule("[bold cyan]Internal Linking Agent[/bold cyan]")
    console.print(f"  Articles    : [bold]{len(content_map)}[/bold]")
    console.print(f"  Base URL    : {base_url}")
    console.print(f"  Min relevance: {min_relevance}")
    console.print(f"  LLM         : {llm.provider_label()}")
    if dry_run:
        console.print("  [yellow]DRY RUN — no files will be modified[/yellow]")
    console.print()

    semaphore = asyncio.Semaphore(concurrency)

    async def run_all():
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
            console=console, expand=True,
        ) as progress:
            task = progress.add_task("[bold green]Finding links[/bold green]", total=len(content_map))

            async def process_and_advance(article):
                result = await _process_article(article, content_map, min_relevance, dry_run, semaphore)
                progress.advance(task)
                return result

            return await asyncio.gather(*[process_and_advance(a) for a in content_map])

    results = asyncio.run(run_all())

    # Summary
    total_injected = sum(len(r.get("injected", [])) for r in results)
    articles_with_links = sum(1 for r in results if r.get("injected"))

    _write_report(results, report_path)

    console.print()

    table = Table(header_style="bold cyan", box=None)
    table.add_column("Article", width=50)
    table.add_column("Links Added", justify="right", width=12)
    table.add_column("Sample Links", width=45)

    for r in sorted(results, key=lambda x: len(x.get("injected", [])), reverse=True):
        if not r.get("injected"):
            continue
        sample = ", ".join(f"[dim]{l['anchor'][:20]}[/dim]" for l in r["injected"][:2])
        table.add_row(Path(r["file"]).name, str(len(r["injected"])), sample)

    if articles_with_links:
        console.print(table)

    console.print()
    action = "Would inject" if dry_run else "Injected"
    console.print(
        f"[bold green]{action} {total_injected} links[/bold green] "
        f"across {articles_with_links}/{len(content_map)} articles"
    )
    console.print(f"[green]✓[/green] Report saved to [cyan]{report_path}[/cyan]\n")


if __name__ == "__main__":
    main()
