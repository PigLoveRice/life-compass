#!/usr/bin/env python3
"""Build a searchable action index from eternity4719/HowToLiveBetter."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ENTRY_RE = re.compile(r"^###\s+(\d+)\.\s*(.+?)\s*$")
FIELD_RE = re.compile(r"^-\s*(成本|说人话|收益|证据等级|来源|备注)：\s*(.*)$")
TAG_RE = re.compile(r"<!--\s*成本标签:\s*(.*?)\s*-->")

TOPIC_WORDS = {
    "健康": ["健康", "看病", "药", "病", "睡眠", "运动", "体检", "疫苗"],
    "安全": ["安全", "急救", "火灾", "事故", "报警", "危险", "自杀"],
    "金钱": ["钱", "理财", "保险", "贷款", "借款", "诈骗", "买房"],
    "工作": ["工作", "上班", "离职", "工伤", "创业", "公司", "技能"],
    "关系": ["恋爱", "结婚", "伴侣", "孩子", "老人", "家庭", "关系"],
    "法律": ["法律", "违法", "犯罪", "合同", "证据", "起诉", "报警"],
    "数字": ["账号", "密码", "手机", "网站", "信息安全", "网络"],
    "恢复": ["打击", "失业", "没钱", "压力", "抑郁", "焦虑", "放松"],
}


def clean(value: str) -> str:
    value = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[*_`]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def cost_tags(raw: str) -> dict[str, str]:
    return dict(re.findall(r"(钱|时间|毅力|收益|口径)=(\S+)", raw or ""))


def ratio(tags: dict[str, str]) -> str:
    weights = {"钱": {"0": 0, "少": 1, "多": 2}, "时间": {"少": 0, "中": 1, "多": 2}, "毅力": {"否": 0, "些": 1, "是": 2}}
    try:
        total = sum(weights[key][tags[key]] for key in ("钱", "时间", "毅力"))
    except KeyError:
        return "未分级"
    if tags.get("收益") == "大":
        return "极高" if total == 0 else ("高" if total <= 2 else "一般")
    if tags.get("收益") == "中" and total == 0:
        return "高"
    return "一般"


def topics_for(text: str) -> list[str]:
    return [topic for topic, words in TOPIC_WORDS.items() if any(word in text for word in words)][:5] or ["生活"]


def revision(repo: Path) -> str:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def parse_book(path: Path, chapter_number: int) -> tuple[dict, list[dict]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    chapter_title = next((clean(line[2:]) for line in lines if line.startswith("# ")), path.stem)
    entries: list[dict] = []
    current: dict | None = None
    last_field: str | None = None
    for line in lines:
        match = ENTRY_RE.match(line)
        if match:
            if current:
                entries.append(current)
            current = {"number": int(match.group(1)), "heading": clean(match.group(2)), "fields": {}, "tags_raw": ""}
            last_field = None
            continue
        if current is None:
            continue
        tag_match = TAG_RE.search(line)
        if tag_match:
            current["tags_raw"] = tag_match.group(1)
            continue
        field_match = FIELD_RE.match(line)
        if field_match:
            last_field = field_match.group(1)
            current["fields"][last_field] = clean(field_match.group(2))
            continue
        if not line.strip():
            last_field = None
        elif last_field:
            current["fields"][last_field] += " " + clean(line)
    if current:
        entries.append(current)

    output: list[dict] = []
    for item in entries:
        fields = item["fields"]
        tags = cost_tags(item["tags_raw"])
        context = " ".join([chapter_title, item["heading"], fields.get("说人话", ""), fields.get("备注", "")])
        output.append({
            "id": f"action-{chapter_number}-{item['number']}",
            "library": "action",
            "chapter": chapter_title,
            "number": item["number"],
            "heading": item["heading"],
            "summary": fields.get("说人话", ""),
            "content": " ".join(filter(None, [fields.get("说人话"), fields.get("成本"), fields.get("收益")]))[:3200],
            "cost": fields.get("成本", ""),
            "benefit": fields.get("收益", ""),
            "note": fields.get("备注", ""),
            "evidence": fields.get("证据等级", "未分级"),
            "sources": fields.get("来源", ""),
            "cost_tags": tags,
            "ratio": ratio(tags),
            "source": f"book/{path.name}#第-{item['number']}-条",
            "topics": topics_for(context),
        })
    return {"title": chapter_title, "source": f"book/{path.name}", "topics": topics_for(chapter_title)}, output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parents[1] / "web" / "action-knowledge.json")
    args = parser.parse_args()
    books = sorted((args.source / "book").glob("[0-9][0-9]-*.md"))
    if not books:
        raise SystemExit(f"No book/NN-*.md files found under {args.source}")
    chapters: list[dict] = []
    entries: list[dict] = []
    for path in books:
        chapter, items = parse_book(path, int(path.name[:2]))
        chapters.append(chapter)
        entries.extend(items)
    payload = {
        "title": "高性价比人生指南行动库",
        "source": "https://github.com/eternity4719/HowToLiveBetter",
        "license": "CC BY 4.0",
        "revision": revision(args.source),
        "chapterCount": len(chapters),
        "sectionCount": len(entries),
        "chapters": chapters,
        "sections": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Indexed {len(chapters)} chapters and {len(entries)} actions -> {args.output}")


if __name__ == "__main__":
    main()
