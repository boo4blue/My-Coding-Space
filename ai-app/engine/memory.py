import json
import os
from pathlib import Path
from datetime import datetime


class ConversationMemory:
    def __init__(self, sessions_dir: str, max_history: int = 50):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.max_history = max_history
        self.current_session_id: str = self._new_session_id()
        self.messages: list[dict] = []
        self._sessions_index: list[dict] = self._load_index()

    def _new_session_id(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _session_path(self, sid: str) -> Path:
        return self.sessions_dir / f"{sid}.json"

    def _index_path(self) -> Path:
        return self.sessions_dir / "index.json"

    def _load_index(self) -> list[dict]:
        p = self._index_path()
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        return []

    def _save_index(self):
        self._index_path().write_text(json.dumps(self._sessions_index, indent=2))

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_history * 2:
            # Keep system context, trim middle
            self.messages = self.messages[-self.max_history * 2:]
        self._autosave()

    def get_history(self) -> list[dict]:
        return self.messages.copy()

    def clear(self):
        self.messages = []

    def new_session(self, title: str = "") -> str:
        self._autosave()
        self.current_session_id = self._new_session_id()
        self.messages = []
        entry = {
            "id": self.current_session_id,
            "title": title or f"Chat {self.current_session_id}",
            "created": self.current_session_id,
        }
        self._sessions_index.insert(0, entry)
        if len(self._sessions_index) > 100:
            self._sessions_index = self._sessions_index[:100]
        self._save_index()
        return self.current_session_id

    def _autosave(self):
        if not self.messages:
            return
        data = {
            "id": self.current_session_id,
            "messages": self.messages,
            "updated": datetime.now().isoformat(),
        }
        self._session_path(self.current_session_id).write_text(
            json.dumps(data, indent=2)
        )
        # Update index title from first user message
        first_user = next(
            (m["content"][:60] for m in self.messages if m["role"] == "user"), None
        )
        for entry in self._sessions_index:
            if entry["id"] == self.current_session_id and first_user:
                entry["title"] = first_user
        self._save_index()

    def load_session(self, session_id: str) -> bool:
        p = self._session_path(session_id)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text())
            self.messages = data.get("messages", [])
            self.current_session_id = session_id
            return True
        except Exception:
            return False

    def list_sessions(self) -> list[dict]:
        return self._sessions_index

    def delete_session(self, session_id: str):
        p = self._session_path(session_id)
        if p.exists():
            p.unlink()
        self._sessions_index = [
            e for e in self._sessions_index if e["id"] != session_id
        ]
        self._save_index()
