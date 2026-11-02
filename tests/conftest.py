import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API con proveedores offline (FakeLLM + HashEmbeddings) y datos en tmp."""
    env = {
        "APP_ENV": "local",
        "LLM_PROVIDER": "fake",
        "EMBEDDINGS_PROVIDER": "hash",
        "VECTOR_STORE": "local",
        "STORAGE_BACKEND": "local",
        "MIN_RELEVANCE": "0.10",
        "API_KEY": "test-key",
        "API_KEY_SSM_PARAM": "",
        "DATA_DIR": str(tmp_path),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.container import reset_container

    reset_container()
    import importlib

    import app.main as main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    c = TestClient(main.app)
    c.headers.update({"X-API-Key": "test-key"})
    yield c
    reset_container()


@pytest.fixture()
def loaded_client(client):
    for f in sorted((ROOT / "data" / "docs").glob("*.md")):
        r = client.post("/documents", files={"file": (f.name, f.read_bytes(), "text/markdown")})
        assert r.status_code == 201, r.text
    return client
