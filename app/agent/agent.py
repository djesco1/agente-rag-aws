"""Agente RAG con herramientas.

Flujo por pregunta:
 1. Guardrail de entrada (prompt injection directo) -> si se detecta, se responde
    sin llamar al modelo.
 2. Recuperación de contexto (top-k + umbral de relevancia).
 3. Loop del agente (máx. MAX_AGENT_STEPS): el modelo responde o pide herramientas;
    las herramientas se ejecutan con validación y su resultado vuelve al modelo.
 4. Guardrail de salida (fuga del prompt/canario) y extracción de citas [n].
 5. Registro en historial (trazabilidad) y logs estructurados.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.prompts import CANARY, INJECTION_MESSAGE, NO_INFO_MESSAGE, SYSTEM_PROMPT, build_user_message
from app.agent.tools import TOOLS, run_tool
from app.logging_conf import log_event, trace_id_var
from app.security import detect_prompt_injection

logger = logging.getLogger(__name__)
_CITATION = re.compile(r"\[(\d{1,2})\]")
# Algunos modelos (p. ej. Amazon Nova con herramientas) escriben su razonamiento en
# <thinking>...</thinking>. Es interno: no se muestra al usuario ni se guarda en la respuesta.
_THINKING = re.compile(r"<thinking>.*?(</thinking>|$)", re.DOTALL | re.IGNORECASE)


def clean_answer(text: str) -> str:
    text = _THINKING.sub("", text or "")
    # Etiquetas envolventes que a veces agrega el modelo (<answer>, <respuesta>, <response>).
    text = re.sub(r"</?\s*(answer|respuesta|response|final_answer)\s*>", "", text, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_NO_INFO_HINTS = ("no encontré información suficiente", "no tengo información suficiente", "no encontre informacion suficiente")


class RagAgent:
    def __init__(self, settings, llm, pipeline, history_store, requests_repo):
        self.s = settings
        self.llm = llm
        self.pipeline = pipeline
        self.history = history_store
        self.requests = requests_repo

    def ask(self, question: str, session_id: str | None = None, top_k: int | None = None) -> dict[str, Any]:
        trace_id = trace_id_var.get() if trace_id_var.get() != "-" else uuid.uuid4().hex
        started = time.perf_counter()
        result = self._run(question, top_k)
        result.update(
            trace_id=trace_id,
            model_id=getattr(self.llm, "model_id", "unknown"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        record = {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "session_id": session_id,
            "question": question,
            **{k: result[k] for k in ("answer", "grounded", "guardrail", "sources", "tool_calls", "model_id", "latency_ms", "usage")},
        }
        try:
            self.history.put(record)
        except Exception:  # noqa: BLE001 - el historial no debe tumbar la respuesta
            logger.exception("history_write_failed")
        log_event(
            logger,
            "ask_completed",
            grounded=result["grounded"],
            guardrail=result["guardrail"],
            sources=[s["chunk_id"] for s in result["sources"]],
            tools=[t["name"] for t in result["tool_calls"]],
            latency_ms=result["latency_ms"],
            usage=result["usage"],
        )
        return result

    # ------------------------------------------------------------------
    def _run(self, question: str, top_k: int | None) -> dict[str, Any]:
        injection = detect_prompt_injection(question)
        if injection:
            log_event(logger, "prompt_injection_blocked", logging.WARNING, categories=injection)
            return self._result(INJECTION_MESSAGE, False, [], [], f"prompt_injection:{','.join(injection)}", {})

        relevant, _ = self.pipeline.retrieve(question, top_k)
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": build_user_message(question, relevant)}]}]
        tool_specs = [t.spec for t in TOOLS.values()]
        tool_calls: list[dict[str, Any]] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        answer = ""

        for step in range(self.s.max_agent_steps):
            resp = self.llm.chat(SYSTEM_PROMPT, messages, tool_specs)
            for k in usage:
                usage[k] += resp.usage.get(k, 0)
            if not resp.tool_calls:
                answer = resp.text
                break
            messages.append({"role": "assistant", "content": resp.content})
            results_blocks = []
            for call in resp.tool_calls:
                output, status = run_tool(call.name, call.input, self.requests)
                log_event(logger, "tool_call", step=step, tool=call.name, input=call.input, status=status)
                tool_calls.append({"name": call.name, "input": call.input, "output": output, "status": status})
                results_blocks.append({"type": "tool_result", "id": call.id, "content": output, "status": status})
            messages.append({"role": "user", "content": results_blocks})
        else:
            answer = "No pude completar la respuesta dentro del límite de pasos del agente. Intenta una pregunta más específica."

        answer = clean_answer(answer)
        if not answer:
            answer = NO_INFO_MESSAGE

        # Guardrail de salida: fuga del prompt del sistema.
        if CANARY in answer:
            log_event(logger, "system_prompt_leak_blocked", logging.WARNING)
            return self._result(INJECTION_MESSAGE, False, [], tool_calls, "output_leak", usage)

        cited_refs = sorted({int(n) for n in _CITATION.findall(answer) if 1 <= int(n) <= len(relevant)})
        sources = [
            {
                "ref": n,
                "document": relevant[n - 1].document,
                "chunk_id": relevant[n - 1].chunk_id,
                "score": round(relevant[n - 1].score, 4),
                "excerpt": relevant[n - 1].text,
            }
            for n in cited_refs
        ]
        said_no_info = any(h in answer.lower() for h in _NO_INFO_HINTS)
        used_tools = any(t["status"] == "success" for t in tool_calls)
        grounded = (bool(sources) or used_tools) and not said_no_info
        return self._result(answer, grounded, sources, tool_calls, None, usage)

    @staticmethod
    def _result(answer, grounded, sources, tool_calls, guardrail, usage) -> dict[str, Any]:
        return {"answer": answer, "grounded": grounded, "sources": sources, "tool_calls": tool_calls, "guardrail": guardrail, "usage": usage}
