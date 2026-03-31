import llm


async def write_article(brief: dict) -> str:
    """
    Write a complete article from a brief dict.
    Returns the article as a Markdown string.
    """
    secondary_kws = ", ".join(brief.get("secondary_keywords", []))

    prompt = f"""Write a complete, high-quality SEO article based on this brief.

TITLE: {brief["title"]}
PRIMARY KEYWORD: {brief["primary_keyword"]}
SECONDARY KEYWORDS: {secondary_kws}
SEARCH INTENT: {brief["search_intent"]}
TARGET WORD COUNT: {brief["word_count_target"]} words
CALL TO ACTION: {brief["cta"]}

TABLE OF CONTENTS (use these as your exact H2/H3 headings):
{brief["table_of_contents"]}

WRITING INSTRUCTIONS:
- Open with a compelling introduction (150–200 words) that immediately addresses the reader's search intent
- Include the primary keyword naturally within the first 100 words
- Follow the table of contents headings exactly as H2/H3 structure
- Write substantively under each section — no thin or filler content
- Weave secondary keywords in naturally (never force them)
- Include practical examples, actionable tips, data, or comparisons where relevant
- The FAQ section must contain 4–6 real questions readers actually have, with thorough 2–4 sentence answers
- Close with a conclusion that naturally leads into the CTA
- Tone: clear, confident, and appropriate for the stated search intent

Write the full article in Markdown. Start directly with the H1 title.
Do not include front matter, preamble, or any commentary outside the article."""

    return await llm.async_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8000,
    )
