#!/usr/bin/env python3
"""Build a document-level searchable index from the Chinese book sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


LINK_RE = re.compile(r"\[[^\]]+\]\((docs/[^)#?]+\.md)(?:#[^)]+)?\)")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

PATH_TOPICS = {
    "README.md": ["开始", "阅读"],
    "book-downloads": ["工具", "阅读"],
    "part-0": ["开始", "阅读"],
    "part-1": ["学习", "英语"],
    "part-2": ["生活", "关系", "选择", "恢复"],
    "part-3": ["AI", "项目", "证据"],
    "part-4": ["实践", "家庭", "节律"],
    "part-5": ["行动", "长期", "复盘"],
    "part-6": ["自我", "成长", "长期"],
    "templates": ["工具", "模板"],
    "practice": ["实践", "项目"],
    "reference": ["索引", "方法"],
}

KEYWORD_TOPICS = {
    "关系": ["关系", "沟通", "同意", "边界", "伴侣", "家庭"],
    "恢复": ["恢复", "低谷", "失眠", "抑郁", "焦虑", "安全"],
    "选择": ["选择", "决定", "决策", "代价", "可逆"],
    "学习": ["学习", "英语", "练习", "能力", "复测"],
    "AI": ["AI", "模型", "提示词", "智能体"],
    "项目": ["项目", "交付", "作品", "用户", "创业"],
    "行动": ["行动", "任务", "九十天", "节律", "坚持"],
    "证据": ["证据", "基线", "验证", "反馈", "迁移"],
    "自我": ["自己", "自我", "羞耻", "价值", "成长"],
}


def plain(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_>#|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def readable(text: str) -> str:
    """Turn markdown into readable plain text while preserving paragraph boundaries."""
    text = re.sub(r"```(?:[^\n]*)\n([\s\S]*?)```", r"\n\1\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "• ", line)
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"[`*_#|]", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def clean_inline(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def document_blocks(text: str, title: str) -> list[dict]:
    """Preserve a document's heading and paragraph hierarchy for the reader UI."""
    text = re.sub(r"<!--([\s\S]*?)-->", "", text)
    text = re.sub(r"```[^\n]*\n([\s\S]*?)```", r"\n\1\n", text)
    blocks: list[dict] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            value = clean_inline(" ".join(paragraph))
            if value:
                blocks.append({"type": "paragraph", "text": value})
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append({"type": "list", "items": list_items.copy()})
            list_items.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            flush_paragraph()
            flush_list()
            heading = clean_inline(heading_match.group(2))
            if heading and not (len(heading_match.group(1)) == 1 and heading == title):
                blocks.append({"type": "heading", "level": min(len(heading_match.group(1)), 4), "text": heading})
            continue
        if not line:
            flush_paragraph()
            flush_list()
            continue
        list_match = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if list_match:
            flush_paragraph()
            item = clean_inline(list_match.group(1))
            if item:
                list_items.append(item)
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            flush_list()
            cells = [clean_inline(cell) for cell in line.strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                blocks.append({"type": "paragraph", "text": " · ".join(cell for cell in cells if cell)})
            continue
        flush_list()
        cleaned = clean_inline(re.sub(r"^>\s*", "", line))
        if cleaned:
            paragraph.append(cleaned)
    flush_paragraph()
    flush_list()
    return blocks


def stable_id(value: str) -> str:
    return hashlib.blake2s(value.encode("utf-8"), digest_size=5).hexdigest()


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    values: dict[str, str] = {}
    if not match:
        return values, text
    for line in match.group(1).splitlines():
        item = re.match(r"^([\w-]+):\s*[\"']?(.*?)[\"']?\s*$", line)
        if item:
            values[item.group(1)] = item.group(2)
    return values, text[match.end() :]


def topics_for(path: str, title: str, body: str) -> list[str]:
    topics: list[str] = []
    for marker, values in PATH_TOPICS.items():
        if marker in path:
            topics.extend(values)
    title_text = title.lower()
    body_text = body.lower()
    for topic, words in KEYWORD_TOPICS.items():
        title_match = any(word.lower() in title_text for word in words)
        body_score = sum(body_text.count(word.lower()) for word in words)
        if title_match or body_score >= 3:
            topics.append(topic)
    return list(dict.fromkeys(topics))[:6] or ["通用"]


def document(path: Path, relative: str) -> tuple[dict, dict]:
    raw = path.read_text(encoding="utf-8")
    meta, body = frontmatter(raw)
    matches = list(HEADING_RE.finditer(body))
    title = meta.get("title") or (plain(matches[0].group(2)) if matches else path.stem)
    chapter_topics = topics_for(relative, f"{title} {meta.get('description', '')}", "")
    chapter = {
        "title": title,
        "description": meta.get("description", ""),
        "updated": meta.get("updated", ""),
        "source": relative,
        "topics": chapter_topics,
    }
    full_content = readable(body)
    blocks = document_blocks(body, title)
    outline = [block["text"] for block in blocks if block["type"] == "heading"]
    entry = {
        "id": f"doc-{stable_id(relative)}",
        "library": "reflection",
        "chapter": title,
        "heading": title,
        "description": meta.get("description", ""),
        "content": plain(body),
        "fullContent": full_content,
        "blocks": blocks,
        "outline": outline,
        "wordCount": len(re.sub(r"\s+", "", full_content)),
        "source": relative,
        "updated": meta.get("updated", ""),
        "topics": chapter_topics,
    }
    return chapter, entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parents[1] / "web" / "knowledge.json")
    args = parser.parse_args()
    summary = (args.source / "SUMMARY.md").read_text(encoding="utf-8")
    sources = list(dict.fromkeys(LINK_RE.findall(summary)))
    chapters: list[dict] = []
    entries: list[dict] = []
    missing: list[str] = []
    for relative in sources:
        path = args.source / relative
        if not path.exists():
            missing.append(relative)
            continue
        chapter, entry = document(path, relative)
        chapters.append(chapter)
        entries.append(entry)
    payload = {
        "title": "人生进阶指南知识库",
        "source": "https://github.com/byoungd/up",
        "license": "CC BY-NC 4.0",
        "chapterCount": len(chapters),
        "documentCount": len(entries),
        "sectionCount": len(entries),
        "chapters": chapters,
        "sections": entries,
        "missing": missing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Indexed {len(entries)} complete documents -> {args.output}")


if __name__ == "__main__":
    main()
