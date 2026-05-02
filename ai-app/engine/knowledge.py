import json
import os
import re
import math
import hashlib
from pathlib import Path
from typing import Optional
from collections import Counter


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9]{2,}\b", text.lower())


def _tfidf_score(query_tokens: list[str], doc_tokens: list[str], df: dict, n_docs: int) -> float:
    doc_freq = Counter(doc_tokens)
    score = 0.0
    for tok in query_tokens:
        tf = doc_freq.get(tok, 0) / max(len(doc_tokens), 1)
        idf = math.log((n_docs + 1) / (df.get(tok, 0) + 1)) + 1
        score += tf * idf
    return score


class KnowledgeBase:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.data_dir / "index.json"
        self.chunks: list[dict] = []
        self.df: dict[str, int] = {}
        self._load()

    def _load(self):
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
                self.chunks = data.get("chunks", [])
                self.df = data.get("df", {})
            except Exception:
                self.chunks, self.df = [], {}

    def _save(self):
        self.index_path.write_text(
            json.dumps({"chunks": self.chunks, "df": self.df}, indent=2)
        )

    def _rebuild_df(self):
        self.df = {}
        for chunk in self.chunks:
            seen = set()
            for tok in chunk["tokens"]:
                if tok not in seen:
                    self.df[tok] = self.df.get(tok, 0) + 1
                    seen.add(tok)

    def _chunk_text(self, text: str, source: str, chunk_size: int = 500) -> list[dict]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - 50):
            snippet = " ".join(words[i : i + chunk_size])
            if len(snippet.strip()) < 20:
                continue
            tokens = _tokenize(snippet)
            chunks.append({
                "id": hashlib.md5(f"{source}:{i}".encode()).hexdigest()[:12],
                "source": source,
                "text": snippet,
                "tokens": tokens,
                "start": i,
            })
        return chunks

    def _extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        try:
            if suffix in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv",
                          ".html", ".css", ".yaml", ".yml", ".toml", ".sh",
                          ".java", ".cpp", ".c", ".rs", ".go", ".rb", ".php"):
                return file_path.read_text(errors="replace")
            elif suffix == ".pdf":
                return self._extract_pdf(file_path)
            else:
                # Try as text
                return file_path.read_text(errors="replace")
        except Exception as e:
            return f"[Could not read file: {e}]"

    def _extract_pdf(self, path: Path) -> str:
        try:
            import PyPDF2
            text = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        except ImportError:
            pass
        try:
            import subprocess
            result = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return "[PDF text extraction not available - install PyPDF2 or pdftotext]"

    def add_file(self, file_path: str) -> dict:
        path = Path(file_path).expanduser()
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        source = path.name
        # Remove existing chunks for this source
        self.chunks = [c for c in self.chunks if c["source"] != source]

        text = self._extract_text(path)
        if text.startswith("[Could not"):
            return {"success": False, "error": text}

        new_chunks = self._chunk_text(text, source)
        self.chunks.extend(new_chunks)
        self._rebuild_df()
        self._save()

        return {
            "success": True,
            "source": source,
            "chunks": len(new_chunks),
            "chars": len(text),
        }

    def add_text(self, text: str, source: str = "manual") -> dict:
        self.chunks = [c for c in self.chunks if c["source"] != source]
        new_chunks = self._chunk_text(text, source)
        self.chunks.extend(new_chunks)
        self._rebuild_df()
        self._save()
        return {"success": True, "source": source, "chunks": len(new_chunks)}

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scored = []
        for chunk in self.chunks:
            score = _tfidf_score(q_tokens, chunk["tokens"], self.df, len(self.chunks))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"source": c["source"], "text": c["text"], "score": round(s, 4)}
            for s, c in scored[:top_k]
        ]

    def list_documents(self) -> list[dict]:
        sources: dict[str, int] = {}
        for chunk in self.chunks:
            sources[chunk["source"]] = sources.get(chunk["source"], 0) + 1
        return [{"source": s, "chunks": n} for s, n in sources.items()]

    def remove_document(self, source: str):
        self.chunks = [c for c in self.chunks if c["source"] != source]
        self._rebuild_df()
        self._save()

    def clear(self):
        self.chunks = []
        self.df = {}
        self._save()
