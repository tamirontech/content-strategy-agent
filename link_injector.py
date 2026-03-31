"""
Injects Markdown internal links into article files.
Safely handles edge cases: headings, code blocks, existing links.
"""

import re
from pathlib import Path


# Patterns that indicate we should NOT linkify a match
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_EXISTING_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def _protected_ranges(body: str) -> list:
    """
    Return a list of (start, end) ranges in body that must not be modified:
    code blocks, inline code, existing links, headings.
    """
    ranges = []
    for pattern in (_CODE_BLOCK_RE, _INLINE_CODE_RE, _EXISTING_LINK_RE, _HEADING_RE):
        for m in pattern.finditer(body):
            ranges.append((m.start(), m.end()))
    return ranges


def _in_protected_range(start: int, end: int, protected: list) -> bool:
    return any(p_start <= start and end <= p_end for p_start, p_end in protected)


def inject_links(file_path: str, opportunities: list) -> dict:
    """
    Inject link opportunities into the article at file_path.
    Only replaces the FIRST occurrence of each anchor text.
    Skips anchors inside headings, code blocks, or existing links.

    Returns {"injected": [...], "skipped": [...]}
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")

    # Split front matter from body so we only edit the body
    front_matter = ""
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            front_matter = content[: end + 4]
            body = content[end + 4:]

    injected = []
    skipped = []

    for opp in opportunities:
        anchor = opp["anchor"]
        url = opp["url"]

        protected = _protected_ranges(body)
        match = re.search(re.escape(anchor), body)

        if not match:
            skipped.append({**opp, "reason": "anchor not found in body"})
            continue

        if _in_protected_range(match.start(), match.end(), protected):
            skipped.append({**opp, "reason": "anchor is inside a heading, code block, or existing link"})
            continue

        # Replace only the first occurrence
        replacement = f"[{anchor}]({url})"
        body = body[: match.start()] + replacement + body[match.end():]
        injected.append({"anchor": anchor, "url": url})

    # Write back
    if injected:
        path.write_text(front_matter + body, encoding="utf-8")

    return {"injected": injected, "skipped": skipped}
