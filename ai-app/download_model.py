"""
Download a GGUF model for ARIA.
Run:  python download_model.py
Or:   python download_model.py --model llama3.2
"""

import os
import sys
import json
import urllib.request
import argparse
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

AVAILABLE_MODELS = {
    "llama3.2": {
        "desc": "Llama 3.2 3B Instruct  (~2.0 GB)  — fast, great for everyday use",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    },
    "llama3.1-8b": {
        "desc": "Llama 3.1 8B Instruct  (~4.9 GB)  — smarter, needs more RAM",
        "url": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    },
    "mistral-7b": {
        "desc": "Mistral 7B Instruct v0.3  (~4.1 GB)  — sharp and fast",
        "url": "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "filename": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
    },
    "phi3-mini": {
        "desc": "Phi-3 Mini 3.8B  (~2.2 GB)  — Microsoft model, very capable for its size",
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf",
        "filename": "Phi-3-mini-4k-instruct-q4.gguf",
    },
    "codellama": {
        "desc": "CodeLlama 7B Instruct  (~3.8 GB)  — best for coding tasks",
        "url": "https://huggingface.co/TheBloke/CodeLlama-7B-Instruct-GGUF/resolve/main/codellama-7b-instruct.Q4_K_M.gguf",
        "filename": "codellama-7b-instruct.Q4_K_M.gguf",
    },
}


def progress_bar(downloaded: int, total: int):
    if total <= 0:
        print(f"\r  {downloaded / 1024 / 1024:.1f} MB downloaded", end="", flush=True)
        return
    pct = downloaded / total
    bar_len = 40
    filled = int(bar_len * pct)
    bar = "█" * filled + "░" * (bar_len - filled)
    dl_mb  = downloaded / 1024 / 1024
    tot_mb = total / 1024 / 1024
    print(f"\r  [{bar}] {pct*100:.1f}%  {dl_mb:.0f}/{tot_mb:.0f} MB", end="", flush=True)


def download(url: str, dest: Path):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")

    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 64  # 64 KB
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                progress_bar(downloaded, total)

    tmp.rename(dest)
    print()  # newline after progress bar


def update_config(model_path: Path):
    cfg_path = Path(__file__).parent / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception:
        cfg = {}
    cfg["model_path"] = str(model_path)
    cfg_path.write_text(json.dumps(cfg, indent=2))
    print(f"  config.json updated → model_path: {model_path}")


def main():
    parser = argparse.ArgumentParser(description="Download a GGUF model for ARIA")
    parser.add_argument("--model", default=None, help="Model key (see list)")
    parser.add_argument("--url", default=None, help="Custom GGUF download URL")
    parser.add_argument("--filename", default=None, help="Filename when using --url")
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════════╗")
    print("║        ARIA — Model Downloader           ║")
    print("╚══════════════════════════════════════════╝\n")

    # Custom URL path
    if args.url:
        filename = args.filename or args.url.split("/")[-1]
        dest = MODELS_DIR / filename
        if dest.exists():
            print(f"Already downloaded: {dest}")
            update_config(dest)
            return
        print(f"Downloading from {args.url} …")
        download(args.url, dest)
        print(f"\n✓ Saved to {dest}")
        update_config(dest)
        return

    # Pick from menu
    choice_key = args.model
    if not choice_key:
        print("Which model do you want?\n")
        keys = list(AVAILABLE_MODELS.keys())
        for i, k in enumerate(keys, 1):
            info = AVAILABLE_MODELS[k]
            print(f"  {i}) {k:<14}  {info['desc']}")
        print()
        raw = input("Choice [1]: ").strip() or "1"
        try:
            idx = int(raw) - 1
            choice_key = keys[idx]
        except (ValueError, IndexError):
            choice_key = "llama3.2"

    info = AVAILABLE_MODELS.get(choice_key)
    if not info:
        print(f"Unknown model '{choice_key}'. Available: {', '.join(AVAILABLE_MODELS)}")
        sys.exit(1)

    dest = MODELS_DIR / info["filename"]

    if dest.exists():
        size_gb = dest.stat().st_size / 1024 / 1024 / 1024
        print(f"Already downloaded: {dest.name} ({size_gb:.2f} GB)")
        update_config(dest)
        print("\n✓ Ready to go. Run start.bat")
        return

    print(f"\nDownloading {choice_key}: {info['desc']}")
    print(f"  → {dest}\n")

    try:
        download(info["url"], dest)
    except KeyboardInterrupt:
        if dest.with_suffix(".tmp").exists():
            dest.with_suffix(".tmp").unlink()
        print("\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        print("  Try downloading manually and placing the .gguf file in the models/ folder.")
        sys.exit(1)

    size_gb = dest.stat().st_size / 1024 / 1024 / 1024
    print(f"\n✓ Downloaded {dest.name} ({size_gb:.2f} GB)")
    update_config(dest)
    print("✓ Run start.bat to launch ARIA\n")


if __name__ == "__main__":
    main()
