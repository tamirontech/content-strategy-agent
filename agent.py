import json
import llm

SYSTEM_PROMPT = (
    "You are an expert SEO content strategist with deep knowledge of pillar content architecture. "
    "You create comprehensive, data-driven content strategies. "
    "Always respond with valid JSON only — no markdown code blocks, no explanations outside the JSON."
)


def generate_strategy(vertical: str) -> dict:
    """
    Analyse the vertical and generate 5 pillars with seed keywords.
    Returns a structured strategy dict.
    """
    prompt = f"""Analyze this business vertical and create a pillar content strategy.

Vertical: {vertical}

Return a JSON object with this exact structure:
{{
  "vertical_summary": "One sentence describing the vertical",
  "target_audience": "Primary audience description",
  "pillars": [
    {{
      "number": 1,
      "title": "SEO-optimized pillar page title",
      "description": "2-3 sentences on what this pillar covers and why it matters",
      "search_intent": "informational",
      "seed_keywords": [
        "primary keyword",
        "secondary keyword",
        "related keyword 1",
        "related keyword 2",
        "related keyword 3",
        "related keyword 4"
      ],
      "cluster_pages": [
        "Supporting article title 1",
        "Supporting article title 2",
        "Supporting article title 3",
        "Supporting article title 4",
        "Supporting article title 5"
      ]
    }}
  ]
}}

Requirements:
- Generate exactly 5 pillars covering distinct aspects of the vertical
- search_intent must be one of: informational, commercial, transactional, navigational
- Each pillar needs 6-8 seed_keywords (exact phrases people would search)
- Each pillar needs exactly 5 cluster_pages (supporting article titles)
- Seed keywords must be diverse: include head terms, modifier variants, and audience-specific terms
- Do NOT repeat the same keyword across pillars
- Return only valid JSON with no markdown formatting"""

    response_text = llm.complete(
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
        max_tokens=4000,
        json_mode=True,
    )

    # Strip accidental markdown fences (some models add them despite instructions)
    response_text = response_text.strip()
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[1:end])

    return json.loads(response_text)
