from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]+|[\u3400-\u9fff]")


def tokens(text: str) -> list[str]:
    raw = TOKEN_RE.findall(text.lower())
    chinese = [token for token in raw if "\u3400" <= token <= "\u9fff"]
    latin = [token for token in raw if token not in chinese]
    bigrams = ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]
    return latin + chinese + bigrams


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
    def __init__(self, path: Path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.meta = {key: payload[key] for key in ("title", "source", "license", "chapterCount", "sectionCount")}
        self.sections = payload["sections"]
        self.vectors = [vectorize(f"{item['chapter']} {item['heading']} {item['content']} {' '.join(item['topics'])}") for item in self.sections]

    def search(self, query: str, topic: str | None = None, limit: int = 8) -> list[dict]:
        query_vector = vectorize(query)
        query_tokens = set(tokens(query))
        ranked: list[tuple[float, dict]] = []
        for item, item_vector in zip(self.sections, self.vectors, strict=True):
            if topic and topic != "全部" and topic not in item["topics"]:
                continue
            heading_tokens = set(tokens(f"{item['chapter']} {item['heading']}"))
            body_tokens = set(tokens(item["content"]))
            lexical = len(query_tokens & heading_tokens) * 0.12 + len(query_tokens & body_tokens) * 0.025
            topic_bonus = 0.12 if topic and topic in item["topics"] else 0
            score = cosine(query_vector, item_vector) * 0.72 + min(lexical, 0.5) + topic_bonus
            if score > 0.03:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [{**item, "score": round(score, 4)} for score, item in ranked[:limit]]
