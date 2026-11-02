"""Amazon Bedrock: Converse API (LLM con tool use nativo) y Titan Text Embeddings V2.

Autenticación: el rol IAM de la Lambda (o tu perfil local de AWS CLI). No hay
API keys de modelo que guardar.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.providers.base import LLMResponse, ProviderError, ToolCall, ToolSpec

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=60, connect_timeout=5)


def _to_bedrock_messages(messages: list[dict[str, Any]], supports_status: bool = False) -> list[dict[str, Any]]:
    """Traduce el formato neutral al de Converse. El campo `status` de toolResult solo
    lo aceptan algunos modelos (Anthropic); para el resto el error va dentro del JSON."""
    out = []
    for msg in messages:
        blocks = []
        for b in msg["content"]:
            if b["type"] == "text":
                blocks.append({"text": b["text"]})
            elif b["type"] == "tool_use":
                blocks.append({"toolUse": {"toolUseId": b["id"], "name": b["name"], "input": b["input"]}})
            elif b["type"] == "tool_result":
                result = {"toolUseId": b["id"], "content": [{"json": b["content"]}]}
                if supports_status:
                    result["status"] = b.get("status", "success")
                blocks.append({"toolResult": result})
        out.append({"role": msg["role"], "content": blocks})
    return out


class BedrockLLM:
    def __init__(self, model_id: str, region: str, temperature: float = 0.1, max_tokens: int = 800):
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region, config=_BOTO_CONFIG)

    def chat(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": _to_bedrock_messages(messages, supports_status="anthropic" in self.model_id),
            "inferenceConfig": {"maxTokens": self.max_tokens, "temperature": self.temperature},
        }
        if tools:
            kwargs["toolConfig"] = {
                "tools": [
                    {"toolSpec": {"name": t.name, "description": t.description, "inputSchema": {"json": t.input_schema}}}
                    for t in tools
                ]
            }
        try:
            resp = self._client.converse(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise ProviderError(f"Bedrock converse falló: {exc}") from exc

        content = resp["output"]["message"]["content"]
        text_parts, tool_calls, neutral = [], [], []
        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
                neutral.append({"type": "text", "text": block["text"]})
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(ToolCall(id=tu["toolUseId"], name=tu["name"], input=tu.get("input") or {}))
                neutral.append({"type": "tool_use", "id": tu["toolUseId"], "name": tu["name"], "input": tu.get("input") or {}})
        usage = resp.get("usage", {})
        return LLMResponse(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=resp.get("stopReason", ""),
            content=neutral,
            usage={"input_tokens": usage.get("inputTokens", 0), "output_tokens": usage.get("outputTokens", 0)},
        )


class BedrockEmbeddings:
    """Titan Text Embeddings V2 (dimensiones admitidas: 256, 512 o 1024)."""

    def __init__(self, model_id: str, region: str, dimension: int = 1024):
        self.model_id = model_id
        self.dimension = dimension
        self._client = boto3.client("bedrock-runtime", region_name=region, config=_BOTO_CONFIG)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            body = json.dumps({"inputText": text[:30000], "dimensions": self.dimension, "normalize": True})
            try:
                resp = self._client.invoke_model(modelId=self.model_id, body=body, contentType="application/json", accept="application/json")
            except (ClientError, BotoCoreError) as exc:
                raise ProviderError(f"Bedrock embeddings falló: {exc}") from exc
            vectors.append(json.loads(resp["body"].read())["embedding"])
        return vectors
