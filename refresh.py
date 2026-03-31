import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

import llm
from gsc import SearchConsoleClient
from refresh_agent import refresh_article

load_dotenv(Path(__file__).parent / ".env")
console = Console()

STATE_VERSION = 1


def load_refresh_state(state_path: str) -> dict:
    if Path(state_path).exists():
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    return {"version": STATE_VERSION, "articles": {}}


def save_refresh_state(state: dict, state_path: str) -> None:
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def match_article_file(slug: str, articles_dir: str) -> str | None:
    """Find a local article file whose slug matches the GSC page slug."""
    articles_path = Path(articles_dir)
    for md_file in articles_path.rglob("article_*.md"):
        content = md_file.read_text(encoding="utf-8")
        if f'slug: "{slug}"' in content or f"slug: {slug}" in content:
            return str(md_file)
    return None


async def run_refresh(
    targets: list,
    articles_dir: str,
    state: dict,
    state_path: str,
    gsc_client: SearchConsoleClient,
    concurrency: int,
    dry_run: bool,
) -> list:
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    state_lock = asyncio.Lock()

    async def process_one(target: dict) -> None:
        slug = target["slug"]
        url = target["url"]

        async with semaphore:
            article_file = match_article_file(slug, articles_dir)
            if not article_file:
                results.append({**target, "status": "skipped", "reason": "no matching local file"})
                return

            # Fetch keywords this page ranks for
            gsc_keywords = gsc_client.get_keyword_performance(url)
            # Use top competitor URLs from GSC data (pages outranking this one)
            competitor_urls = []  # populated below if DataForSEO available

            if dry_run:
                results.append({
                    **target,
                    "status": "dry_run",
                    "file": article_file,
                    "top_keywords": [k["keyword"] for k in gsc_keywords[:5]],
                })
                async with state_lock:
                    progress.advance(overall_task)
                return

            try:
                summary = await refresh_article(article_file, gsc_keywords, competitor_urls)
                async with state_lock:
                    state["articles"][slug] = {
                        "status": "refreshed",
                        "file": article_file,
                        "position_before": target["position"],
                        "wc_before": summary["wc_before"],
                        "wc_after": summary["wc_after"],
                        "refreshed_at": datetime.now().isoformat(),
                    }
                    save_refresh_state(state, state_path)
                results.append({**target, "status": "refreshed", **summary})
            except Exception as exc:
                async with state_lock:
                    state["articles"][slug] = {
                        "status": "failed",
                        "error": str(exc),
                        "failed_at": datetime.now().isoformat(),
                    }
                    save_refresh_state(state, state_path)
                results.append({**target, "status": "failed", "error": str(exc)})
            finally:
                async with state_lock:
                    progress.advance(overall_task)

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
        console=console, expand=True,
    ) as prog:
        global progress, overall_task
        progress = prog
        overall_task = prog.add_task("[bold green]Refreshing articles[/bold green]", total=len(targets))
        await asyncio.gather(*[process_one(t) for t in targets])

    return results


@click.command()
@click.option("--articles-dir", "-a", required=True, type=click.Path(exists=True),
              help="Directory containing written articles.")
@click.option("--min-position", default=11.0, show_default=True,
              help="Only refresh pages ranked below this position.")
@click.option("--max-position", default=20.0, show_default=True,
              help="Only refresh pages ranked above this position.")
@click.option("--days", default=90, show_default=True,
              help="GSC data lookback window in days.")
@click.option("--min-impressions", default=50, show_default=True,
              help="Minimum impressions to consider a page for refresh.")
@click.option("--concurrency", "-n", default=2, show_default=True,
              help="Parallel refresh agents (keep low — these are heavy).")
@click.option("--state-file", default=None,
              help="Refresh state JSON path. Default: refresh_state.json in articles dir.")
@click.option("--retry-failed", is_flag=True, default=False,
              help="Retry previously failed refreshes.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show which articles would be refreshed without modifying them.")
@click.option("--provider", default=None, help="LLM provider: anthropic or ollama.")
@click.option("--model", default=None, help="Model override.")
def main(articles_dir, min_position, max_position, days, min_impressions,
         concurrency, state_file, retry_failed, dry_run, provider, model):
    """
    Identify underperforming pages via Google Search Console and refresh them with Claude.

    Targets pages ranking in positions 11–20 (page 2) — highest ROI for refresh.
    Automatically resumes — already-refreshed articles are skipped.

    \b
    Examples:
      python refresh.py --articles-dir articles/
      python refresh.py --articles-dir articles/ --min-position 8 --max-position 25
      python refresh.py --articles-dir articles/ --dry-run
    """
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    missing = []
    if llm.get_provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("GSC_SERVICE_ACCOUNT_FILE"):
        missing.append("GSC_SERVICE_ACCOUNT_FILE")
    if not os.getenv("GSC_SITE_URL"):
        missing.append("GSC_SITE_URL")
    if missing:
        console.print(f"[red]Error:[/red] Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    if state_file is None:
        state_file = str(Path(articles_dir) / "refresh_state.json")

    state = load_refresh_state(state_file)

    console.print()
    console.rule("[bold cyan]Content Refresh Workflow[/bold cyan]")
    console.print(f"  Articles dir : {articles_dir}")
    console.print(f"  LLM          : {llm.provider_label()}")
    console.print(f"  Target range : positions {min_position}–{max_position}")
    console.print(f"  GSC lookback : {days} days")
    if dry_run:
        console.print("  [yellow]DRY RUN — no files will be modified[/yellow]")
    console.print()

    # Fetch underperforming pages from GSC
    with console.status("Fetching page performance from Google Search Console...", spinner="dots"):
        gsc = SearchConsoleClient()
        targets = gsc.get_underperforming_pages(
            min_position=min_position,
            max_position=max_position,
            min_impressions=min_impressions,
            days=days,
        )

    console.print(f"[green]✓[/green] Found [bold]{len(targets)}[/bold] pages in positions {min_position}–{max_position}")

    # Filter already-refreshed (unless retry-failed)
    to_refresh = []
    skipped = 0
    for t in targets:
        prev = state["articles"].get(t["slug"], {})
        status = prev.get("status")
        if status == "refreshed":
            skipped += 1
        elif status == "failed" and not retry_failed:
            skipped += 1
        else:
            to_refresh.append(t)

    if not to_refresh:
        console.print("[green]All eligible pages have already been refreshed.[/green]")
        return

    console.print(f"  Skipping {skipped} already refreshed  |  [bold]{len(to_refresh)} to refresh[/bold]")
    console.print()

    results = asyncio.run(run_refresh(to_refresh, articles_dir, state, state_file, gsc, concurrency, dry_run))

    # Summary table
    refreshed = [r for r in results if r.get("status") == "refreshed"]
    failed = [r for r in results if r.get("status") == "failed"]
    skipped_local = [r for r in results if r.get("status") == "skipped"]

    console.print()
    if refreshed:
        table = Table(header_style="bold cyan", box=None)
        table.add_column("Article", width=42)
        table.add_column("Position", justify="right", width=10)
        table.add_column("Words Before", justify="right", width=13)
        table.add_column("Words After", justify="right", width=12)
        table.add_column("Change", justify="right", width=8)

        for r in refreshed:
            delta = r.get("wc_delta", 0)
            delta_str = f"[green]+{delta}[/green]" if delta > 0 else str(delta)
            table.add_row(
                r.get("title", r["slug"])[:40],
                str(r["position"]),
                str(r.get("wc_before", "?")),
                str(r.get("wc_after", "?")),
                delta_str,
            )
        console.print(table)
        console.print()

    console.print(
        f"[bold green]Done![/bold green]  "
        f"Refreshed: [green]{len(refreshed)}[/green]  "
        f"Failed: [red]{len(failed)}[/red]  "
        f"No local file: [dim]{len(skipped_local)}[/dim]"
    )

    if failed:
        console.print("Re-run with [bold]--retry-failed[/bold] to retry failures.")
    console.print(f"State saved to: [cyan]{state_file}[/cyan]\n")


if __name__ == "__main__":
    main()
