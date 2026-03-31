import json
import llm

SYSTEM_PROMPT = (
    "You are an expert SEO content strategist and editorial planner. "
    "You create detailed content briefs that give writers and AI agents everything "
    "they need to produce high-ranking, well-structured articles. "
    "Always respond with valid JSON only — no markdown, no explanations outside the JSON."
)


def generate_pillar_briefs(pillar: dict, keywords: list, num_articles: int = 20) -> list:
    """
    Generate num_articles content briefs for a single pillar.
    Returns a list of brief dicts ready to write to JSON/CSV.
    """
    top_keywords = sorted(keywords, key=lambda x: x["monthly_volume"], reverse=True)[:60]
    kw_lines = "\n".join(
        f"  - {kw['keyword']} (vol: {kw['monthly_volume']:,}, type: {kw['keyword_type']})"
        for kw in top_keywords
    )

    cluster_pages = pillar.get("cluster_pages", [])
    n_cluster = len(cluster_pages)
    remaining = num_articles - n_cluster

    prompt = f"""Create exactly {num_articles} content briefs for articles under this pillar.

PILLAR:
  Title: {pillar['title']}
  Description: {pillar['description']}
  Search Intent: {pillar['search_intent']}

REQUIRED ARTICLES (must be the first {n_cluster} briefs, titles must match exactly):
{chr(10).join(f"  {i+1}. {t}" for i, t in enumerate(cluster_pages))}

ADDITIONAL ARTICLES NEEDED: {remaining} more articles to complete the {num_articles} total.
Generate these from the keyword list below — pick topics with clear search demand.

AVAILABLE KEYWORDS:
{kw_lines}

Return a JSON array of exactly {num_articles} objects. Each object:
{{
  "article_number": 1,
  "title": "SEO-optimized article title (include primary keyword naturally)",
  "slug": "url-friendly-slug-no-special-chars",
  "primary_keyword": "the single most important keyword",
  "secondary_keywords": ["kw 2", "kw 3", "kw 4", "kw 5"],
  "search_intent": "informational|commercial|transactional|navigational",
  "word_count_target": 2000,
  "table_of_contents": [
    {{"level": "h2", "heading": "Section heading", "notes": "Writer guidance for this section"}},
    {{"level": "h3", "heading": "Subsection", "notes": ""}}
  ],
  "meta_description": "Compelling 150-155 char description with primary keyword",
  "cta": "Primary CTA for this specific article",
  "internal_link_to_pillar": true
}}

Rules:
- First {n_cluster} briefs must use the required article titles exactly as given
- Every article must have a DIFFERENT primary_keyword — no duplicates across the {num_articles} briefs
- Distribute the keyword list across articles — don't stack all top keywords on one article
- word_count_target guidance: how-to/questions = 1200–1800, listicles/comparisons = 1800–2500, guides = 2500–4000
- table_of_contents must have 6–10 entries mixing h2 and h3
- Always include a "Frequently Asked Questions" h2 as the last section
- Return only a valid JSON array, no markdown wrapping"""

    response_text = llm.complete(
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
        max_tokens=10000,
        json_mode=True,
    )

    response_text = response_text.strip()
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[1:end])

    briefs = json.loads(response_text)

    for brief in briefs:
        brief["pillar_number"] = pillar["number"]
        brief["pillar_title"] = pillar["title"]

    return briefs
