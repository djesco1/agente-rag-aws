"""Contratos de la API (validación de entradas con Pydantic)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, examples=["¿Cuál es el SLA de una solicitud de prioridad alta?"])
    session_id: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="Agrupa interacciones de un mismo usuario/conversación.")
    top_k: int | None = Field(None, ge=1, le=10, description="Número de fragmentos a recuperar (opcional).")

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("La pregunta es demasiado corta.")
        return v


class SourceRef(BaseModel):
    ref: int = Field(..., description="Número de referencia usado en la respuesta, p. ej. [1].")
    document: str
    chunk_id: str
    score: float
    excerpt: str


class ToolCallRecord(BaseModel):
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | list[Any] | str | None
    status: Literal["success", "error"]


class AskResponse(BaseModel):
    trace_id: str
    answer: str
    grounded: bool = Field(..., description="True si la respuesta se apoyó en fragmentos recuperados o en herramientas.")
    sources: list[SourceRef]
    tool_calls: list[ToolCallRecord]
    guardrail: str | None = Field(None, description="Motivo si un control de seguridad intervino (p. ej. prompt_injection).")
    model_id: str
    latency_ms: int
    usage: dict[str, int] = Field(default_factory=dict)


class DocumentIngestResponse(BaseModel):
    document: str
    chunks: int
    characters: int
    flagged_chunks: int = Field(0, description="Fragmentos marcados por contener posibles instrucciones (indirect prompt injection).")
    storage_uri: str


class DocumentInfo(BaseModel):
    document: str
    size_bytes: int | None = None
    last_modified: str | None = None


class HistoryItem(BaseModel):
    trace_id: str
    timestamp: str
    session_id: str | None = None
    question: str
    answer: str
    grounded: bool
    guardrail: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    model_id: str | None = None
    latency_ms: int | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: Any = None
    trace_id: str | None = None
