from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


SYSTEM_PROMPT = """你是“人生罗盘”的反思教练，不是权威人生导师。
原则：
1. 先区分事实、解释、价值偏好与未知项，不补写用户经历。
2. 不替用户决定；至少保留暂不行动这个选项。
3. 优先提出小、可逆、符合当前容量的实验，并写明证据、复查日期和停止条件。
4. 引用资料时使用 [1]、[2] 标记，只能引用提供的资料。
5. 不以执行力评价人格，不把一次结果写成稳定能力。
6. 涉及医疗、心理、暴力、法律、债务或紧迫安全风险时，停止普通建议，建议联系可信任的人和当地合格专业支持。
7. 回复简洁、温和、具体，结尾提出一个问题，而不是一次给出完整人生方案。"""


@dataclass
class LLMResult:
    content: str
    provider: str
    warning: str = ""


def configured() -> bool:
    return bool(os.getenv("LIFE_COMPASS_LLM_API_KEY"))


def model_name() -> str:
    return os.getenv("LIFE_COMPASS_LLM_MODEL", "gpt-4.1-mini")


async def complete(messages: list[dict], references: list[dict], memories: list[dict]) -> LLMResult | None:
    api_key = os.getenv("LIFE_COMPASS_LLM_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("LIFE_COMPASS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    reference_text = "\n\n".join(
        f"[{index}] {item['chapter']} / {item['heading']}\n{item['content'][:1000]}"
        for index, item in enumerate(references, 1)
    )
    memory_text = "\n".join(f"- {item['kind']}: {item['content']}" for item in memories) or "无"
    prompt_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"用户主动保存的长期记忆：\n{memory_text}\n\n可引用资料：\n{reference_text}"},
        *[{"role": item["role"], "content": item["content"]} for item in messages[-12:]],
    ]
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_name(), "messages": prompt_messages, "temperature": 0.35},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            return LLMResult(content=content, provider=model_name())
    except Exception as exc:
        return LLMResult(content="", provider="local", warning=f"模型服务暂不可用，已切换本地教练：{type(exc).__name__}")
