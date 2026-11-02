"""Fábrica de proveedores según variables de entorno."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import EmbeddingsProvider, LLMProvider


@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "bedrock":
        from app.providers.bedrock import BedrockLLM

        return BedrockLLM(s.llm_model_id, s.aws_region, s.llm_temperature, s.llm_max_tokens)
    if s.llm_provider == "fake":
        from app.providers.local import FakeLLM

        return FakeLLM()
    raise ValueError(f"LLM_PROVIDER no soportado: {s.llm_provider}")


@lru_cache
def get_embeddings() -> EmbeddingsProvider:
    s = get_settings()
    if s.embeddings_provider == "bedrock":
        from app.providers.bedrock import BedrockEmbeddings

        return BedrockEmbeddings(s.embeddings_model_id, s.aws_region, s.embeddings_dimension)
    if s.embeddings_provider == "hash":
        from app.providers.local import HashEmbeddings

        return HashEmbeddings(s.embeddings_dimension)
    raise ValueError(f"EMBEDDINGS_PROVIDER no soportado: {s.embeddings_provider}")
