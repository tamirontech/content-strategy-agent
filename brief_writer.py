import csv
import json
from pathlib import Path

OVERVIEW_HEADERS = [
    "Pillar #",
    "Pillar Title",
    "Article #",
    "Title",
    "Slug",
    "Primary Keyword",
    "Secondary Keywords",
    "Search Intent",
    "Word Count Target",
    "Meta Description",
    "CTA",
    "Table of Contents",
]


def write_briefs_csv(all_briefs: list, output_path: str) -> int:
    """
    Write all briefs to a single overview CSV for human review.
    Returns number of rows written.
    """
    path = Path(output_path)
    rows = 0

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OVERVIEW_HEADERS)
        writer.writeheader()

        for brief in all_briefs:
            toc_flat = " | ".join(
                f"{'  ' if h['level'] == 'h3' else ''}{h['heading']}"
                for h in brief.get("table_of_contents", [])
            )
            writer.writerow({
                "Pillar #": brief["pillar_number"],
                "Pillar Title": brief["pillar_title"],
                "Article #": brief["article_number"],
                "Title": brief["title"],
                "Slug": brief["slug"],
                "Primary Keyword": brief["primary_keyword"],
                "Secondary Keywords": " | ".join(brief.get("secondary_keywords", [])),
                "Search Intent": brief["search_intent"],
                "Word Count Target": brief["word_count_target"],
                "Meta Description": brief["meta_description"],
                "CTA": brief["cta"],
                "Table of Contents": toc_flat,
            })
            rows += 1

    return rows


def write_briefs_json(all_briefs: list, output_dir: str) -> int:
    """
    Write individual JSON files organized as:
      output_dir/pillar_1/article_01.json
      output_dir/pillar_1/article_02.json
      ...

    Each JSON file is a self-contained brief for a writing agent.
    Returns total number of files written.
    """
    base = Path(output_dir)
    files_written = 0

    for brief in all_briefs:
        pillar_dir = base / f"pillar_{brief['pillar_number']}"
        pillar_dir.mkdir(parents=True, exist_ok=True)

        article_num = str(brief["article_number"]).zfill(2)
        file_path = pillar_dir / f"article_{article_num}.json"

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(brief, f, indent=2, ensure_ascii=False)

        files_written += 1

    return files_written


def load_strategy(strategy_path: str) -> dict:
    with open(strategy_path, encoding="utf-8") as f:
        return json.load(f)


def load_keywords(keywords_path: str) -> dict:
    with open(keywords_path, encoding="utf-8") as f:
        raw = json.load(f)
    # JSON keys are always strings; convert back to int
    return {int(k): v for k, v in raw.items()}
