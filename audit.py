import asyncio
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

import llm
from audit_report import print_summary, write_csv, write_json
from auditor import audit_article
from quality_check import run_quality_check_file

load_dotenv(Path(__file__).parent / ".env")
console = Console()


def discover_articles(path: str) -> list:
    p = Path(path)
    if p.is_file():
        return [str(p)]
    return sorted(str(f) for f in p.rglob("article_*.md"))


@click.command()
@click.argument("path", metavar="PATH")
@click.option("--min-score", default=70, show_default=True, help="Minimum passing score (0–100).")
@click.option("--fix", "auto_fix", is_flag=True, default=False, help="Auto-fix failing articles with Claude.")
@click.option("--grammar", is_flag=True, default=False, help="Run LanguageTool grammar check (requires internet).")
@click.option("--readability", is_flag=True, default=False, help="Run Hemingway-style readability analysis.")
@click.option("--grammarly", "use_grammarly", is_flag=True, default=False,
              help="Run Grammarly Writing Score API (requires GRAMMARLY_CLIENT_ID/SECRET).")
@click.option("--review-files", is_flag=True, default=False,
              help="Write .review.md annotation files next to each article.")
@click.option("--output", "-o", default=None, help="CSV report path. Default: audit_report.csv next to PATH.")
@click.option("--provider", default=None, help="LLM provider: anthropic or ollama (used with --fix).")
@click.option("--model", default=None, help="Model override (used with --fix).")
def main(path, min_score, auto_fix, grammar, readability, use_grammarly, review_files, output, provider, model):
    """
    Audit SEO quality of written articles.

    PATH can be a single article .md file or a directory of articles.

    \b
    Examples:
      python audit.py articles/
      python audit.py articles/pillar_1/article_03.md
      python audit.py articles/ --min-score 80 --readability
      python audit.py articles/ --grammar --review-files
      python audit.py articles/ --grammarly --review-files
      python audit.py articles/ --fix --provider anthropic
    """
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model

    if auto_fix and llm.get_provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set (required for --fix).")
        sys.exit(1)

    if use_grammarly and (not os.getenv("GRAMMARLY_CLIENT_ID") or not os.getenv("GRAMMARLY_CLIENT_SECRET")):
        console.print("[red]Error:[/red] GRAMMARLY_CLIENT_ID and GRAMMARLY_CLIENT_SECRET required for --grammarly.")
        console.print("  Sign up at [cyan]https://developer.grammarly.com/[/cyan] for enterprise API access.")
        sys.exit(1)

    files = discover_articles(path)
    if not files:
        console.print(f"[red]Error:[/red] No article_*.md files found at: {path}")
        sys.exit(1)

    base_dir = Path(path) if Path(path).is_dir() else Path(path).parent
    if output is None:
        output = str(base_dir / "audit_report.csv")
    json_output = output.replace(".csv", ".json")

    # Build quality check backend list
    quality_backends = []
    if readability or grammar or use_grammarly:
        quality_backends.append("hemingway")  # always include when quality checks requested
    if grammar:
        quality_backends.append("languagetool")
    if use_grammarly:
        quality_backends.append("grammarly")

    console.print()
    console.rule("[bold cyan]SEO Audit[/bold cyan]")
    console.print(f"  Articles   : [bold]{len(files)}[/bold]")
    console.print(f"  Threshold  : {min_score}/100")
    if auto_fix:
        console.print(f"  Auto-fix   : enabled  ({llm.provider_label()})")
    if quality_backends:
        console.print(f"  Quality    : {', '.join(quality_backends)}")
    if review_files:
        console.print(f"  Reviews    : .review.md files will be written")
    console.print()

    # ── Run SEO audits ────────────────────────────────────────────
    results = []
    with console.status("Auditing articles...", spinner="dots"):
        for f in files:
            results.append(audit_article(f))

    # ── Run quality checks ────────────────────────────────────────
    if quality_backends:
        console.print(f"Running quality checks ({', '.join(quality_backends)})...")
        quality_errors = _run_quality_checks(files, results, quality_backends, review_files)
        if quality_errors:
            console.print(f"  [yellow]Warning:[/yellow] {quality_errors} article(s) had quality check errors (check logs)")

    # ── Apply min_score to passed field ───────────────────────────
    for r in results:
        r["passed"] = r["score"] >= min_score

    failing = [r for r in results if not r["passed"]]

    # ── Auto-fix ──────────────────────────────────────────────────
    if auto_fix and failing:
        console.print(f"[yellow]Auto-fixing {len(failing)} failing articles...[/yellow]\n")
        asyncio.run(_fix_articles(failing, min_score))

        # Re-audit fixed articles
        fixed_files = {r["file"] for r in failing}
        for i, r in enumerate(results):
            if r["file"] in fixed_files:
                fresh = audit_article(r["file"])
                fresh["passed"] = fresh["score"] >= min_score
                results[i] = fresh

    # ── Report ────────────────────────────────────────────────────
    print_summary(results, console, min_score)

    write_csv(results, output)
    write_json(results, json_output)

    console.print()
    console.print(f"[green]✓[/green] Report saved to [cyan]{output}[/cyan]")
    if review_files and quality_backends:
        console.print(f"[green]✓[/green] Review files written next to each article (.review.md)")

    still_failing = sum(1 for r in results if not r["passed"])
    if still_failing:
        console.print(
            f"\n[red]{still_failing} article(s) still below threshold.[/red] "
            "Review the report or re-run with [bold]--fix[/bold]."
        )
        sys.exit(1)
    else:
        console.print("\n[bold green]All articles passed.[/bold green]")


def _run_quality_checks(
    files: list,
    results: list,
    backends: list,
    write_review: bool,
) -> int:
    """
    Run quality checks for each article and merge results into the audit dicts.
    Returns count of articles that encountered errors during quality checking.
    """
    error_count = 0
    for file_path, audit_result in zip(files, results):
        try:
            qr = run_quality_check_file(
                article_path=file_path,
                backends=backends,
                write_review=write_review,
            )
            # Merge quality metrics into audit result
            audit_result["grammar_errors"] = qr.grammar_error_count
            audit_result["spelling_errors"] = qr.spelling_error_count
            audit_result["readability_grade"] = qr.hemingway_grade
            audit_result["flesch_reading_ease"] = qr.flesch_reading_ease
            audit_result["passive_voice"] = qr.passive_voice_count
            audit_result["adverbs"] = qr.adverb_count
            audit_result["hard_sentences"] = qr.hard_sentence_count
            audit_result["very_hard_sentences"] = qr.very_hard_sentence_count

            if qr.grammarly_score is not None:
                audit_result["grammarly_score"] = qr.grammarly_score

            # Append quality issues to the audit issues list
            audit_result["issues"] = audit_result.get("issues", []) + qr.issues

            # Penalise score: deduct up to 10pts for grammar + 5pts for readability
            if qr.grammar_error_count > 0 or qr.spelling_error_count > 0:
                grammar_penalty = min(10, (qr.grammar_error_count + qr.spelling_error_count) * 2)
                audit_result["score"] = max(0, audit_result["score"] - grammar_penalty)
                audit_result["issues"].append(
                    f"Grammar penalty: -{grammar_penalty}pts "
                    f"({qr.grammar_error_count} grammar, {qr.spelling_error_count} spelling errors)"
                )

            if qr.hemingway_grade > 12:
                readability_penalty = min(5, qr.hemingway_grade - 12)
                audit_result["score"] = max(0, audit_result["score"] - readability_penalty)
                audit_result["issues"].append(
                    f"Readability penalty: -{readability_penalty}pts (grade {qr.hemingway_grade})"
                )

        except Exception as exc:
            console.print(f"  [yellow]Quality check failed[/yellow] for {Path(file_path).name}: {exc}")
            error_count += 1

    return error_count


async def _fix_articles(failing: list, min_score: int) -> None:
    """Send each failing article to Claude with targeted fix instructions."""
    import aiofiles

    sem = asyncio.Semaphore(3)

    async def fix_one(result: dict) -> None:
        async with sem:
            issues_text = "\n".join(f"- {i}" for i in result["issues"])
            file_path = result["file"]

            async with aiofiles.open(file_path, encoding="utf-8") as f:
                current_content = await f.read()

            prompt = (
                f"This article scored {result['score']}/100 on an SEO audit. "
                f"Fix ONLY these specific issues — do not change the overall structure, tone, or length:\n\n"
                f"{issues_text}\n\n"
                f"Return the complete revised article including the front matter. "
                f"Make minimal targeted changes.\n\n"
                f"---ARTICLE---\n{current_content}"
            )

            revised = await llm.async_complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
            )

            # Strip any accidental fences around the whole response
            revised = revised.strip()
            if revised.startswith("```"):
                lines = revised.split("\n")
                end = -1 if lines[-1].strip() == "```" else len(lines)
                revised = "\n".join(lines[1:end])

            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(revised)

            console.print(f"  [green]fixed[/green]  {Path(file_path).name}")

    await asyncio.gather(*[fix_one(r) for r in failing])


if __name__ == "__main__":
    main()
