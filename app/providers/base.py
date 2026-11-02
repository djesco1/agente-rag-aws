"""Interfaces neutrales de proveedor.

El agente trabaja con un formato de mensajes propio y cada proveedor (Bedrock,
Fake) lo traduce a su API. Así cambiar de modelo o de nube es cambiar
una variable de entorno, no reescribir el agente.

Formato neutral de mensajes:
    {"role": "user" | "assistant", "content": [bloque, ...]}
Bloques:
    {"type": "text", "text": str}
    {"type": "tool_use", "id": str, "name": str, "input": dict}
    {"type": "tool_result", "id": str, "content": dict, "status": "success" | "error"}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    content: list[dict[str, Any]]  # bloques neutrales del asistente (para re-enviar en el loop)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class LLMProvider(Protocol):
    model_id: str

    def chat(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> LLMResponse: ...


class EmbeddingsProvider(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ProviderError(RuntimeError):
    """Error al invocar un modelo (cuotas, permisos, timeouts...)."""
