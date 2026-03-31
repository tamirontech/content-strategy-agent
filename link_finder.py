"""
Uses Claude to identify natural internal linking opportunities in each article.
"""

import json
import re

import llm


async def find_link_opportunities(
    article: dict,
    content_map: list,
    min_relevance: float = 0.6,
) -> list:
    """
    Given an article entry and the full content map, ask Claude to identify
    up to 5 anchor text phrases that would make natural internal links.

    Returns list of {"anchor": str, "url": str, "relevance": float}
    filtered to min_relevance and validated against the article body.
    """
    article_file = article["file"]
    article_body = _read_body(article_file)
    if not article_body:
        return []

    # Filter candidate targets:
    # - not itself
    # - not already linked
    # - same pillar gets priority (cross-pillar max 1 link enforced in prompt)
    existing = set(article.get("existing_links", []))
    candidates = [
        e for e in content_map
        if e["file"] != article_file and e["url"] not in existing
    ]

    if not candidates:
        return []

    candidates_text = "\n".join(
        f'  [{i+1}] title="{c["title"]}" url="{c["url"]}" '
        f'keyword="{c["primary_keyword"]}" pillar={c["pillar"]} '
        f'summary="{c["summary"][:100]}"'
        for i, c in enumerate(candidates)
    )

    prompt = f"""You are an internal linking specialist. Identify natural anchor text opportunities in the article below.

ARTICLE TITLE: {article["title"]}
ARTICLE PILLAR: {article["pillar"]}

CANDIDATE PAGES TO LINK TO:
{candidates_text}

ARTICLE BODY (first 3000 chars):
{article_body[:3000]}

Find up to 5 phrases in the article body that would make natural, helpful internal links to the candidate pages.

Rules:
- The anchor text must be an EXACT substring of the article body (copy it character-for-character)
- Prefer same-pillar links; include at most 1 cross-pillar link
- The pillar page (article=01) must always be linked if not already present and the article is a cluster page
- Never suggest anchor text from inside a heading or code block
- No more than 2 links pointing to the same target URL
- Only suggest links that genuinely add reader value — no forced links

Return a JSON array only, no other text:
[
  {{"anchor": "exact phrase from article", "url": "/slug-of-target", "relevance": 0.9}},
  ...
]"""

    response = await llm.async_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )

    opportunities = _parse_json_response(response)

    # Validate anchor text actually exists in body and meets relevance threshold
    validated = []
    seen_urls: dict = {}
    for opp in opportunities:
        anchor = opp.get("anchor", "")
        url = opp.get("url", "")
        relevance = float(opp.get("relevance", 0))

        if relevance < min_relevance:
            continue
        if not anchor or not url:
            continue
        if anchor not in article_body:
            continue
        # Max 2 links to same URL
        if seen_urls.get(url, 0) >= 2:
            continue

        seen_urls[url] = seen_urls.get(url, 0) + 1
        validated.append({"anchor": anchor, "url": url, "relevance": relevance})

    return validated


def _read_body(file_path: str) -> str:
    """Read article file and return body (without front matter)."""
    try:
        content = open(file_path, encoding="utf-8").read()
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                return content[end + 4:].strip()
        return content
    except OSError:
        return ""


def _parse_json_response(text: str) -> list:
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    # Extract JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []
