"""Composición de dependencias (local vs AWS) en un solo lugar."""
from __future__ import annotations

from functools import lru_cache

from app.agent.agent import RagAgent
from app.config import get_settings
from app.providers import get_embeddings, get_llm
from app.rag.pipeline import RagPipeline
from app.rag.vectorstore import LocalVectorStore, S3VectorStore
from app.storage.repositories import (
    DynamoHistoryStore,
    DynamoRequestsRepo,
    JsonRequestsRepo,
    LocalDocumentStore,
    LocalHistoryStore,
    S3DocumentStore,
)


@lru_cache
def get_pipeline() -> RagPipeline:
    s = get_settings()
    vectors = S3VectorStore(s.vector_bucket, s.vector_index, s.aws_region) if s.vector_store == "s3vectors" else LocalVectorStore(s.data_dir / "vectors.json")
    docs = S3DocumentStore(s.docs_bucket, s.aws_region) if s.storage_backend == "aws" else LocalDocumentStore(s.data_dir)
    return RagPipeline(s, get_embeddings(), vectors, docs)


@lru_cache
def get_history():
    s = get_settings()
    return DynamoHistoryStore(s.history_table, s.aws_region) if s.storage_backend == "aws" else LocalHistoryStore(s.data_dir)


@lru_cache
def get_requests_repo():
    s = get_settings()
    return DynamoRequestsRepo(s.requests_table, s.aws_region) if s.storage_backend == "aws" else JsonRequestsRepo(s.requests_seed_file)


@lru_cache
def get_agent() -> RagAgent:
    return RagAgent(get_settings(), get_llm(), get_pipeline(), get_history(), get_requests_repo())


def reset_container() -> None:
    """Usado por las pruebas para reconstruir dependencias con otra configuración."""
    from app import providers

    for fn in (get_pipeline, get_history, get_requests_repo, get_agent, providers.get_llm, providers.get_embeddings, get_settings):
        fn.cache_clear()
