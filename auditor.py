"""
SEO scoring engine — purely algorithmic, no LLM calls.
Reads a written article .md file and scores it against 10 SEO checks.
"""

import re
from pathlib import Path


# ── Front matter parsing ──────────────────────────────────────────────────────

def parse_front_matter(content: str) -> tuple[dict, str]:
    """
    Split YAML front matter from body.
    Returns (metadata_dict, body_text).
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    fm_block = content[3:end].strip()
    body = content[end + 4:].strip()

    meta = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")

    return meta, body


# ── Text helpers ──────────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def strip_markdown(text: str) -> str:
    """Remove markdown syntax to get plain text for keyword checks."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)  # code blocks
    text = re.sub(r"`[^`]+`", " ", text)                      # inline code
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)               # images
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)      # links → anchor text
    text = re.sub(r"[#*_~>|]", " ", text)                      # markdown chars
    return text


def keyword_occurrences(text: str, keyword: str) -> int:
    if not keyword:
        return 0
    pattern = re.compile(re.escape(keyword.lower()), re.IGNORECASE)
    return len(pattern.findall(text))


# ── Individual checks ─────────────────────────────────────────────────────────

def check_keyword_density(plain_body: str, primary_keyword: str, max_pts: int = 15) -> dict:
    wc = word_count(plain_body)
    if wc == 0 or not primary_keyword:
        return {"score": 0, "max": max_pts, "issue": "No body text or primary keyword found"}

    occurrences = keyword_occurrences(plain_body, primary_keyword)
    density = (occurrences / wc) * 1000  # per 1000 words

    if 3 <= density <= 8:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif 2 <= density < 3 or 8 < density <= 12:
        issue = f"Keyword density {density:.1f}/1000 words (target: 3–8)"
        return {"score": max_pts // 2, "max": max_pts, "issue": issue}
    else:
        issue = (
            f"Keyword density too low ({density:.1f}/1000 words)" if density < 2
            else f"Keyword stuffing detected ({density:.1f}/1000 words)"
        )
        return {"score": 0, "max": max_pts, "issue": issue}


def check_title_has_keyword(title: str, primary_keyword: str, max_pts: int = 10) -> dict:
    if not title or not primary_keyword:
        return {"score": 0, "max": max_pts, "issue": "Missing title or primary keyword"}

    if primary_keyword.lower() in title.lower():
        return {"score": max_pts, "max": max_pts, "issue": None}

    # Partial match — check if most words of keyword appear
    kw_words = set(primary_keyword.lower().split())
    title_words = set(title.lower().split())
    overlap = len(kw_words & title_words) / len(kw_words)
    if overlap >= 0.7:
        return {"score": max_pts // 2, "max": max_pts, "issue": f"Primary keyword not in title (partial match)"}

    return {"score": 0, "max": max_pts, "issue": f"Primary keyword '{primary_keyword}' not found in title"}


def check_keyword_in_intro(plain_body: str, primary_keyword: str, max_pts: int = 10) -> dict:
    if not primary_keyword:
        return {"score": 0, "max": max_pts, "issue": "No primary keyword"}

    words = plain_body.split()
    intro = " ".join(words[:120])
    if keyword_occurrences(intro, primary_keyword) > 0:
        return {"score": max_pts, "max": max_pts, "issue": None}

    return {"score": 0, "max": max_pts, "issue": "Primary keyword not found in first ~100 words"}


def check_heading_structure(body: str, max_pts: int = 10) -> dict:
    headings = re.findall(r"^(#{1,6})\s+(.+)$", body, re.MULTILINE)
    issues = []

    if not headings:
        return {"score": 0, "max": max_pts, "issue": "No headings found in article"}

    levels = [len(h[0]) for h in headings]
    h2_count = levels.count(2)
    h3_count = levels.count(3)

    if h2_count < 3:
        issues.append(f"Only {h2_count} H2 headings (need ≥3)")

    # Check H3s don't appear without a parent H2
    last_h2_pos = -1
    for i, lvl in enumerate(levels):
        if lvl == 2:
            last_h2_pos = i
        elif lvl == 3 and last_h2_pos == -1:
            issues.append("H3 appears before any H2")
            break

    # Check for skipped levels (H1 → H3 without H2)
    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 1:
            issues.append(f"Skipped heading level (H{levels[i-1]} → H{levels[i]})")
            break

    if not issues:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif len(issues) == 1:
        return {"score": max_pts // 2, "max": max_pts, "issue": issues[0]}
    else:
        return {"score": 0, "max": max_pts, "issue": "; ".join(issues)}


def check_word_count(plain_body: str, target: int, max_pts: int = 15) -> dict:
    if not target:
        return {"score": max_pts // 2, "max": max_pts, "issue": "No word count target in front matter"}

    wc = word_count(plain_body)
    deviation = abs(wc - target) / target

    if deviation <= 0.20:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif deviation <= 0.40:
        direction = "short" if wc < target else "long"
        return {
            "score": max_pts // 2,
            "max": max_pts,
            "issue": f"Word count {wc} is {direction} of target {target} (±{deviation*100:.0f}%)",
        }
    else:
        direction = "short" if wc < target else "long"
        return {
            "score": 0,
            "max": max_pts,
            "issue": f"Word count {wc} far {direction} of target {target} (±{deviation*100:.0f}%)",
        }


def check_meta_description(meta_desc: str, primary_keyword: str, max_pts: int = 10) -> dict:
    if not meta_desc:
        return {"score": 0, "max": max_pts, "issue": "Meta description missing from front matter"}

    issues = []
    length = len(meta_desc)

    if length < 140:
        issues.append(f"Meta description too short ({length} chars, need 140–160)")
    elif length > 160:
        issues.append(f"Meta description too long ({length} chars, need 140–160)")

    if primary_keyword and primary_keyword.lower() not in meta_desc.lower():
        issues.append("Primary keyword not in meta description")

    if not issues:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif len(issues) == 1:
        return {"score": max_pts // 2, "max": max_pts, "issue": issues[0]}
    else:
        return {"score": 0, "max": max_pts, "issue": "; ".join(issues)}


def check_secondary_keywords(plain_body: str, secondary_keywords: list, max_pts: int = 10) -> dict:
    if not secondary_keywords:
        return {"score": max_pts, "max": max_pts, "issue": None}

    present = [kw for kw in secondary_keywords if keyword_occurrences(plain_body, kw) > 0]
    coverage = len(present) / len(secondary_keywords)

    if coverage >= 0.60:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif coverage >= 0.40:
        missing = [kw for kw in secondary_keywords if kw not in present][:3]
        return {
            "score": max_pts // 2,
            "max": max_pts,
            "issue": f"Only {len(present)}/{len(secondary_keywords)} secondary keywords present. Missing: {', '.join(missing)}",
        }
    else:
        return {
            "score": 0,
            "max": max_pts,
            "issue": f"Only {len(present)}/{len(secondary_keywords)} secondary keywords present",
        }


def check_faq_section(body: str, max_pts: int = 10) -> dict:
    if re.search(r"##\s+.*(faq|frequently asked)", body, re.IGNORECASE):
        return {"score": max_pts, "max": max_pts, "issue": None}
    return {"score": 0, "max": max_pts, "issue": "No FAQ section found (need H2 matching 'FAQ' or 'Frequently Asked')"}


def check_internal_links(body: str, max_pts: int = 10) -> dict:
    links = re.findall(r"\[([^\]]+)\]\(([^\)]+)\)", body)
    internal = [l for l in links if not l[1].startswith("http")]
    all_links = len(links)
    internal_count = len(internal)

    if internal_count >= 2:
        return {"score": max_pts, "max": max_pts, "issue": None}
    elif internal_count == 1:
        return {"score": max_pts // 2, "max": max_pts, "issue": "Only 1 internal link (recommend ≥2)"}
    elif all_links > 0:
        return {"score": max_pts // 4, "max": max_pts, "issue": "No internal links found (external links present)"}
    else:
        return {"score": 0, "max": max_pts, "issue": "No links found in article"}


def check_cta_present(body: str, cta: str, max_pts: int = 5) -> dict:
    if not cta:
        return {"score": max_pts // 2, "max": max_pts, "issue": "No CTA in front matter"}

    # Check last 25% of article
    words = body.split()
    tail = " ".join(words[int(len(words) * 0.75):])
    cta_words = cta.lower().split()[:4]  # first 4 words of CTA
    tail_lower = tail.lower()

    if any(w in tail_lower for w in cta_words):
        return {"score": max_pts, "max": max_pts, "issue": None}

    # Check anywhere in article
    if any(w in body.lower() for w in cta_words):
        return {"score": max_pts // 2, "max": max_pts, "issue": "CTA present but not near the end of article"}

    return {"score": 0, "max": max_pts, "issue": f"CTA not found in article: '{cta}'"}


# ── Main audit function ───────────────────────────────────────────────────────

def audit_article(file_path: str) -> dict:
    """
    Run all SEO checks on a single article .md file.
    Returns a result dict with score, pass/fail, per-check details, and issues list.
    """
    path = Path(file_path)
    if not path.exists():
        return {"file": file_path, "score": 0, "passed": False, "issues": ["File not found"], "checks": {}}

    content = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(content)
    plain_body = strip_markdown(body)

    primary_keyword = meta.get("primary_keyword", "")
    secondary_raw = meta.get("secondary_keywords", "")
    secondary_keywords = [k.strip() for k in secondary_raw.split("|") if k.strip()] if secondary_raw else []
    word_count_target = int(meta.get("word_count_target", 0) or 0)
    meta_desc = meta.get("meta_description", "")
    title = meta.get("title", "")
    cta = meta.get("cta", "")

    checks = {
        "keyword_density":      check_keyword_density(plain_body, primary_keyword),
        "title_has_keyword":    check_title_has_keyword(title, primary_keyword),
        "keyword_in_intro":     check_keyword_in_intro(plain_body, primary_keyword),
        "heading_structure":    check_heading_structure(body),
        "word_count":           check_word_count(plain_body, word_count_target),
        "meta_description":     check_meta_description(meta_desc, primary_keyword),
        "secondary_keywords":   check_secondary_keywords(plain_body, secondary_keywords),
        "faq_section":          check_faq_section(body),
        "internal_links":       check_internal_links(body),
        "cta_present":          check_cta_present(body, cta),
    }

    total_score = sum(c["score"] for c in checks.values())
    max_score = sum(c["max"] for c in checks.values())
    normalized = round((total_score / max_score) * 100) if max_score else 0
    issues = [c["issue"] for c in checks.values() if c["issue"]]

    return {
        "file": str(path),
        "title": title or path.name,
        "primary_keyword": primary_keyword,
        "score": normalized,
        "passed": normalized >= 70,
        "word_count": word_count(plain_body),
        "word_count_target": word_count_target,
        "issues": issues,
        "checks": checks,
    }
