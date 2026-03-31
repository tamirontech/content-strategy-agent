"""
Scans a directory of written articles and builds a content map (slug/topic index).
Saves content_map.json for use by link_finder and link_injector.
"""

import json
import re
from pathlib import Path


def _parse_front_matter(content: str) -> tuple[dict, str]:
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


def _first_paragraph(body: str, max_chars: int = 200) -> str:
    """Extract first non-heading paragraph for use as summary."""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            # Strip markdown formatting
            clean = re.sub(r"[*_`\[\]]", "", line)
            return clean[:max_chars]
    return ""


def _existing_links(body: str) -> set:
    """Return set of URLs already linked in the article body."""
    return {m.group(1) for m in re.finditer(r"\]\(([^)]+)\)", body)}


def build_content_map(articles_dir: str, base_url: str) -> list:
    """
    Scan all article_*.md files under articles_dir.
    Returns a list of content map entry dicts.
    """
    base_url = base_url.rstrip("/")
    entries = []

    for path in sorted(Path(articles_dir).rglob("article_*.md")):
        content = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(content)

        slug = meta.get("slug", path.stem)
        url = f"{base_url}/{slug}" if base_url else f"/{slug}"

        entries.append({
            "file": str(path),
            "pillar": meta.get("pillar", ""),
            "article": meta.get("article", ""),
            "title": meta.get("title", path.name),
            "slug": slug,
            "url": url,
            "primary_keyword": meta.get("primary_keyword", ""),
            "summary": _first_paragraph(body),
            "existing_links": list(_existing_links(body)),
        })

    return entries


def save_content_map(entries: list, articles_dir: str) -> str:
    out_path = Path(articles_dir) / "content_map.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    return str(out_path)


def load_content_map(articles_dir: str) -> list:
    path = Path(articles_dir) / "content_map.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mark_links_added(articles_dir: str, file_path: str, new_links: list) -> None:
    """Update content_map.json to record newly injected links for a file."""
    entries = load_content_map(articles_dir)
    for entry in entries:
        if entry["file"] == file_path:
            existing = set(entry.get("existing_links", []))
            existing.update(new_links)
            entry["existing_links"] = list(existing)
            break
    save_content_map(entries, articles_dir)
