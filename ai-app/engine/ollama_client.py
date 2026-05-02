import httpx
import json
import asyncio
from typing import AsyncIterator, Optional


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=120.0)

    async def is_running(self) -> bool:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": 8192},
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with self._client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300.0,
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

    async def generate(self, prompt: str, model: str, system: str = "") -> str:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        try:
            r = await self._client.post(
                f"{self.base_url}/api/generate", json=payload, timeout=120.0
            )
            return r.json().get("response", "")
        except Exception as e:
            return f"[Error: {e}]"

    async def embed(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        try:
            r = await self._client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30.0,
            )
            return r.json().get("embedding", [])
        except Exception:
            return []

    async def close(self):
        await self._client.aclose()
