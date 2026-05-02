import os
import re
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DANGEROUS_COMMANDS = [
    r"\brm\s+-rf\s+/",
    r"\bdd\b",
    r"\bmkfs\b",
    r">\s*/dev/sd",
    r"\bformat\b.*\bC:",
    r":\(\)\{.*\}",  # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+0\b",
]


def _safe_path(path_str: str, allowed_paths: list[str] = None) -> Path:
    path = Path(path_str).expanduser().resolve()
    if allowed_paths:
        allowed = [Path(p).expanduser().resolve() for p in allowed_paths]
        if not any(
            str(path).startswith(str(a)) for a in allowed
        ):
            raise PermissionError(
                f"Access denied: {path} is outside allowed paths."
            )
    return path


class ToolEngine:
    def __init__(self, config: dict, knowledge_base=None):
        self.config = config
        self.kb = knowledge_base
        self.workspace = Path(
            config.get("workspace_path", "~/Desktop")
        ).expanduser()
        self.allowed_paths = config.get(
            "allowed_paths",
            ["~", "/tmp", "~/Desktop", "~/Documents", "~/Downloads"],
        )
        self.enable_shell = config.get("enable_shell", True)
        self.shell_confirm_dangerous = config.get("shell_confirm_dangerous", True)

        self._tools = {
            "web_search": self.web_search,
            "get_webpage": self.get_webpage,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_files": self.list_files,
            "delete_file": self.delete_file,
            "download_file": self.download_file,
            "open_app": self.open_app,
            "run_command": self.run_command,
            "search_knowledge_base": self.search_knowledge_base,
            "add_to_knowledge": self.add_to_knowledge,
            "get_system_info": self.get_system_info,
            "screenshot": self.screenshot,
        }

    def get_tool_descriptions(self) -> str:
        return """You have access to powerful tools. To use a tool, output EXACTLY this on its own line (no extra text around it):
TOOL_CALL: {"name": "tool_name", "args": {"key": "value"}}

Available tools:
- web_search(query) — Search DuckDuckGo for information
- get_webpage(url) — Fetch and read a webpage's text content
- read_file(path) — Read a file's contents
- write_file(path, content) — Write content to a file (creates directories if needed)
- list_files(path) — List files in a directory
- delete_file(path) — Delete a file or empty directory
- download_file(url, save_path) — Download a file from the internet
- open_app(app_name) — Open an application on the PC (e.g. "firefox", "vscode", "terminal")
- run_command(command) — Run a shell command and return output
- search_knowledge_base(query) — Search documents you've been taught
- add_to_knowledge(text, source) — Add text to your knowledge base
- get_system_info() — Get OS, hardware, running processes info
- screenshot() — Take a screenshot and save it

After you call a tool I will provide the result in a TOOL_RESULT block. Keep your response going naturally after the result.
You can call multiple tools. Think step-by-step."""

    async def call(self, name: str, args: dict) -> str:
        fn = self._tools.get(name)
        if not fn:
            return f"[Unknown tool: {name}]"
        try:
            result = fn(**args)
            if hasattr(result, "__await__"):
                result = await result
            return str(result)
        except Exception as e:
            return f"[Tool error: {e}]"

    # ── Web ──────────────────────────────────────────────────────────────────

    def web_search(self, query: str) -> str:
        try:
            import requests
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
            }
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            results = []
            for r in soup.select(".result__body")[:8]:
                title_el = r.select_one(".result__title")
                snippet_el = r.select_one(".result__snippet")
                url_el = r.select_one(".result__url")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                link = url_el.get_text(strip=True) if url_el else ""
                if title or snippet:
                    results.append(f"**{title}**\n{snippet}\n{link}")

            if not results:
                return "No results found."
            return "\n\n".join(results[:6])
        except Exception as e:
            return f"[Search failed: {e}]"

    def get_webpage(self, url: str) -> str:
        try:
            import requests
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Collapse blank lines
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            text = "\n".join(lines)
            return text[:8000] + ("\n...[truncated]" if len(text) > 8000 else "")
        except Exception as e:
            return f"[Webpage fetch failed: {e}]"

    # ── File system ──────────────────────────────────────────────────────────

    def read_file(self, path: str) -> str:
        try:
            p = _safe_path(path, self.allowed_paths)
            if not p.exists():
                return f"[File not found: {path}]"
            if p.is_dir():
                return self.list_files(path)
            text = p.read_text(errors="replace")
            if len(text) > 20000:
                text = text[:20000] + "\n...[truncated]"
            return text
        except PermissionError as e:
            return f"[{e}]"

    def write_file(self, path: str, content: str) -> str:
        try:
            p = _safe_path(path, self.allowed_paths)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"File written: {p} ({len(content)} chars)"
        except PermissionError as e:
            return f"[{e}]"
        except Exception as e:
            return f"[Write failed: {e}]"

    def list_files(self, path: str = ".") -> str:
        try:
            p = _safe_path(path, self.allowed_paths)
            if not p.exists():
                return f"[Path not found: {path}]"
            entries = []
            for item in sorted(p.iterdir()):
                size = ""
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                        size = f" ({self._human_size(sz)})"
                    except Exception:
                        pass
                icon = "d" if item.is_dir() else "f"
                entries.append(f"[{icon}] {item.name}{size}")
            return f"{p}/\n" + "\n".join(entries) if entries else f"{p}/ (empty)"
        except PermissionError as e:
            return f"[{e}]"

    def delete_file(self, path: str) -> str:
        try:
            p = _safe_path(path, self.allowed_paths)
            if not p.exists():
                return f"[Not found: {path}]"
            if p.is_dir():
                p.rmdir()
                return f"Directory removed: {p}"
            else:
                p.unlink()
                return f"File deleted: {p}"
        except PermissionError as e:
            return f"[{e}]"
        except Exception as e:
            return f"[Delete failed: {e}]"

    def download_file(self, url: str, save_path: str) -> str:
        try:
            p = _safe_path(save_path, self.allowed_paths)
            p.parent.mkdir(parents=True, exist_ok=True)
            import requests
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, stream=True, timeout=60)
            resp.raise_for_status()
            total = 0
            with open(p, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    total += len(chunk)
            return f"Downloaded {self._human_size(total)} to {p}"
        except PermissionError as e:
            return f"[{e}]"
        except Exception as e:
            return f"[Download failed: {e}]"

    # ── System ───────────────────────────────────────────────────────────────

    def open_app(self, app_name: str) -> str:
        app_map = {
            "terminal": ["x-terminal-emulator", "gnome-terminal", "xterm", "konsole"],
            "browser": ["xdg-open", "firefox", "chromium", "google-chrome"],
            "files": ["nautilus", "dolphin", "thunar", "nemo"],
            "vscode": ["code", "codium"],
            "text editor": ["gedit", "kate", "mousepad", "xed"],
        }
        candidates = app_map.get(app_name.lower(), [app_name])
        for cmd in candidates:
            if shutil.which(cmd):
                try:
                    subprocess.Popen(
                        [cmd],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return f"Opened: {cmd}"
                except Exception as e:
                    continue
        # Try xdg-open as fallback
        try:
            subprocess.Popen(
                ["xdg-open", app_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Launched via xdg-open: {app_name}"
        except Exception as e:
            return f"[Could not open {app_name}: {e}]"

    def run_command(self, command: str) -> str:
        if not self.enable_shell:
            return "[Shell execution is disabled in settings]"

        if self.shell_confirm_dangerous:
            for pattern in DANGEROUS_COMMANDS:
                if re.search(pattern, command, re.IGNORECASE):
                    return f"[Blocked: command matches dangerous pattern '{pattern}'. User must explicitly allow this.]"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.workspace),
            )
            out = result.stdout or ""
            err = result.stderr or ""
            combined = (out + ("\nSTDERR: " + err if err else "")).strip()
            if len(combined) > 4000:
                combined = combined[:4000] + "\n...[truncated]"
            return combined or "(no output)"
        except subprocess.TimeoutExpired:
            return "[Command timed out after 30 seconds]"
        except Exception as e:
            return f"[Command failed: {e}]"

    def get_system_info(self) -> str:
        info = []
        try:
            info.append(f"OS: {self.run_command('uname -a')}")
            info.append(f"CPU: {self.run_command('nproc')} cores")
            info.append(f"Memory: {self.run_command('free -h | head -2')}")
            info.append(f"Disk: {self.run_command('df -h / | tail -1')}")
            info.append(f"User: {self.run_command('whoami')}")
            info.append(f"Uptime: {self.run_command('uptime -p')}")
        except Exception as e:
            info.append(f"Error: {e}")
        return "\n".join(info)

    def screenshot(self) -> str:
        save_path = self.workspace / "aria_screenshot.png"
        cmds = [
            ["gnome-screenshot", "-f", str(save_path)],
            ["scrot", str(save_path)],
            ["import", "-window", "root", str(save_path)],
        ]
        for cmd in cmds:
            if shutil.which(cmd[0]):
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    if result.returncode == 0:
                        return f"Screenshot saved to {save_path}"
                except Exception:
                    continue
        return "[Screenshot failed: no compatible tool found (try: apt install scrot)]"

    # ── Knowledge base ───────────────────────────────────────────────────────

    def search_knowledge_base(self, query: str) -> str:
        if not self.kb:
            return "[Knowledge base not available]"
        results = self.kb.search(query, top_k=4)
        if not results:
            return "No relevant information found in knowledge base."
        parts = []
        for r in results:
            parts.append(f"[Source: {r['source']}]\n{r['text']}")
        return "\n\n---\n\n".join(parts)

    def add_to_knowledge(self, text: str, source: str = "user_input") -> str:
        if not self.kb:
            return "[Knowledge base not available]"
        result = self.kb.add_text(text, source)
        return f"Added {result['chunks']} chunks from '{source}' to knowledge base."

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _human_size(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"
