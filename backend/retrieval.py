from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]+|[\u3400-\u9fff]")
SYNONYMS = {
    "辞职": "离职 失业 工作 收入",
    "摔跤": "摔倒 跌倒",
    "摔了": "摔倒 跌倒",
    "没钱": "失业 低保 救助 收入",
    "睡不好": "失眠 睡眠",
    "被骗": "诈骗 报警 证据",
    "看医生": "医院 看病 就医",
}


def tokens(text: str) -> list[str]:
    additions = " ".join(value for key, value in SYNONYMS.items() if key in text)
    text = f"{text} {additions}"
    raw = TOKEN_RE.findall(text.lower())
    chinese = [token for token in raw if "\u3400" <= token <= "\u9fff"]
    latin = [token for token in raw if token not in chinese]
    bigrams = ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]
    return latin + bigrams + (chinese if len(chinese) == 1 else [])


def vectorize(text: str, dimensions: int = 384) -> dict[int, float]:
    counts = Counter(tokens(text))
    vector: dict[int, float] = {}
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest, "big") % dimensions
        sign = 1 if digest[0] & 1 else -1
        vector[index] = vector.get(index, 0.0) + sign * (1 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector.values())) or 1
    return {index: value / norm for index, value in vector.items()}


def cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(index, 0) for index, value in left.items())


class KnowledgeIndex:
    def __init__(self, path: Path, library: str = "reflection"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.library = library
        self.meta = {key: payload.get(key) for key in ("title", "source", "license", "revision", "chapterCount", "documentCount", "moduleCount", "itemCount", "sectionCount") if payload.get(key) is not None}
        self.sections = [{**item, "library": item.get("library", library)} for item in payload["sections"]]
        self.vectors = [vectorize(self.searchable(item)) for item in self.sections]
        self.nested_vectors = [
            [vectorize(self.nested_searchable(entry)) for entry in item.get("items", [])]
            for item in self.sections
        ]

    @staticmethod
    def searchable(item: dict) -> str:
        base = " ".join(str(value) for value in (
            item.get("chapter", ""), item.get("heading", ""), item.get("summary", ""),
            item.get("content", ""), item.get("note", ""), " ".join(item.get("topics", [])),
        ))
        nested = " ".join(
            " ".join(str(entry.get(key, "")) for key in ("heading", "summary", "topics"))
            for entry in item.get("items", [])
        )
        return f"{base} {nested}"

    @staticmethod
    def nested_searchable(item: dict) -> str:
        return " ".join(str(value) for value in (
            item.get("heading", ""), item.get("summary", ""), item.get("note", ""),
            " ".join(item.get("topics", [])),
        ))

    def search(self, query: str, topic: str | None = None, limit: int = 8) -> list[dict]:
        query_vector = vectorize(query)
        query_tokens = set(tokens(query))
        ranked: list[tuple[float, dict, list[str]]] = []
        for item, item_vector, nested_vectors in zip(self.sections, self.vectors, self.nested_vectors, strict=True):
            if topic and topic != "全部" and topic not in item["topics"]:
                continue
            heading_tokens = set(tokens(f"{item['chapter']} {item['heading']}"))
            body_tokens = set(tokens(self.searchable(item)))
            lexical = len(query_tokens & heading_tokens) * 0.16 + len(query_tokens & body_tokens) * 0.04
            topic_bonus = 0.12 if topic and topic in item["topics"] else 0
            action_bonus = 0.04 if self.library == "action" and item.get("evidence") == "A" else 0
            score = cosine(query_vector, item_vector) * 0.72 + min(lexical, 0.5) + topic_bonus + action_bonus
            nested_scores: list[tuple[float, str]] = []
            for entry, entry_vector in zip(item.get("items", []), nested_vectors, strict=True):
                entry_heading_tokens = set(tokens(entry.get("heading", "")))
                entry_body_tokens = set(tokens(self.nested_searchable(entry)))
                entry_lexical = len(query_tokens & entry_heading_tokens) * 0.16 + len(query_tokens & entry_body_tokens) * 0.04
                entry_bonus = 0.04 if entry.get("evidence") == "A" and entry.get("ratio") in {"极高", "高"} else 0
                nested_scores.append((cosine(query_vector, entry_vector) * 0.72 + min(entry_lexical, 0.5) + entry_bonus, entry["id"]))
            nested_scores.sort(reverse=True)
            if nested_scores:
                score = max(score, nested_scores[0][0] + topic_bonus)
            if score > 0.03:
                ranked.append((score, item, [entry_id for _, entry_id in nested_scores[:3]]))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        results: list[dict] = []
        for score, item, matched_ids in ranked[:limit]:
            public_item = {key: value for key, value in item.items() if key not in {"blocks", "fullContent"}}
            public_item["content"] = public_item.get("content", "")[:4000]
            results.append({**public_item, "matchedItemIds": matched_ids, "score": round(score, 4)})
        return results
