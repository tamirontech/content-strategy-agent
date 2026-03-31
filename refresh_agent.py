"""
Refreshes an underperforming article by:
1. Identifying what top-ranking competitor pages cover that the article doesn't
2. Rewriting/expanding the article with Claude to close those gaps
"""

import re
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

import llm


# ── Competitor scraping ───────────────────────────────────────────────────────

async def scrape_page(url: str, timeout: int = 15) -> str:
    """Fetch a URL and extract the main text content."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentRefreshBot/1.0)"}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove nav, footer, ads, scripts, styles
    for tag in soup(["nav", "footer", "header", "aside", "script", "style",
                     "noscript", "form", "iframe", "advertisement"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
    if not main:
        return ""

    text = main.get_text(separator=" ", strip=True)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text[:6000]  # Cap at 6000 chars per competitor


async def fetch_competitor_content(keyword: str, competitor_urls: list) -> str:
    """
    Scrape up to 3 competitor URLs and combine their content.
    Falls back to empty string if scraping fails.
    """
    import asyncio
    urls = competitor_urls[:3]
    pages = await asyncio.gather(*[scrape_page(url) for url in urls], return_exceptions=True)

    combined = []
    for url, content in zip(urls, pages):
        if isinstance(content, str) and content.strip():
            combined.append(f"--- Competitor: {url} ---\n{content[:2000]}")

    return "\n\n".join(combined)


# ── Front matter helpers ──────────────────────────────────────────────────────

def _split_front_matter(content: str) -> tuple[str, str]:
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---", 3)
    if end == -1:
        return "", content
    return content[: end + 4], content[end + 4:].strip()


def _update_front_matter_field(fm: str, key: str, value: str) -> str:
    pattern = re.compile(rf'^{re.escape(key)}:.*$', re.MULTILINE)
    replacement = f'{key}: "{value}"'
    if pattern.search(fm):
        return pattern.sub(replacement, fm)
    # Add before closing ---
    return fm.rstrip().rstrip("---").rstrip() + f"\n{replacement}\n---"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


# ── Main refresh function ─────────────────────────────────────────────────────

async def refresh_article(
    article_path: str,
    gsc_keywords: list,
    competitor_urls: list,
) -> dict:
    """
    Refresh a single article.

    gsc_keywords: list of {"keyword", "position", "impressions"} from GSC
    competitor_urls: list of URLs to scrape for gap analysis

    Returns a summary dict with before/after stats.
    """
    path = Path(article_path)
    original_content = path.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(original_content)

    wc_before = _word_count(body)
    primary_kw = _extract_fm_value(front_matter, "primary_keyword")
    title = _extract_fm_value(front_matter, "title")

    # Top keywords the page ranks for
    top_kws = ", ".join(k["keyword"] for k in gsc_keywords[:10]) if gsc_keywords else "unknown"
    avg_position = (
        round(sum(k["position"] for k in gsc_keywords) / len(gsc_keywords), 1)
        if gsc_keywords else "unknown"
    )

    # Competitor content for gap analysis
    competitor_content = ""
    if competitor_urls:
        competitor_content = await fetch_competitor_content(primary_kw or title, competitor_urls)

    competitor_section = (
        f"\nCOMPETITOR CONTENT (topics covered by top-ranking pages):\n{competitor_content}"
        if competitor_content
        else ""
    )

    prompt = f"""You are an expert SEO content editor. Refresh and improve this underperforming article.

CURRENT PERFORMANCE:
- Title: {title}
- Primary keyword: {primary_kw}
- Current average position: {avg_position}
- Keywords it ranks for: {top_kws}
{competitor_section}

REFRESH INSTRUCTIONS:
1. Keep all existing H2 sections — do not remove or rename them
2. Expand thin sections with more depth, examples, and actionable detail
3. Add 1–3 new H2 sections covering topics competitors rank for that this article misses
4. Update any outdated phrasing (e.g. "in 2023" → current year)
5. Strengthen the introduction — make the first paragraph more compelling
6. Improve the FAQ — add 2 new questions relevant to what people search for
7. Target word count: {max(wc_before + 400, int(wc_before * 1.25))} words (current: {wc_before})
8. Do NOT change the title, slug, or front matter values

Return the complete refreshed article body in Markdown (no front matter).
Start directly with the H1 heading.

---CURRENT ARTICLE BODY---
{body}"""

    revised_body = await llm.async_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10000,
    )

    # Update front matter with refresh timestamp
    updated_fm = _update_front_matter_field(
        front_matter, "refreshed_at", datetime.now().isoformat()
    )
    updated_fm = _update_front_matter_field(updated_fm, "status", "refreshed")

    path.write_text(updated_fm + "\n\n" + revised_body.strip(), encoding="utf-8")

    wc_after = _word_count(revised_body)
    return {
        "file": article_path,
        "title": title,
        "primary_keyword": primary_kw,
        "avg_position": avg_position,
        "wc_before": wc_before,
        "wc_after": wc_after,
        "wc_delta": wc_after - wc_before,
        "competitor_sources": len([u for u in competitor_urls[:3] if u]),
    }


def _extract_fm_value(front_matter: str, key: str) -> str:
    m = re.search(rf'^{re.escape(key)}:\s*["\']?(.+?)["\']?\s*$', front_matter, re.MULTILINE)
    return m.group(1).strip() if m else ""
