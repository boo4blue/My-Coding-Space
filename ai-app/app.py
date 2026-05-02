import asyncio
import json
import os
import re
import sys
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

from engine.local_model import LocalModel
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
DATA_DIR   = ROOT / "data"
UPLOADS_DIR  = DATA_DIR / "uploads"
SESSIONS_DIR = DATA_DIR / "sessions"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
MODELS_DIR = ROOT / "models"

for d in [UPLOADS_DIR, SESSIONS_DIR, KNOWLEDGE_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Singletons ────────────────────────────────────────────────────────────────

model   = LocalModel(CONFIG)
kb      = KnowledgeBase(str(KNOWLEDGE_DIR))
memory  = ConversationMemory(str(SESSIONS_DIR), CONFIG.get("max_history", 50))
tools   = ToolEngine(CONFIG, kb)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="ARIA — Local AI")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
async def status():
    m_status = model.status()
    # List gguf files in models dir so user can switch
    model_files = [f.name for f in MODELS_DIR.glob("*.gguf")]
    return {
        "ready":       m_status["loaded"],
        "model_exists": m_status["model_exists"],
        "model_name":  m_status["model_name"],
        "model_path":  m_status["model_path"],
        "model_files": model_files,
        "error":       m_status["error"],
        "ai_name":     CONFIG.get("ai_name", "ARIA"),
    }


@app.post("/api/load_model")
async def load_model_endpoint():
    ok = await asyncio.to_thread(model.load)
    return {"ok": ok, "error": model._load_error or None}


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
    memory.max_history = CONFIG.get("max_history", 50)
    # Reload model if path changed
    new_path = Path(CONFIG.get("model_path", "")).expanduser()
    if new_path != model.model_path:
        model.model_path = new_path
        model._llm = None
        model._load_error = ""
    return CONFIG


# ── WebSocket Chat ────────────────────────────────────────────────────────────

TOOL_CALL_RE = re.compile(r"TOOL_CALL:\s*(\{.*?\})", re.DOTALL)


def build_system_prompt() -> str:
    name        = CONFIG.get("ai_name", "ARIA")
    personality = CONFIG.get("ai_personality", "You are a helpful AI assistant.")
    tool_docs   = tools.get_tool_descriptions()

    kb_docs = kb.list_documents()
    kb_note = ""
    if kb_docs:
        sources = ", ".join(d["source"] for d in kb_docs[:10])
        kb_note = (
            f"\n\nYou have a knowledge base with these documents: {sources}. "
            "Use search_knowledge_base to look things up from them."
        )

    return (
        f"{personality}\n\nYour name is {name}. "
        "You are running locally on the user's PC — completely standalone, no internet required for thinking.\n\n"
        f"{tool_docs}{kb_note}\n\n"
        "Respond naturally and helpfully. Use tools proactively when needed."
    )


async def process_with_tools(ws: WebSocket, user_message: str):
    history = memory.get_history()
    history.append({"role": "user", "content": user_message})
    system = build_system_prompt()

    full_response = ""
    iteration     = 0
    max_iterations = 8

    while iteration < max_iterations:
        iteration += 1
        buffer = ""
        tool_calls_made = []

        await ws.send_json({"type": "start"})

        async for chunk in model.chat_stream(history, system):
            buffer += chunk
            full_response += chunk

            if "TOOL_CALL:" in buffer:
                pre = buffer[: buffer.index("TOOL_CALL:")]
                if pre:
                    await ws.send_json({"type": "chunk", "text": pre})

                rest  = buffer[buffer.index("TOOL_CALL:"):]
                match = TOOL_CALL_RE.search(rest)
                if match:
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
                    buffer = rest[match.end():]
                continue

            if "TOOL_CALL:" not in buffer:
                await ws.send_json({"type": "chunk", "text": chunk})
                buffer = ""

        if buffer and "TOOL_CALL:" not in buffer:
            await ws.send_json({"type": "chunk", "text": buffer})

        if tool_calls_made:
            tool_results = []
            for name, args in tool_calls_made:
                await ws.send_json({"type": "tool_running", "name": name})
                result = await tools.call(name, args)
                await ws.send_json({"type": "tool_result", "name": name, "result": result[:2000]})
                tool_results.append(f"TOOL_RESULT ({name}): {result[:3000]}")

            history.append({"role": "assistant", "content": full_response})
            history.append({
                "role": "user",
                "content": "\n".join(tool_results) + "\n\nContinue your response based on these results.",
            })
            full_response = ""
        else:
            break

    memory.add("user", user_message)
    memory.add("assistant", full_response)
    await ws.send_json({"type": "done", "full": full_response})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    # Pre-load the model in the background when a client connects
    if not model.is_loaded() and model.model_exists():
        asyncio.create_task(asyncio.to_thread(model.load))

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
                if not user_text:
                    continue

                if not model.model_exists():
                    await ws.send_json({
                        "type": "error",
                        "text": (
                            "No model file found. "
                            "Run: python download_model.py  to download one, "
                            f"then place the .gguf file in: {MODELS_DIR}"
                        ),
                    })
                    continue

                if not model.is_loaded():
                    await ws.send_json({"type": "status", "text": "Loading model into memory… (first message takes 5–30s)"})
                    ok = await asyncio.to_thread(model.load)
                    if not ok:
                        await ws.send_json({"type": "error", "text": f"Failed to load model: {model._load_error}"})
                        continue

                await process_with_tools(ws, user_text)

            elif msg_type == "new_session":
                sid = memory.new_session()
                await ws.send_json({"type": "session_created", "session_id": sid})

            elif msg_type == "load_session":
                sid = msg.get("session_id", "")
                ok  = memory.load_session(sid)
                await ws.send_json({
                    "type": "session_loaded",
                    "session_id": sid,
                    "messages": memory.get_history() if ok else [],
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
    print(f"  ARIA — Standalone Local AI")
    print(f"  http://localhost:{port}")
    print(f"{'='*50}\n")
    if CONFIG.get("auto_open_browser", True):
        import threading, time
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(f"http://localhost:{port}")),
            daemon=True,
        ).start()
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False, log_level="warning")
