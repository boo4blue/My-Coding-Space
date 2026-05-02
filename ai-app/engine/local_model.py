"""
Standalone local model engine using llama-cpp-python.
Loads a GGUF model file directly — no external server needed.
"""

import os
import sys
import threading
import asyncio
from pathlib import Path
from typing import Iterator


class LocalModel:
    def __init__(self, config: dict):
        self.model_path = Path(
            config.get("model_path", "models/model.gguf")
        ).expanduser()
        self.n_ctx       = config.get("n_ctx", 4096)
        self.n_threads   = config.get("n_threads", max(1, (os.cpu_count() or 4) - 1))
        self.n_gpu_layers = config.get("n_gpu_layers", 0)   # 0 = CPU only; -1 = all layers on GPU
        self.max_tokens  = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.7)
        self._llm = None
        self._load_error: str = ""

    # ── Loading ───────────────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        return self._llm is not None

    def model_exists(self) -> bool:
        return self.model_path.exists()

    def load(self) -> bool:
        if self._llm is not None:
            return True
        if not self.model_path.exists():
            self._load_error = f"Model file not found: {self.model_path}"
            return False
        try:
            from llama_cpp import Llama
            print(f"Loading model: {self.model_path.name} …", flush=True)
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
                chat_format="chatml",
            )
            print("Model loaded.", flush=True)
            return True
        except Exception as e:
            self._load_error = str(e)
            print(f"Model load failed: {e}", flush=True)
            return False

    # ── Synchronous streaming (used internally) ───────────────────────────────

    def _chat_stream_sync(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> Iterator[str]:
        if not self._llm:
            if not self.load():
                yield f"[Model not loaded: {self._load_error}. Run download_model.py to get a model.]"
                return

        msgs: list[dict] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        try:
            stream = self._llm.create_chat_completion(
                messages=msgs,
                stream=True,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.9,
                repeat_penalty=1.1,
            )
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
        except Exception as e:
            yield f"[Generation error: {e}]"

    # ── Async streaming (called from FastAPI WebSocket) ───────────────────────

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ):
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        def _worker():
            try:
                for chunk in self._chat_stream_sync(messages, system_prompt):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, f"[Error: {e}]")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    # ── One-shot generate (for simple prompts) ────────────────────────────────

    async def generate(self, prompt: str, system: str = "") -> str:
        result = ""
        async for chunk in self.chat_stream(
            [{"role": "user", "content": prompt}], system
        ):
            result += chunk
        return result

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "loaded": self.is_loaded(),
            "model_exists": self.model_exists(),
            "model_path": str(self.model_path),
            "model_name": self.model_path.name if self.model_exists() else None,
            "error": self._load_error or None,
            "n_ctx": self.n_ctx,
            "n_threads": self.n_threads,
            "n_gpu_layers": self.n_gpu_layers,
        }
