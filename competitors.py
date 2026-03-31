from typing import Optional

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"


def get_competitor_keywords(
    client,
    domains: list,
    location_code: Optional[int],
    language_code: str,
    limit: int = 200,
    min_volume: int = 50,
) -> dict:
    """
    Fetch organic-ranking keywords for each competitor domain via DataForSEO Labs.
    Returns {domain: [{"keyword", "monthly_volume", "cpc", "competition", "position"}]}
    """
    import requests

    results = {}

    for domain in domains:
        payload = {
            "target": domain.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0],
            "language_code": language_code,
            "limit": limit,
            "order_by": ["keyword_data.keyword_info.search_volume,desc"],
            "filters": [
                ["keyword_data.keyword_info.search_volume", ">", min_volume]
            ],
        }
        if location_code is not None:
            payload["location_code"] = location_code

        resp = requests.post(
            f"{DATAFORSEO_BASE_URL}/dataforseo_labs/google/ranked_keywords/live",
            headers=client.headers,
            json=[payload],
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        keywords = []
        try:
            tasks = data.get("tasks", [])
            items = tasks[0]["result"][0].get("items", []) or []
        except (IndexError, KeyError, TypeError):
            items = []

        for item in items:
            kd = item.get("keyword_data", {})
            ki = kd.get("keyword_info", {})
            serp = item.get("ranked_serp_element", {}).get("serp_item", {})
            keyword = kd.get("keyword", "")
            if not keyword:
                continue
            keywords.append({
                "keyword": keyword,
                "monthly_volume": ki.get("search_volume") or 0,
                "cpc": round(ki.get("cpc") or 0.0, 2),
                "competition": ki.get("competition_level", "N/A"),
                "position": serp.get("rank_group", ""),
            })

        results[domain] = keywords

    return results


def build_overlap_map(competitor_keywords: dict) -> dict:
    """
    Build a lookup: {keyword_lower: [domain1, domain2, ...]}
    Used to annotate strategy keywords with which competitors rank for them.
    """
    overlap: dict = {}
    for domain, keywords in competitor_keywords.items():
        for kw in keywords:
            key = kw["keyword"].lower()
            overlap.setdefault(key, []).append(domain)
    return overlap


def find_gap_keywords(competitor_keywords: dict, strategy_keyword_set: set) -> list:
    """
    Return keywords competitors rank for that are NOT in the strategy.
    Sorted by search volume descending.
    Each item: {"keyword", "monthly_volume", "cpc", "competition", "ranked_by"}
    """
    seen: dict = {}  # keyword_lower -> best item

    for domain, keywords in competitor_keywords.items():
        for kw in keywords:
            key = kw["keyword"].lower()
            if key in strategy_keyword_set:
                continue
            if key not in seen:
                seen[key] = {**kw, "ranked_by": [domain]}
            else:
                seen[key]["ranked_by"].append(domain)
                # Keep the highest volume record
                if kw["monthly_volume"] > seen[key]["monthly_volume"]:
                    seen[key]["monthly_volume"] = kw["monthly_volume"]
                    seen[key]["cpc"] = kw["cpc"]

    return sorted(seen.values(), key=lambda x: x["monthly_volume"], reverse=True)
