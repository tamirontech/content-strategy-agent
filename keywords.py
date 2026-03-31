import base64
from typing import Optional

import requests

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"


class DataForSEOClient:
    def __init__(self, login: str, password: str):
        credentials = base64.b64encode(f"{login}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    def get_keyword_ideas(
        self,
        seed_keywords: list,
        location_code: Optional[int],
        language_code: str,
        limit: int = 50,
    ) -> list:
        """
        Call DataForSEO Keywords for Keywords (Google Ads) endpoint.
        Returns list of keyword dicts with volume/competition/cpc.
        """
        payload = {
            "keywords": seed_keywords,
            "language_code": language_code,
            "include_adult_keywords": False,
            "sort_by": "search_volume",
            "limit": limit,
        }
        if location_code is not None:
            payload["location_code"] = location_code

        resp = requests.post(
            f"{DATAFORSEO_BASE_URL}/keywords_data/google_ads/keywords_for_keywords/live",
            headers=self.headers,
            json=[payload],
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        try:
            tasks = data.get("tasks", [])
            if not tasks:
                return []
            result = tasks[0].get("result", [])
            if not result:
                return []
            items = result[0].get("items", []) or []
        except (IndexError, KeyError, TypeError):
            return []

        keywords = []
        for item in items:
            if not item.get("keyword"):
                continue
            keywords.append({
                "keyword": item["keyword"],
                "monthly_volume": item.get("search_volume") or 0,
                "competition": item.get("competition_level", "N/A"),
                "cpc": round(item.get("cpc") or 0.0, 2),
            })

        return keywords


def categorize_keyword(keyword: str) -> str:
    """Categorize a keyword by type based on its structure."""
    words = keyword.lower().split()
    question_starters = {
        "how", "what", "why", "when", "where", "which", "who",
        "is", "are", "can", "does", "do", "will", "should", "would",
    }
    if words and words[0] in question_starters:
        return "question"
    if len(words) <= 2:
        return "head keyword"
    if len(words) >= 5:
        return "long tail"
    return "mid tail"


def expand_keywords_for_pillars(
    client: DataForSEOClient,
    pillars: list,
    location_code: Optional[int],
    language_code: str,
    max_keywords: int,
) -> dict:
    """
    For each pillar, call DataForSEO and attach category metadata.
    Returns {pillar_number: [keyword_dict, ...]}
    Deduplicates keywords across pillars (first pillar wins).
    """
    result = {}
    seen_keywords: set = set()

    for pillar in pillars:
        raw = client.get_keyword_ideas(
            seed_keywords=pillar["seed_keywords"],
            location_code=location_code,
            language_code=language_code,
            limit=max_keywords,
        )

        unique = []
        for kw in raw:
            key = kw["keyword"].lower()
            if key not in seen_keywords:
                seen_keywords.add(key)
                kw["keyword_type"] = categorize_keyword(kw["keyword"])
                unique.append(kw)

        result[pillar["number"]] = unique

    return result
