"""
ARIA Desktop Launcher
Starts the FastAPI server then opens a native desktop window (no browser needed).
"""

import json
import sys
import time
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent


def load_config() -> dict:
    try:
        return json.loads((ROOT / "config.json").read_text())
    except Exception:
        return {}


def start_server(port: int):
    import uvicorn
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


def wait_for_server(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main():
    cfg  = load_config()
    port = cfg.get("port", 7860)
    name = cfg.get("ai_name", "ARIA")

    # Start server in daemon thread
    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()

    print(f"Starting {name}…", flush=True)

    if not wait_for_server(port):
        print("Server did not start in time.", flush=True)
        sys.exit(1)

    print(f"Server ready on port {port}", flush=True)

    # ── Try pywebview (native desktop window) ─────────────────────────────
    try:
        import webview

        window = webview.create_window(
            title=f"{name} — Local AI",
            url=f"http://127.0.0.1:{port}",
            width=1280,
            height=820,
            min_size=(900, 600),
            background_color="#08080f",
            text_select=True,
        )

        # Keep server alive while window open
        webview.start(debug=False)

    except ImportError:
        # Fallback: open in default browser
        import webbrowser
        print("pywebview not installed — opening in browser.", flush=True)
        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            t.join()          # keep alive until Ctrl+C
        except KeyboardInterrupt:
            pass

    except Exception as e:
        import webbrowser
        print(f"Window error ({e}) — opening in browser.", flush=True)
        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            t.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
