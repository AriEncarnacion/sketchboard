"""Thin client for Gemma via Ollama's OpenAI-compatible endpoint."""

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config


def image_part(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    """An OpenAI-style image_url content part holding the image inline."""
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


@dataclass
class Reply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class Gemma:
    def __init__(self, base_url: str = config.OLLAMA_URL, model: str = config.MODEL):
        self.base_url = base_url
        self.model = model
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT_S, connect=10))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def alive(self) -> bool:
        try:
            r = await self._http.get(f"{self.base_url}/api/version", timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def has_model(self) -> bool:
        try:
            r = await self._http.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            names = {m["name"] for m in r.json().get("models", [])}
            return self.model in names or f"{self.model}:latest" in names
        except (httpx.HTTPError, KeyError, ValueError):
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = config.MAX_TOKENS,
        temperature: float = 0.4,
        reasoning: str = config.REASONING,
    ) -> Reply:
        body = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # Gemma 4 thinks by default and will spend the whole token budget on it.
            # Ollama's OpenAI endpoint ignores `think` but honours reasoning_effort.
            "reasoning_effort": reasoning,
        }
        t0 = time.monotonic()
        r = await self._http.post(f"{self.base_url}/v1/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        return Reply(
            text=data["choices"][0]["message"]["content"] or "",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            seconds=time.monotonic() - t0,
            raw=data,
        )
