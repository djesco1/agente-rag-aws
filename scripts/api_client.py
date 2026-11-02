"""Cliente HTTP mínimo (solo librería estándar) para la API del agente.
Lo usan ingest_docs.py y evals/run_eval.py, así funcionan en CloudShell sin instalar nada."""
from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 90):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> tuple[int, dict]:
        headers = {"X-API-Key": self.api_key}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(f"{self.base_url}{path}", data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"{}")
            except json.JSONDecodeError:
                return exc.code, {"error": exc.reason}

    def ask(self, question: str, session_id: str | None = None) -> tuple[int, dict]:
        payload = {"question": question}
        if session_id:
            payload["session_id"] = session_id
        return self._request("POST", "/ask", json.dumps(payload).encode(), "application/json")

    def upload(self, path: Path) -> tuple[int, dict]:
        boundary = uuid.uuid4().hex
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return self._request("POST", "/documents", body, f"multipart/form-data; boundary={boundary}")

    def history(self, limit: int = 10) -> tuple[int, dict]:
        return self._request("GET", f"/history?limit={limit}")
