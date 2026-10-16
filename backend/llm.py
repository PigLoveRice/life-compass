from __future__ import annotations

import os
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

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


def public_model_config() -> dict:
    return {
        "configured": configured(),
        "base_url": os.getenv("LIFE_COMPASS_LLM_BASE_URL", "https://api.openai.com/v1"),
        "model": model_name(),
        "source": "server" if configured() else "local",
    }


def validate_custom_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("模型地址必须是完整的 HTTP 或 HTTPS 地址")
    if parsed.username or parsed.password:
        raise ValueError("模型地址不能包含用户名或密码")
    if os.getenv("LIFE_COMPASS_ALLOW_PRIVATE_MODEL_HOSTS") == "1":
        return base_url.rstrip("/")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("无法解析模型服务地址") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("默认不允许访问本机或内网模型地址；仅本地可信部署可启用 LIFE_COMPASS_ALLOW_PRIVATE_MODEL_HOSTS=1")
    return base_url.rstrip("/")


def resolve_config(override: dict | None = None) -> tuple[str, str, str] | None:
    if override:
        return validate_custom_base_url(str(override["base_url"])), override["api_key"], override["model"]
    api_key = os.getenv("LIFE_COMPASS_LLM_API_KEY")
    if not api_key:
        return None
    return os.getenv("LIFE_COMPASS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"), api_key, model_name()


async def test_connection(override: dict) -> LLMResult:
    try:
        base_url, api_key, selected_model = resolve_config(override) or ("", "", "")
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": selected_model, "messages": [{"role": "user", "content": "只回复 OK"}], "temperature": 0, "max_tokens": 8},
            )
            response.raise_for_status()
            response.json()["choices"][0]["message"]["content"]
            return LLMResult(content="连接成功", provider=selected_model)
    except ValueError as exc:
        return LLMResult(content="", provider=override.get("model", "custom"), warning=str(exc))
    except httpx.HTTPStatusError as exc:
        return LLMResult(content="", provider=override.get("model", "custom"), warning=f"模型服务返回 HTTP {exc.response.status_code}")
    except httpx.RequestError:
        return LLMResult(content="", provider=override.get("model", "custom"), warning="无法连接模型服务")
    except Exception as exc:
        return LLMResult(content="", provider=override.get("model", "custom"), warning=f"模型响应格式不兼容：{type(exc).__name__}")


async def complete(messages: list[dict], references: list[dict], memories: list[dict], override: dict | None = None) -> LLMResult | None:
    config = resolve_config(override)
    if not config:
        return None
    base_url, api_key, selected_model = config
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
                json={"model": selected_model, "messages": prompt_messages, "temperature": 0.35},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            return LLMResult(content=content, provider=selected_model)
    except Exception as exc:
        return LLMResult(content="", provider="local", warning=f"模型服务暂不可用，已切换本地教练：{type(exc).__name__}")
