"""Proveedores para desarrollo y pruebas sin AWS.

- HashEmbeddings: embeddings deterministas sin modelo (solo desarrollo/pruebas).
- FakeLLM: LLM determinista para pruebas unitarias del flujo del agente.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any

from app.providers.base import LLMResponse, ToolCall, ToolSpec


# --------------------------------------------------------------------------------------
# Hash embeddings (sin modelo)
# --------------------------------------------------------------------------------------
_STOPWORDS = set(
    "el la los las un una unos unas de del al a en y o u que por para con sin se su sus es son ser como cual cuales "
    "qué cuál cuáles cómo cuándo dónde este esta estos estas ese esa eso lo le les mi tu nos más menos muy hay "
    "the of and to in is are for on with as by be".split()
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", _strip_accents(text.lower()))
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _l2_normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class HashEmbeddings:
    """Bolsa de palabras + bigramas con *feature hashing*. No es semántico: solo
    permite ejecutar y probar el pipeline completo sin credenciales ni descargas."""

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension

    def _features(self, text: str) -> list[str]:
        toks = _tokens(text)
        # prefijos de 5 letras ~ stemming barato (solicitud/solicitudes)
        stems = [t[:5] for t in toks]
        return stems + [f"{a}_{b}" for a, b in zip(stems, stems[1:])]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dimension
            for feat in self._features(text):
                h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
                v[h % self.dimension] += 1.0 if (h >> 64) & 1 else -1.0
            out.append(_l2_normalize(v))
        return out


# --------------------------------------------------------------------------------------
# Fake LLM (pruebas)
# --------------------------------------------------------------------------------------
_REQ_ID = re.compile(r"\bSOL-\d{4}\b", re.IGNORECASE)


class FakeLLM:
    """Simula un LLM con tool use para probar el loop del agente sin red.

    Reglas: si la pregunta menciona un ID SOL-XXXX y todavía no hay resultado de
    herramienta, pide `consultar_estado_solicitud`. Si no, responde citando el
    primer documento del contexto o declara que no hay información.
    """

    model_id = "fake-llm"

    def chat(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> LLMResponse:
        first_user = next(b["text"] for b in messages[0]["content"] if b["type"] == "text")
        question = first_user.split("<pregunta>")[-1].split("</pregunta>")[0]
        tool_names = {t.name for t in tools}
        results = [b for m in messages for b in m["content"] if b["type"] == "tool_result"]

        match = _REQ_ID.search(question)
        if match and not results and "consultar_estado_solicitud" in tool_names:
            call = ToolCall(id="tool_fake_1", name="consultar_estado_solicitud", input={"request_id": match.group(0).upper()})
            return LLMResponse("", [call], "tool_use", [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}])

        if results:
            text = f"Resultado de la herramienta: {json.dumps(results[-1]['content'], ensure_ascii=False)}"
        else:
            docs = re.findall(r'<documento ref="(\d+)"[^>]*>\s*(.*?)\s*</documento>', first_user, re.DOTALL)
            if docs:
                ref, body = docs[0]
                sentence = re.split(r"(?<=[.!?])\s", body.strip())[0]
                text = f"{sentence} [{ref}]"
            else:
                text = "No encontré información suficiente en los documentos disponibles para responder esa pregunta."
        return LLMResponse(text, [], "end_turn", [{"type": "text", "text": text}], {"input_tokens": 0, "output_tokens": 0})
