"""Sube todos los documentos de una carpeta al endpoint POST /documents.

Uso:
    python3 scripts/ingest_docs.py --url https://<tu-function-url> --api-key <key>
    python3 scripts/ingest_docs.py --url http://localhost:8000 --api-key dev-key
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ApiClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--folder", default=str(ROOT / "data" / "docs"))
    args = parser.parse_args()

    client = ApiClient(args.url, args.api_key)
    files = sorted(p for p in Path(args.folder).iterdir() if p.suffix.lower() in {".md", ".txt", ".pdf"})
    for f in files:
        status, body = client.upload(f)
        print(f"[{status}] {f.name}: {body}")


if __name__ == "__main__":
    main()
