import csv
from pathlib import Path

STRATEGY_HEADERS = [
    "Pillar #",
    "Pillar Title",
    "Pillar Description",
    "Search Intent",
    "Keyword",
    "Monthly Volume",
    "Competition",
    "CPC ($)",
    "Keyword Type",
    "Competitor Overlap",
    "Cluster Pages",
]

GAP_HEADERS = [
    "Section",
    "Keyword",
    "Monthly Volume",
    "Competition",
    "CPC ($)",
    "Ranked By (Competitors)",
    "Suggested Pillar",
]


def write_csv(
    strategy: dict,
    keyword_data: dict,
    output_path: str,
    overlap_map: dict = None,
    gap_keywords: list = None,
) -> int:
    """
    Write the full strategy to a CSV file.
    Returns the number of strategy keyword rows written.

    overlap_map: {keyword_lower: [domain1, domain2, ...]}
    gap_keywords: list of gap keyword dicts from competitors.find_gap_keywords()
    """
    overlap_map = overlap_map or {}
    gap_keywords = gap_keywords or []
    path = Path(output_path)
    rows_written = 0

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # ── Strategy Keywords Section ──────────────────────────────────────
        writer.writerow(STRATEGY_HEADERS)

        for pillar in strategy["pillars"]:
            pillar_num = pillar["number"]
            cluster_pages = " | ".join(pillar.get("cluster_pages", []))
            keywords = keyword_data.get(pillar_num, [])

            if keywords:
                for kw in keywords:
                    overlap = overlap_map.get(kw["keyword"].lower(), [])
                    writer.writerow([
                        pillar_num,
                        pillar["title"],
                        pillar["description"],
                        pillar["search_intent"],
                        kw["keyword"],
                        kw["monthly_volume"],
                        kw["competition"],
                        kw["cpc"],
                        kw["keyword_type"],
                        ", ".join(overlap) if overlap else "",
                        cluster_pages,
                    ])
                    rows_written += 1
            else:
                writer.writerow([
                    pillar_num,
                    pillar["title"],
                    pillar["description"],
                    pillar["search_intent"],
                    "(no keyword data returned)",
                    "", "", "", "", "", cluster_pages,
                ])
                rows_written += 1

        # ── Competitor Gap Keywords Section ───────────────────────────────
        if gap_keywords:
            writer.writerow([])  # blank separator row
            writer.writerow(GAP_HEADERS)

            for kw in gap_keywords:
                writer.writerow([
                    "GAP OPPORTUNITY",
                    kw["keyword"],
                    kw["monthly_volume"],
                    kw.get("competition", "N/A"),
                    kw["cpc"],
                    ", ".join(kw.get("ranked_by", [])),
                    "",  # user fills in suggested pillar
                ])

    return rows_written
