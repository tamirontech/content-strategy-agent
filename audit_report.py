import csv
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

CSV_HEADERS = [
    "File", "Title", "Score", "Passed",
    "Keyword Density", "Title Has Keyword", "Keyword In Intro",
    "Heading Structure", "Word Count", "Meta Description",
    "Secondary Keywords", "FAQ Section", "Internal Links", "CTA Present",
    "Issues",
]


def write_csv(results: list, output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in results:
            checks = r.get("checks", {})
            writer.writerow({
                "File": r["file"],
                "Title": r["title"],
                "Score": r["score"],
                "Passed": "YES" if r["passed"] else "NO",
                "Keyword Density":    f"{checks.get('keyword_density',    {}).get('score', 0)}/{checks.get('keyword_density',    {}).get('max', 0)}",
                "Title Has Keyword":  f"{checks.get('title_has_keyword',  {}).get('score', 0)}/{checks.get('title_has_keyword',  {}).get('max', 0)}",
                "Keyword In Intro":   f"{checks.get('keyword_in_intro',   {}).get('score', 0)}/{checks.get('keyword_in_intro',   {}).get('max', 0)}",
                "Heading Structure":  f"{checks.get('heading_structure',  {}).get('score', 0)}/{checks.get('heading_structure',  {}).get('max', 0)}",
                "Word Count":         f"{checks.get('word_count',         {}).get('score', 0)}/{checks.get('word_count',         {}).get('max', 0)}",
                "Meta Description":   f"{checks.get('meta_description',   {}).get('score', 0)}/{checks.get('meta_description',   {}).get('max', 0)}",
                "Secondary Keywords": f"{checks.get('secondary_keywords', {}).get('score', 0)}/{checks.get('secondary_keywords', {}).get('max', 0)}",
                "FAQ Section":        f"{checks.get('faq_section',        {}).get('score', 0)}/{checks.get('faq_section',        {}).get('max', 0)}",
                "Internal Links":     f"{checks.get('internal_links',     {}).get('score', 0)}/{checks.get('internal_links',     {}).get('max', 0)}",
                "CTA Present":        f"{checks.get('cta_present',        {}).get('score', 0)}/{checks.get('cta_present',        {}).get('max', 0)}",
                "Issues": " | ".join(r.get("issues", [])),
            })


def write_json(results: list, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def print_summary(results: list, console: Console, min_score: int = 70) -> None:
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    avg_score = round(sum(r["score"] for r in results) / len(results)) if results else 0

    table = Table(header_style="bold cyan", box=None, show_lines=False)
    table.add_column("File", style="dim", width=35)
    table.add_column("Title", width=42)
    table.add_column("Score", justify="right", width=7)
    table.add_column("", width=6)  # pass/fail icon
    table.add_column("Top Issue", width=45)

    for r in sorted(results, key=lambda x: x["score"]):
        score_color = "green" if r["passed"] else ("yellow" if r["score"] >= 50 else "red")
        icon = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
        top_issue = r["issues"][0] if r["issues"] else ""
        table.add_row(
            Path(r["file"]).name,
            r["title"][:40],
            f"[{score_color}]{r['score']}[/{score_color}]",
            icon,
            top_issue[:43],
        )

    console.print(table)
    console.print()
    console.print(
        f"  [green]Passed: {len(passed)}[/green]  "
        f"[red]Failed: {len(failed)}[/red]  "
        f"Avg score: [bold]{avg_score}[/bold]  "
        f"Threshold: {min_score}"
    )

    # Top recurring issues
    issue_counts: dict = {}
    for r in results:
        for issue in r["issues"]:
            # Normalise to the first 6 words to group similar issues
            key = " ".join(issue.split()[:6])
            issue_counts[key] = issue_counts.get(key, 0) + 1

    if issue_counts:
        top = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        console.print()
        console.print("  [bold]Most common issues:[/bold]")
        for issue, count in top:
            console.print(f"    [dim]{count}x[/dim]  {issue}...")
