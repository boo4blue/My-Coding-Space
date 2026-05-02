import asyncio
import json
import os
import re
import sys
import shutil
import webbrowser
from pathlib import Path

import aiofiles
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine.ollama_client import OllamaClient
from engine.tools import ToolEngine
from engine.knowledge import KnowledgeBase
from engine.memory import ConversationMemory

# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg_path = ROOT / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    (ROOT / "config.json").write_text(json.dumps(cfg, indent=2))


CONFIG = load_config()
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SESSIONS_DIR = DATA_DIR / "sessions"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"

for d in [UPLOADS_DIR, SESSIONS_DIR, KNOWLEDGE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Singletons ────────────────────────────────────────────────────────────────

ollama = OllamaClient(CONFIG.get("ollama_url", "http://localhost:11434"))
kb = KnowledgeBase(str(KNOWLEDGE_DIR))
memory = ConversationMemory(str(SESSIONS_DIR), CONFIG.get("max_history", 50))
tools = ToolEngine(CONFIG, kb)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="ARIA — Local AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
async def status():
    alive = await ollama.is_running()
    models = await ollama.list_models() if alive else []
    return {
        "ollama": alive,
        "models": models,
        "current_model": CONFIG.get("default_model", "llama3.2"),
        "ai_name": CONFIG.get("ai_name", "ARIA"),
    }


@app.get("/api/sessions")
async def list_sessions():
    return memory.list_sessions()


@app.post("/api/session/new")
async def new_session():
    sid = memory.new_session()
    return {"session_id": sid}


@app.get("/api/session/{session_id}")
async def load_session(session_id: str):
    ok = memory.load_session(session_id)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"session_id": session_id, "messages": memory.get_history()}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    memory.delete_session(session_id)
    return {"ok": True}


@app.get("/api/knowledge")
async def knowledge_docs():
    return kb.list_documents()


@app.delete("/api/knowledge/{source}")
async def remove_knowledge(source: str):
    kb.remove_document(source)
    return {"ok": True}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), add_to_kb: str = Form("false")):
    dest = UPLOADS_DIR / file.filename
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    result: dict = {"filename": file.filename, "path": str(dest)}

    if add_to_kb.lower() == "true":
        kb_result = kb.add_file(str(dest))
        result["knowledge"] = kb_result

    return result


@app.get("/api/config")
async def get_config():
    return CONFIG


@app.post("/api/config")
async def update_config(data: dict):
    CONFIG.update(data)
    save_config(CONFIG)
    # Reload memory max_history
    memory.max_history = CONFIG.get("max_history", 50)
    return CONFIG


# ── WebSocket Chat ────────────────────────────────────────────────────────────

TOOL_CALL_RE = re.compile(r"TOOL_CALL:\s*(\{.*?\})", re.DOTALL)


def build_system_prompt() -> str:
    name = CONFIG.get("ai_name", "ARIA")
    personality = CONFIG.get("ai_personality", "You are a helpful AI assistant.")
    tool_docs = tools.get_tool_descriptions()

    kb_docs = kb.list_documents()
    kb_note = ""
    if kb_docs:
        sources = ", ".join(d["source"] for d in kb_docs[:10])
        kb_note = f"\n\nYou have a knowledge base with these documents: {sources}. Use search_knowledge_base to look things up from them."

    return f"""{personality}

Your name is {name}. You are running locally on the user's PC.

{tool_docs}{kb_note}

Respond naturally and helpfully. When you need information or need to take action, use the tools. Be proactive — if the user asks you to find something, search for it. If they ask you to open something, open it. If they ask you to write code, write it and save it to a file."""


async def process_with_tools(ws: WebSocket, user_message: str, model: str):
    history = memory.get_history()
    history.append({"role": "user", "content": user_message})
    system = build_system_prompt()

    full_response = ""
    iteration = 0
    max_iterations = 8

    while iteration < max_iterations:
        iteration += 1
        buffer = ""
        tool_calls_made = []

        # Stream from Ollama
        await ws.send_json({"type": "start"})

        async for chunk in ollama.chat_stream(history, model, system):
            buffer += chunk
            full_response += chunk

            # Check for tool call marker in buffer
            if "TOOL_CALL:" in buffer:
                # Send text up to the TOOL_CALL
                pre = buffer[: buffer.index("TOOL_CALL:")]
                if pre:
                    await ws.send_json({"type": "chunk", "text": pre})

                # Wait for complete JSON — check if we have a complete object
                rest = buffer[buffer.index("TOOL_CALL:"):]
                match = TOOL_CALL_RE.search(rest)
                if match:
                    # Send tool_call notification
                    try:
                        call_data = json.loads(match.group(1))
                        tool_name = call_data.get("name", "")
                        tool_args = call_data.get("args", {})
                        await ws.send_json({
                            "type": "tool_call",
                            "name": tool_name,
                            "args": tool_args,
                        })
                        tool_calls_made.append((tool_name, tool_args))
                    except json.JSONDecodeError:
                        pass
                    # Clear buffer after the match
                    buffer = rest[match.end():]
                # If no complete JSON yet, keep accumulating
                continue

            # Send non-tool text chunks in real time
            # Only send if we don't have a partial TOOL_CALL in buffer
            if "TOOL_CALL:" not in buffer:
                await ws.send_json({"type": "chunk", "text": chunk})
                buffer = ""

        # Send any remaining buffer text
        if buffer and "TOOL_CALL:" not in buffer:
            await ws.send_json({"type": "chunk", "text": buffer})

        # Execute tool calls if any
        if tool_calls_made:
            tool_results = []
            for name, args in tool_calls_made:
                await ws.send_json({"type": "tool_running", "name": name})
                result = await tools.call(name, args)
                await ws.send_json({
                    "type": "tool_result",
                    "name": name,
                    "result": result[:2000],
                })
                tool_results.append(
                    f"TOOL_RESULT ({name}): {result[:3000]}"
                )

            # Inject tool results and continue
            history.append({"role": "assistant", "content": full_response})
            history.append({
                "role": "user",
                "content": "\n".join(tool_results) + "\n\nContinue your response based on these results.",
            })
            full_response = ""
        else:
            # No tool calls — done
            break

    # Save final exchange to memory
    memory.add("user", user_message)
    memory.add("assistant", full_response)
    await ws.send_json({"type": "done", "full": full_response})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "chat")

            if msg_type == "chat":
                user_text = msg.get("text", "").strip()
                model = msg.get("model", CONFIG.get("default_model", "llama3.2"))
                if not user_text:
                    continue

                alive = await ollama.is_running()
                if not alive:
                    await ws.send_json({
                        "type": "error",
                        "text": "Ollama is not running. Start it with: ollama serve",
                    })
                    continue

                await process_with_tools(ws, user_text, model)

            elif msg_type == "new_session":
                sid = memory.new_session()
                await ws.send_json({"type": "session_created", "session_id": sid})

            elif msg_type == "load_session":
                sid = msg.get("session_id", "")
                ok = memory.load_session(sid)
                history = memory.get_history() if ok else []
                await ws.send_json({
                    "type": "session_loaded",
                    "session_id": sid,
                    "messages": history,
                    "ok": ok,
                })

            elif msg_type == "clear":
                memory.clear()
                await ws.send_json({"type": "cleared"})

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = CONFIG.get("port", 7860)
    print(f"\n{'='*50}")
    print(f"  ARIA — Local AI")
    print(f"  http://localhost:{port}")
    print(f"{'='*50}\n")
    if CONFIG.get("auto_open_browser", True):
        import threading
        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False, log_level="warning")
