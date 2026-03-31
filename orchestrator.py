import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

import llm
from article_writer import write_article
from auditor import audit_article

load_dotenv(Path(__file__).parent / ".env")
console = Console()


# ── CSV loading ────────────────────────────────────────────────────────────────

def load_csv_jobs(csv_path: str) -> list:
    """
    Read the briefs_overview.csv and return a list of job dicts.
    Skips the gap-keywords section (rows without valid Pillar # / Article #).
    """
    jobs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pillar_num = str(int(row.get("Pillar #", "").strip()))
                article_num = str(int(row.get("Article #", "").strip())).zfill(2)
            except (ValueError, AttributeError):
                continue  # gap-keyword rows or blank rows

            job_id = f"p{pillar_num}_a{article_num}"
            jobs.append({
                "id": job_id,
                "pillar_number": pillar_num,
                "article_number": article_num,
                "pillar_title": row.get("Pillar Title", "").strip(),
                "title": row.get("Title", "").strip(),
                "slug": row.get("Slug", "").strip(),
                "primary_keyword": row.get("Primary Keyword", "").strip(),
                "secondary_keywords": [
                    k.strip()
                    for k in row.get("Secondary Keywords", "").split("|")
                    if k.strip()
                ],
                "search_intent": row.get("Search Intent", "").strip(),
                "word_count_target": int(row.get("Word Count Target") or 1500),
                "meta_description": row.get("Meta Description", "").strip(),
                "cta": row.get("CTA", "").strip(),
                "table_of_contents": row.get("Table of Contents", "").strip(),
            })
    return jobs


# ── State management ──────────────────────────────────────────────────────────

def load_state(state_path: str) -> dict:
    if Path(state_path).exists():
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    return {"jobs": {}}


async def save_state(state: dict, state_path: str, lock: asyncio.Lock) -> None:
    async with lock:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


# ── Per-article worker ────────────────────────────────────────────────────────

async def process_job(
    job: dict,
    state: dict,
    state_path: str,
    output_dir: str,
    semaphore: asyncio.Semaphore,
    state_lock: asyncio.Lock,
    progress: Progress,
    overall_task,
    dry_run: bool,
    run_audit: bool = False,
    min_score: int = 70,
) -> None:
    async with semaphore:
        job_id = job["id"]
        label = f"{job['title'][:55]}"
        task_id = progress.add_task(f"[cyan]Writing:[/cyan] {label}", total=None)

        try:
            # Mark as in_progress
            async with state_lock:
                state["jobs"][job_id] = {
                    "status": "writing",
                    "title": job["title"],
                    "pillar": job["pillar_number"],
                    "started_at": datetime.now().isoformat(),
                    "output_file": None,
                    "error": None,
                }
            await save_state(state, state_path, state_lock)

            # Write the article
            if dry_run:
                await asyncio.sleep(0.3)
                content = f"# {job['title']}\n\n_[DRY RUN — no content generated]_\n"
            else:
                content = await write_article(job)

            # Save to file with YAML front matter
            article_dir = Path(output_dir) / f"pillar_{job['pillar_number']}"
            article_dir.mkdir(parents=True, exist_ok=True)
            output_file = article_dir / f"article_{job['article_number']}.md"

            front_matter = "\n".join([
                "---",
                f'title: "{job["title"]}"',
                f'slug: "{job["slug"]}"',
                f'pillar: {job["pillar_number"]}',
                f'article: {job["article_number"]}',
                f'primary_keyword: "{job["primary_keyword"]}"',
                f'word_count_target: {job["word_count_target"]}',
                f'meta_description: "{job["meta_description"]}"',
                f'status: draft',
                f'generated_at: "{datetime.now().isoformat()}"',
                "---\n\n",
            ])
            output_file.write_text(front_matter + content, encoding="utf-8")

            # Optional audit gate
            audit_score = None
            audit_passed = None
            if run_audit and not dry_run:
                audit_result = audit_article(str(output_file))
                audit_score = audit_result["score"]
                audit_passed = audit_score >= min_score
                suffix = f"  [dim]audit: {audit_score}/100[/dim]"
                if not audit_passed:
                    progress.update(
                        task_id,
                        description=f"[yellow]⚠ needs review:[/yellow] {label}{suffix}",
                        completed=1, total=1,
                    )
                    progress.advance(overall_task)
                    async with state_lock:
                        state["jobs"][job_id].update({
                            "status": "needs_review",
                            "output_file": str(output_file),
                            "completed_at": datetime.now().isoformat(),
                            "audit_score": audit_score,
                            "audit_passed": False,
                        })
                    await save_state(state, state_path, state_lock)
                    return

            # Mark completed
            async with state_lock:
                state["jobs"][job_id].update({
                    "status": "completed",
                    "output_file": str(output_file),
                    "completed_at": datetime.now().isoformat(),
                    **({"audit_score": audit_score, "audit_passed": audit_passed} if run_audit else {}),
                })
            await save_state(state, state_path, state_lock)

            audit_suffix = f"  [dim]audit: {audit_score}/100[/dim]" if audit_score is not None else ""
            progress.update(
                task_id,
                description=f"[green]✓[/green] {label}{audit_suffix}",
                completed=1,
                total=1,
            )

        except Exception as exc:
            async with state_lock:
                state["jobs"][job_id].update({
                    "status": "failed",
                    "error": str(exc),
                    "failed_at": datetime.now().isoformat(),
                })
            await save_state(state, state_path, state_lock)

            progress.update(
                task_id,
                description=f"[red]✗ FAILED:[/red] {label}",
                completed=1,
                total=1,
            )

        finally:
            progress.advance(overall_task)


# ── Orchestrator core ─────────────────────────────────────────────────────────

async def run_orchestrator(
    jobs: list,
    state: dict,
    state_path: str,
    output_dir: str,
    concurrency: int,
    retry_failed: bool,
    dry_run: bool,
    run_audit: bool = False,
    min_score: int = 70,
) -> tuple:
    semaphore = asyncio.Semaphore(concurrency)
    state_lock = asyncio.Lock()

    # Decide which jobs to run
    to_run = []
    skipped = 0

    for job in jobs:
        prev = state["jobs"].get(job["id"], {})
        status = prev.get("status")

        if status == "completed":
            skipped += 1
            continue
        if status == "failed" and not retry_failed:
            skipped += 1
            continue
        # Reset interrupted jobs so they re-run cleanly
        if status == "writing":
            async with state_lock:
                state["jobs"][job["id"]]["status"] = "pending"

        to_run.append(job)

    if not to_run:
        return skipped, 0, 0

    console.print(
        f"  [dim]Skipping {skipped} already completed[/dim]  |  "
        f"[bold]{len(to_run)} articles to write[/bold]  |  "
        f"[bold]{concurrency} parallel agents[/bold]"
    )
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        overall_task = progress.add_task(
            "[bold green]Overall[/bold green]",
            total=len(to_run),
        )

        await asyncio.gather(*[
            process_job(
                job, state, state_path, output_dir,
                semaphore, state_lock, progress, overall_task, dry_run,
                run_audit=run_audit, min_score=min_score,
            )
            for job in to_run
        ])

    all_jobs = list(state["jobs"].values())
    completed = sum(1 for j in all_jobs if j.get("status") == "completed")
    failed = sum(1 for j in all_jobs if j.get("status") == "failed")
    needs_review = sum(1 for j in all_jobs if j.get("status") == "needs_review")
    return skipped, completed, failed, needs_review


# ── Status display ────────────────────────────────────────────────────────────

def print_status(jobs: list, state: dict) -> None:
    counts = {"completed": 0, "failed": 0, "writing": 0, "pending": 0}

    table = Table(title="Writing State", header_style="bold cyan", box=None, show_lines=False)
    table.add_column("ID", style="dim", width=12)
    table.add_column("Pillar", width=8, justify="center")
    table.add_column("Title", width=48)
    table.add_column("Status", width=14)
    table.add_column("File", width=30, style="dim")

    for job in jobs:
        js = state["jobs"].get(job["id"], {})
        status = js.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1

        status_cell = {
            "completed": "[green]✓ done[/green]",
            "writing":   "[yellow]⟳ writing[/yellow]",
            "failed":    "[red]✗ failed[/red]",
            "pending":   "[dim]○ pending[/dim]",
        }.get(status, status)

        out = Path(js["output_file"]).name if js.get("output_file") else ""
        table.add_row(job["id"], job["pillar_number"], job["title"][:46], status_cell, out)

    console.print(table)
    console.print()
    console.print(
        f"  [green]completed: {counts['completed']}[/green]  "
        f"[yellow]writing: {counts['writing']}[/yellow]  "
        f"[red]failed: {counts['failed']}[/red]  "
        f"[dim]pending: {counts['pending']}[/dim]"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option(
    "--concurrency", "-n",
    default=3, show_default=True,
    help="Number of articles to write in parallel.",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    help="Directory to save articles. Default: articles/ next to the CSV.",
)
@click.option(
    "--state-file",
    default=None,
    help="State JSON file. Default: writing_state.json next to the CSV.",
)
@click.option(
    "--retry-failed",
    is_flag=True, default=False,
    help="Retry articles that previously failed.",
)
@click.option(
    "--dry-run",
    is_flag=True, default=False,
    help="Simulate the run without calling the Claude API.",
)
@click.option(
    "--status",
    "show_status",
    is_flag=True, default=False,
    help="Print the current state of all articles and exit.",
)
@click.option("--provider", default=None, help="LLM provider: anthropic (default) or ollama.")
@click.option("--model", default=None, help="Model override (e.g. llama3.2, mistral).")
@click.option("--audit", "run_audit", is_flag=True, default=False, help="Run SEO audit after each article is written.")
@click.option("--min-score", default=70, show_default=True, help="Minimum audit score to mark as completed (used with --audit).")
def main(csv_file, concurrency, output_dir, state_file, retry_failed, dry_run, show_status, provider, model, run_audit, min_score):
    """
    Read content briefs from CSV_FILE and spawn parallel agents to write articles.

    Automatically resumes — completed articles are always skipped.
    Run again at any time to pick up where you left off.

    \b
    Examples:
      python orchestrator.py briefs_overview.csv
      python orchestrator.py briefs_overview.csv --concurrency 5
      python orchestrator.py briefs_overview.csv --retry-failed
      python orchestrator.py briefs_overview.csv --status
      python orchestrator.py briefs_overview.csv --dry-run
    """
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    if llm.get_provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    csv_path = Path(csv_file)
    if state_file is None:
        state_file = str(csv_path.parent / "writing_state.json")
    if output_dir is None:
        output_dir = str(csv_path.parent / "articles")

    jobs = load_csv_jobs(csv_file)
    if not jobs:
        console.print("[red]Error:[/red] No valid article rows found in CSV.")
        sys.exit(1)

    state = load_state(state_file)

    # ── --status mode ────────────────────────────────────────────
    if show_status:
        print_status(jobs, state)
        return

    # ── Run ──────────────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Writing Agent Orchestrator[/bold cyan]")
    console.print(f"  CSV        : {csv_file}")
    console.print(f"  LLM        : {llm.provider_label()}")
    console.print(f"  Articles   : [bold]{len(jobs)}[/bold]")
    console.print(f"  State file : {state_file}")
    console.print(f"  Output dir : {output_dir}")
    if run_audit:
        console.print(f"  Audit      : enabled  (min score: {min_score})")
    if dry_run:
        console.print("  [yellow]DRY RUN — Claude will not be called[/yellow]")
    console.print()

    skipped, completed, failed, needs_review = asyncio.run(
        run_orchestrator(
            jobs, state, state_file, output_dir,
            concurrency, retry_failed, dry_run,
            run_audit=run_audit, min_score=min_score,
        )
    )

    console.print()
    review_note = f"  Needs review: [yellow]{needs_review}[/yellow]" if needs_review else ""
    console.print(
        f"[bold green]Done![/bold green]  "
        f"Completed: [green]{completed}[/green]  "
        f"Failed: [red]{failed}[/red]  "
        f"Skipped: [dim]{skipped}[/dim]{review_note}"
    )
    if failed:
        console.print("Re-run with [bold]--retry-failed[/bold] to retry failed articles.")
    if needs_review:
        console.print(f"[yellow]{needs_review} article(s) need review[/yellow] — run [bold]python audit.py {output_dir} --fix[/bold]")
    console.print(f"Articles saved to: [cyan]{output_dir}/[/cyan]\n")


if __name__ == "__main__":
    main()
