"""Configuración centralizada leída desde variables de entorno.

Ningún secreto se escribe en el código: todo llega por entorno (local: archivo .env,
AWS: variables de la Lambda + SSM Parameter Store para la API key).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Carga mínima de .env (sin dependencia extra). No sobrescribe variables ya definidas."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Entorno de ejecución: "local" o "aws"
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "local"))
    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # Proveedores intercambiables
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "bedrock"))  # bedrock | fake
    embeddings_provider: str = field(default_factory=lambda: _env("EMBEDDINGS_PROVIDER", "bedrock"))  # bedrock | hash
    vector_store: str = field(default_factory=lambda: _env("VECTOR_STORE", "local"))  # local | s3vectors
    storage_backend: str = field(default_factory=lambda: _env("STORAGE_BACKEND", "local"))  # local | aws

    # Modelos
    llm_model_id: str = field(default_factory=lambda: _env("LLM_MODEL_ID", "us.amazon.nova-lite-v1:0"))
    embeddings_model_id: str = field(default_factory=lambda: _env("EMBEDDINGS_MODEL_ID", "amazon.titan-embed-text-v2:0"))
    embeddings_dimension: int = field(default_factory=lambda: _env_int("EMBEDDINGS_DIMENSION", 1024))
    llm_temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.1))
    llm_max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 800))

    # RAG
    chunk_size: int = field(default_factory=lambda: _env_int("CHUNK_SIZE", 800))
    chunk_overlap: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP", 120))
    top_k: int = field(default_factory=lambda: _env_int("TOP_K", 4))
    # Similitud coseno mínima para considerar que hay contexto suficiente.
    min_relevance: float = field(default_factory=lambda: _env_float("MIN_RELEVANCE", 0.20))

    # Agente
    max_agent_steps: int = field(default_factory=lambda: _env_int("MAX_AGENT_STEPS", 5))

    # Límites de entrada
    max_question_chars: int = field(default_factory=lambda: _env_int("MAX_QUESTION_CHARS", 2000))
    max_upload_bytes: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_BYTES", 2_000_000))

    # Seguridad: API key directa (solo local) o nombre del parámetro SSM (AWS)
    api_key: str = field(default_factory=lambda: _env("API_KEY", ""))
    api_key_ssm_param: str = field(default_factory=lambda: _env("API_KEY_SSM_PARAM", ""))

    # Recursos AWS
    docs_bucket: str = field(default_factory=lambda: _env("DOCS_BUCKET", ""))
    vector_bucket: str = field(default_factory=lambda: _env("VECTOR_BUCKET", ""))
    vector_index: str = field(default_factory=lambda: _env("VECTOR_INDEX", "docs-index"))
    history_table: str = field(default_factory=lambda: _env("HISTORY_TABLE", ""))
    requests_table: str = field(default_factory=lambda: _env("REQUESTS_TABLE", ""))

    # Rutas locales
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT_DIR / ".localdata"))))
    requests_seed_file: Path = field(default_factory=lambda: Path(_env("REQUESTS_SEED_FILE", str(ROOT_DIR / "data" / "requests.json"))))


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(ROOT_DIR / ".env")
    return Settings()
