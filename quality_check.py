"""
Quality checking module — grammar, style, and readability analysis.

Three backends:
  1. LanguageTool  — free REST API for grammar/spelling/style errors
  2. Grammarly     — enterprise Writing Score API (requires client credentials)
  3. Hemingway     — algorithmic readability metrics (textstat + regex)

Usage:
  from quality_check import run_quality_check

  result = run_quality_check(
      text="Your article body here...",
      backends=["languagetool", "hemingway"],  # or ["grammarly", "hemingway"]
  )
  # result keys: grammar_errors, readability_grade, hemingway_score,
  #              grammarly_score, annotations, issues
"""

import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Annotation:
    """A single inline quality issue attached to a sentence or phrase."""
    text: str           # The offending text snippet
    offset: int         # Character offset in original text
    length: int         # Length of the offending span
    message: str        # Human-readable explanation
    replacements: list  # Suggested fixes (may be empty)
    category: str       # "grammar" | "spelling" | "style" | "readability"
    severity: str       # "error" | "warning" | "suggestion"


@dataclass
class QualityResult:
    """Aggregate quality check result for one article."""
    backends_used: list = field(default_factory=list)

    # Grammar / spelling
    grammar_error_count: int = 0
    spelling_error_count: int = 0

    # Readability (Hemingway-style)
    flesch_kincaid_grade: float = 0.0    # Grade level (lower = easier)
    flesch_reading_ease: float = 0.0     # 0–100 (higher = easier)
    hemingway_grade: int = 0             # Hemingway app equivalent grade
    passive_voice_count: int = 0
    adverb_count: int = 0
    hard_sentence_count: int = 0         # sentences flagged as hard to read
    very_hard_sentence_count: int = 0    # sentences flagged as very hard

    # Grammarly
    grammarly_score: Optional[int] = None        # 0–100
    grammarly_correctness: Optional[int] = None
    grammarly_clarity: Optional[int] = None
    grammarly_engagement: Optional[int] = None
    grammarly_delivery: Optional[int] = None

    # Inline annotations
    annotations: list = field(default_factory=list)

    # Summary
    issues: list = field(default_factory=list)      # human-readable issue strings

    def to_dict(self) -> dict:
        return {
            "backends_used": self.backends_used,
            "grammar_error_count": self.grammar_error_count,
            "spelling_error_count": self.spelling_error_count,
            "flesch_kincaid_grade": self.flesch_kincaid_grade,
            "flesch_reading_ease": self.flesch_reading_ease,
            "hemingway_grade": self.hemingway_grade,
            "passive_voice_count": self.passive_voice_count,
            "adverb_count": self.adverb_count,
            "hard_sentence_count": self.hard_sentence_count,
            "very_hard_sentence_count": self.very_hard_sentence_count,
            "grammarly_score": self.grammarly_score,
            "grammarly_correctness": self.grammarly_correctness,
            "grammarly_clarity": self.grammarly_clarity,
            "grammarly_engagement": self.grammarly_engagement,
            "grammarly_delivery": self.grammarly_delivery,
            "annotation_count": len(self.annotations),
            "issues": self.issues,
        }


# ── Text helpers ──────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Convert Markdown to plain text for quality analysis."""
    text = re.sub(r"```[\s\S]*?```", " ", text)         # fenced code blocks
    text = re.sub(r"`[^`]+`", " ", text)                 # inline code
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)         # images
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # links → text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"[*_~>|]", " ", text)                 # emphasis etc.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """Split plain text into sentences."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in parts if s.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _syllable_count(word: str) -> int:
    """Estimate syllable count via vowel-group heuristic."""
    word = word.lower().strip(".,!?;:'\"")
    if not word:
        return 0
    vowels = "aeiou"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Silent 'e' at end
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


# ── Hemingway backend ─────────────────────────────────────────────────────────

_PASSIVE_PATTERN = re.compile(
    r"\b(am|is|are|was|were|be|been|being)\s+"
    r"([\w]+ed|[\w]+en|[\w]+t)\b",
    re.IGNORECASE,
)

_ADVERB_PATTERN = re.compile(
    r"\b\w+ly\b",
    re.IGNORECASE,
)

# Words with simpler alternatives (Hemingway-style)
_COMPLEX_WORDS = {
    "utilize": "use", "leverage": "use", "facilitate": "help", "implement": "use",
    "commence": "start", "terminate": "end", "demonstrate": "show",
    "endeavor": "try", "purchase": "buy", "obtain": "get", "sufficient": "enough",
    "additional": "more", "assistance": "help", "subsequently": "then",
    "approximately": "about", "consequently": "so", "nevertheless": "still",
    "furthermore": "also", "therefore": "so", "regarding": "about",
}


def _flesch_kincaid(text: str) -> tuple[float, float]:
    """Return (grade_level, reading_ease) using Flesch-Kincaid formulas."""
    sentences = _split_sentences(text)
    words = re.findall(r"\b\w+\b", text)
    if not sentences or not words:
        return 0.0, 0.0

    total_syllables = sum(_syllable_count(w) for w in words)
    num_words = len(words)
    num_sentences = len(sentences)

    avg_sentence_length = num_words / num_sentences
    avg_syllables_per_word = total_syllables / num_words

    grade = 0.39 * avg_sentence_length + 11.8 * avg_syllables_per_word - 15.59
    ease = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word

    return round(max(0, grade), 1), round(min(100, max(0, ease)), 1)


def _hemingway_grade(reading_ease: float) -> int:
    """Convert Flesch Reading Ease to approximate Hemingway app grade."""
    if reading_ease >= 90:
        return 5
    elif reading_ease >= 80:
        return 6
    elif reading_ease >= 70:
        return 7
    elif reading_ease >= 60:
        return 9
    elif reading_ease >= 50:
        return 11
    elif reading_ease >= 30:
        return 14
    else:
        return 17


def _flag_hard_sentences(sentences: list[str]) -> tuple[list[str], list[str]]:
    """Return (hard_sentences, very_hard_sentences) based on word count and syllables."""
    hard, very_hard = [], []
    for sent in sentences:
        words = re.findall(r"\b\w+\b", sent)
        wc = len(words)
        syllables = sum(_syllable_count(w) for w in words)
        avg_syl = syllables / wc if wc else 0

        # Hemingway thresholds: >14 words OR high syllable avg → hard
        # >25 words → very hard
        if wc > 25 or avg_syl > 2.0:
            very_hard.append(sent)
        elif wc > 14 or avg_syl > 1.7:
            hard.append(sent)

    return hard, very_hard


def _run_hemingway(text: str, plain_text: str) -> tuple[QualityResult, list[Annotation]]:
    """Run algorithmic Hemingway-style analysis."""
    result = QualityResult()
    annotations = []

    grade, ease = _flesch_kincaid(plain_text)
    result.flesch_kincaid_grade = grade
    result.flesch_reading_ease = ease
    result.hemingway_grade = _hemingway_grade(ease)

    sentences = _split_sentences(plain_text)

    # Passive voice
    for m in _PASSIVE_PATTERN.finditer(plain_text):
        result.passive_voice_count += 1
        annotations.append(Annotation(
            text=m.group(0),
            offset=m.start(),
            length=len(m.group(0)),
            message="Passive voice — consider rewriting in active voice",
            replacements=[],
            category="style",
            severity="suggestion",
        ))

    # Adverbs
    for m in _ADVERB_PATTERN.finditer(plain_text):
        word = m.group(0).lower()
        # Skip common adverbs that are rarely problematic
        if word not in {"also", "only", "very", "just", "really", "already",
                        "likely", "nearly", "early", "daily", "weekly", "finally",
                        "simply", "usually", "quickly", "easily", "clearly"}:
            result.adverb_count += 1
            annotations.append(Annotation(
                text=m.group(0),
                offset=m.start(),
                length=len(m.group(0)),
                message=f"Adverb '{m.group(0)}' — consider removing or replacing with a stronger verb",
                replacements=[],
                category="style",
                severity="suggestion",
            ))

    # Hard sentences
    hard, very_hard = _flag_hard_sentences(sentences)
    result.hard_sentence_count = len(hard)
    result.very_hard_sentence_count = len(very_hard)

    for sent in very_hard:
        idx = plain_text.find(sent[:40])
        annotations.append(Annotation(
            text=sent[:80] + ("..." if len(sent) > 80 else ""),
            offset=max(0, idx),
            length=len(sent),
            message="Very hard to read — split into shorter sentences",
            replacements=[],
            category="readability",
            severity="warning",
        ))

    for sent in hard:
        idx = plain_text.find(sent[:40])
        annotations.append(Annotation(
            text=sent[:80] + ("..." if len(sent) > 80 else ""),
            offset=max(0, idx),
            length=len(sent),
            message="Hard to read — consider simplifying",
            replacements=[],
            category="readability",
            severity="suggestion",
        ))

    # Complex words
    for word, simpler in _COMPLEX_WORDS.items():
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for m in pattern.finditer(plain_text):
            annotations.append(Annotation(
                text=m.group(0),
                offset=m.start(),
                length=len(m.group(0)),
                message=f"Consider replacing '{m.group(0)}' with '{simpler}'",
                replacements=[simpler],
                category="style",
                severity="suggestion",
            ))

    # Build issues summary
    issues = []
    if result.hemingway_grade > 10:
        issues.append(f"Readability grade {result.hemingway_grade} (target ≤10 for general audience)")
    if result.passive_voice_count > 3:
        issues.append(f"{result.passive_voice_count} passive voice instances (target ≤3)")
    if result.adverb_count > 5:
        issues.append(f"{result.adverb_count} adverbs detected (consider cutting)")
    if result.very_hard_sentence_count > 2:
        issues.append(f"{result.very_hard_sentence_count} very hard sentences (split them up)")
    if result.hard_sentence_count > 5:
        issues.append(f"{result.hard_sentence_count} hard sentences")

    return result, annotations, issues


# ── LanguageTool backend ──────────────────────────────────────────────────────

_LT_DEFAULT_URL = "https://api.languagetool.org"
_LT_TIMEOUT = 30


def _run_languagetool(plain_text: str, language: str = "en-US") -> tuple[int, int, list[Annotation], list[str]]:
    """
    Call the LanguageTool REST API.
    Returns (grammar_errors, spelling_errors, annotations, issues).

    Set LANGUAGETOOL_URL env var to use a self-hosted instance.
    """
    base_url = os.environ.get("LANGUAGETOOL_URL", _LT_DEFAULT_URL).rstrip("/")
    endpoint = f"{base_url}/v2/check"

    # Respect LanguageTool's free tier: max 20 requests/min, 75K chars/request
    text_to_check = plain_text[:75000]

    try:
        resp = httpx.post(
            endpoint,
            data={"text": text_to_check, "language": language},
            timeout=_LT_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"LanguageTool API error: {exc}") from exc

    grammar_errors = 0
    spelling_errors = 0
    annotations = []
    issues = []

    for match in data.get("matches", []):
        rule = match.get("rule", {})
        cat_id = rule.get("issueType", "").lower()
        msg = match.get("message", "")
        offset = match.get("offset", 0)
        length = match.get("length", 0)
        replacements = [r["value"] for r in match.get("replacements", [])[:3]]
        context_text = match.get("context", {}).get("text", "")[
            match.get("context", {}).get("offset", 0):
            match.get("context", {}).get("offset", 0) + match.get("context", {}).get("length", 0)
        ]

        if cat_id in ("misspelling", "typos"):
            spelling_errors += 1
            severity = "error"
            category = "spelling"
        elif cat_id in ("grammar",):
            grammar_errors += 1
            severity = "error"
            category = "grammar"
        else:
            grammar_errors += 1
            severity = "warning"
            category = "style"

        annotations.append(Annotation(
            text=context_text or plain_text[offset: offset + length],
            offset=offset,
            length=length,
            message=msg,
            replacements=replacements,
            category=category,
            severity=severity,
        ))

    if spelling_errors:
        issues.append(f"{spelling_errors} spelling error(s) detected")
    if grammar_errors:
        issues.append(f"{grammar_errors} grammar/style issue(s) detected")

    return grammar_errors, spelling_errors, annotations, issues


# ── Grammarly backend ─────────────────────────────────────────────────────────

_GRAMMARLY_TOKEN_URL = "https://api.grammarly.com/oauth/token"
_GRAMMARLY_API_URL   = "https://api.grammarly.com"
_GRAMMARLY_TIMEOUT   = 30

_grammarly_token_cache: dict = {}  # {"access_token": ..., "expires_at": ...}


def _get_grammarly_token(client_id: str, client_secret: str) -> str:
    """Obtain (or return cached) OAuth 2.0 Bearer token for Grammarly API."""
    now = time.time()
    if _grammarly_token_cache.get("expires_at", 0) > now + 60:
        return _grammarly_token_cache["access_token"]

    resp = httpx.post(
        _GRAMMARLY_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=_GRAMMARLY_TIMEOUT,
    )
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _grammarly_token_cache["access_token"] = access_token
    _grammarly_token_cache["expires_at"] = now + expires_in

    return access_token


def _run_grammarly(plain_text: str) -> tuple[Optional[int], dict, list[str]]:
    """
    Call the Grammarly Writing Score API.
    Returns (overall_score, score_breakdown_dict, issues).

    Requires env vars:
      GRAMMARLY_CLIENT_ID     — OAuth2 client ID from developer.grammarly.com
      GRAMMARLY_CLIENT_SECRET — OAuth2 client secret
      GRAMMARLY_API_URL       — optional override (default: https://api.grammarly.com)
    """
    client_id = os.environ.get("GRAMMARLY_CLIENT_ID", "")
    client_secret = os.environ.get("GRAMMARLY_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Grammarly backend requires GRAMMARLY_CLIENT_ID and GRAMMARLY_CLIENT_SECRET env vars. "
            "Sign up at https://developer.grammarly.com/ for enterprise access."
        )

    base_url = os.environ.get("GRAMMARLY_API_URL", _GRAMMARLY_API_URL).rstrip("/")
    token = _get_grammarly_token(client_id, client_secret)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Writing Score API endpoint
    endpoint = f"{base_url}/api/writing-score/v1/score"
    payload = {
        "text": plain_text[:50000],  # API limit
        "dialect": "american",
    }

    try:
        resp = httpx.post(endpoint, json=payload, headers=headers, timeout=_GRAMMARLY_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise RuntimeError("Grammarly API: authentication failed — check GRAMMARLY_CLIENT_ID/SECRET") from exc
        elif exc.response.status_code == 403:
            raise RuntimeError("Grammarly API: access denied — ensure your plan includes the Writing Score API") from exc
        raise RuntimeError(f"Grammarly API error {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Grammarly API connection error: {exc}") from exc

    overall = data.get("overall", data.get("score"))
    breakdown = {
        "correctness": data.get("correctness"),
        "clarity":     data.get("clarity"),
        "engagement":  data.get("engagement"),
        "delivery":    data.get("delivery"),
    }

    issues = []
    if overall is not None and overall < 80:
        issues.append(f"Grammarly writing score {overall}/100 (target ≥80)")

    return overall, breakdown, issues


# ── Review file writer ────────────────────────────────────────────────────────

def write_review_file(article_path: str, result: QualityResult) -> str:
    """
    Write an annotated review Markdown file alongside the article.
    Returns the path to the review file.
    """
    from pathlib import Path

    article = Path(article_path)
    review_path = article.with_suffix(".review.md")

    lines = [
        f"# Quality Review: {article.name}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Grammar errors | {result.grammar_error_count} |",
        f"| Spelling errors | {result.spelling_error_count} |",
        f"| Readability grade | {result.hemingway_grade} |",
        f"| Flesch Reading Ease | {result.flesch_reading_ease} |",
        f"| Flesch-Kincaid Grade | {result.flesch_kincaid_grade} |",
        f"| Passive voice | {result.passive_voice_count} |",
        f"| Adverbs | {result.adverb_count} |",
        f"| Hard sentences | {result.hard_sentence_count} |",
        f"| Very hard sentences | {result.very_hard_sentence_count} |",
    ]

    if result.grammarly_score is not None:
        lines.append(f"| Grammarly score | {result.grammarly_score}/100 |")

    if result.issues:
        lines += ["", "## Issues", ""]
        for issue in result.issues:
            lines.append(f"- {issue}")

    # Group annotations by category
    by_cat: dict[str, list[Annotation]] = {}
    for ann in result.annotations:
        by_cat.setdefault(ann.category, []).append(ann)

    for cat, anns in sorted(by_cat.items()):
        if not anns:
            continue
        lines += ["", f"## {cat.title()} ({len(anns)})", ""]
        for ann in anns[:30]:  # cap at 30 per category
            sev_icon = {"error": "🔴", "warning": "🟡", "suggestion": "🔵"}.get(ann.severity, "•")
            lines.append(f"{sev_icon} **{ann.message}**")
            lines.append(f"  > {ann.text}")
            if ann.replacements:
                lines.append(f"  Suggestions: {', '.join(ann.replacements)}")
            lines.append("")

    review_path.write_text("\n".join(lines), encoding="utf-8")
    return str(review_path)


# ── Public API ────────────────────────────────────────────────────────────────

def run_quality_check(
    text: str,
    backends: list[str] | None = None,
    language: str = "en-US",
    write_review: bool = False,
    article_path: str | None = None,
) -> QualityResult:
    """
    Run quality checks against the given article text.

    Args:
        text:         Raw article text (Markdown OK — will be stripped).
        backends:     List of backends to run. Options: "languagetool", "grammarly", "hemingway".
                      Defaults to ["hemingway"] (always runs; LanguageTool and Grammarly are opt-in).
        language:     BCP-47 language code for LanguageTool (default: "en-US").
        write_review: If True and article_path is set, write a .review.md annotation file.
        article_path: Path to the source article (used for write_review).

    Returns:
        QualityResult dataclass with all metrics and inline annotations.
    """
    if backends is None:
        backends = ["hemingway"]

    plain = _strip_markdown(text)
    result = QualityResult(backends_used=list(backends))

    # Always run Hemingway (algorithmic, no external dependency)
    hw_result, hw_annotations, hw_issues = _run_hemingway(text, plain)
    result.flesch_kincaid_grade = hw_result.flesch_kincaid_grade
    result.flesch_reading_ease = hw_result.flesch_reading_ease
    result.hemingway_grade = hw_result.hemingway_grade
    result.passive_voice_count = hw_result.passive_voice_count
    result.adverb_count = hw_result.adverb_count
    result.hard_sentence_count = hw_result.hard_sentence_count
    result.very_hard_sentence_count = hw_result.very_hard_sentence_count
    result.annotations.extend(hw_annotations)
    result.issues.extend(hw_issues)

    if "languagetool" in backends:
        grammar_errors, spelling_errors, lt_annotations, lt_issues = _run_languagetool(plain, language)
        result.grammar_error_count += grammar_errors
        result.spelling_error_count += spelling_errors
        result.annotations.extend(lt_annotations)
        result.issues.extend(lt_issues)

    if "grammarly" in backends:
        overall, breakdown, gr_issues = _run_grammarly(plain)
        result.grammarly_score = overall
        result.grammarly_correctness = breakdown.get("correctness")
        result.grammarly_clarity = breakdown.get("clarity")
        result.grammarly_engagement = breakdown.get("engagement")
        result.grammarly_delivery = breakdown.get("delivery")
        result.issues.extend(gr_issues)

    if write_review and article_path:
        write_review_file(article_path, result)

    return result


def run_quality_check_file(
    article_path: str,
    backends: list[str] | None = None,
    language: str = "en-US",
    write_review: bool = True,
) -> QualityResult:
    """Convenience wrapper — reads file and runs quality check."""
    from pathlib import Path

    content = Path(article_path).read_text(encoding="utf-8")

    # Strip YAML front matter
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4:].strip()

    return run_quality_check(
        text=content,
        backends=backends,
        language=language,
        write_review=write_review,
        article_path=article_path,
    )
