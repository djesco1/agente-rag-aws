"""Suite de evaluación del agente.

Ejecuta las preguntas de evals/eval_set.json contra la API y calcula:
  - Exactitud por criterios (palabras clave esperadas / prohibidas).
  - Precisión de citas: % de fuentes citadas que pertenecen a las fuentes esperadas.
  - Recall de fuente: ¿se citó al menos una fuente esperada?
  - Uso correcto de herramientas.
  - Respuesta ante falta de información y bloqueo de prompt injection.
  - Groundedness: (a) léxica: % de términos de la respuesta presentes en los
    fragmentos citados; (b) opcional LLM-as-judge con Bedrock (--judge).

Uso:
  # contra la Lambda desplegada (desde CloudShell o tu PC)
  python3 evals/run_eval.py --url https://xxxx.lambda-url.us-east-1.on.aws --api-key <key> --judge
  # contra la API local
  python3 evals/run_eval.py --url http://localhost:8000 --api-key dev-key-cambiame
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from api_client import ApiClient  # noqa: E402

NO_INFO_HINTS = ("no encontré información suficiente", "no encontre informacion suficiente", "no tengo información suficiente", "no dispongo de información")
STOP = set("el la los las un una de del al a en y o que por para con se su es son como lo le más muy hay este esta esto".split())


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def lexical_groundedness(answer: str, excerpts: list[str]) -> float | None:
    if not excerpts:
        return None
    context = set(re.findall(r"[a-z0-9]+", norm(" ".join(excerpts))))
    terms = [t for t in re.findall(r"[a-z0-9]+", norm(re.sub(r"\[\d+\]", "", answer))) if t not in STOP and len(t) > 3]
    if not terms:
        return None
    return round(sum(t in context for t in terms) / len(terms), 2)


JUDGE_PROMPT = """Eres un evaluador estricto de sistemas RAG. Evalúa si la RESPUESTA está completamente respaldada por el CONTEXTO (fragmentos de documentos y resultados de herramientas). No uses conocimiento externo.
Devuelve SOLO un JSON: {{"score": <1-5>, "justificacion": "<una frase>"}}
5 = todo respaldado; 3 = parcialmente; 1 = inventado o contradice el contexto.

CONTEXTO:
{context}

PREGUNTA: {question}
RESPUESTA: {answer}"""


def judge_groundedness(model_id: str, region: str, question: str, answer: str, context: str) -> dict:
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": JUDGE_PROMPT.format(context=context[:12000], question=question, answer=answer)}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0)) if match else {"score": None, "justificacion": text[:200]}


def evaluate_case(case: dict, data: dict, status: int) -> dict:
    answer = data.get("answer", "") if status == 200 else ""
    a_norm = norm(answer)
    cited_docs = [s["document"] for s in data.get("sources", [])]
    tools_used = [t["name"] for t in data.get("tool_calls", [])]
    checks: dict[str, bool] = {"http_200": status == 200}
    notes: list[str] = []

    for group in case.get("debe_contener", []):
        ok = any(norm(opt) in a_norm for opt in group)
        checks[f"contiene:{group[0]}"] = ok
        if not ok:
            notes.append(f"Falta '{group[0]}' en la respuesta")
    for bad in case.get("no_debe_contener", []):
        ok = norm(bad) not in a_norm
        checks[f"no_contiene:{bad}"] = ok
        if not ok:
            notes.append(f"La respuesta contiene texto prohibido '{bad}'")

    expected_sources = case.get("fuentes_esperadas")
    citation_precision = None
    if expected_sources:
        hit = any(d in expected_sources for d in cited_docs)
        checks["cita_fuente_esperada"] = hit
        citation_precision = round(sum(d in expected_sources for d in cited_docs) / len(cited_docs), 2) if cited_docs else 0.0
        if not hit:
            notes.append(f"No citó fuentes esperadas (citó: {cited_docs or 'ninguna'})")

    if case.get("herramienta_esperada"):
        ok = case["herramienta_esperada"] in tools_used
        checks["herramienta_correcta"] = ok
        if not ok:
            notes.append(f"No usó {case['herramienta_esperada']} (usó: {tools_used or 'ninguna'})")

    if case.get("espera_sin_informacion"):
        ok = any(h in a_norm for h in map(norm, NO_INFO_HINTS)) and not data.get("grounded", True)
        checks["declara_sin_informacion"] = ok
        if not ok:
            notes.append("Debía declarar falta de información (posible alucinación)")

    if case.get("espera_bloqueo"):
        ok = bool(data.get("guardrail"))
        checks["bloqueado_por_guardrail"] = ok
        if not ok:
            notes.append("El guardrail no bloqueó la petición")

    excerpts = [s.get("excerpt", "") for s in data.get("sources", [])]
    excerpts += [json.dumps(t.get("output"), ensure_ascii=False) for t in data.get("tool_calls", [])]
    passed = all(checks.values())
    return {
        "id": case["id"],
        "categoria": case["categoria"],
        "pregunta": case["pregunta"],
        "criterio_aceptacion": case["criterio_aceptacion"],
        "respuesta": answer,
        "fuentes_citadas": cited_docs,
        "herramientas": tools_used,
        "guardrail": data.get("guardrail"),
        "grounded_flag": data.get("grounded"),
        "checks": checks,
        "aprobado": passed,
        "precision_citas": citation_precision,
        "groundedness_lexica": lexical_groundedness(answer, excerpts) if not case.get("espera_sin_informacion") and not case.get("espera_bloqueo") else None,
        "latency_ms": data.get("latency_ms"),
        "trace_id": data.get("trace_id"),
        "observacion": "; ".join(notes) if notes else "Cumple el criterio de aceptación.",
        "_context": "\n---\n".join(excerpts),
    }


def write_report(results: list[dict], meta: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"results-{stamp}.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(results)
    passed = sum(r["aprobado"] for r in results)
    cps = [r["precision_citas"] for r in results if r["precision_citas"] is not None]
    lex = [r["groundedness_lexica"] for r in results if r["groundedness_lexica"] is not None]
    judge = [r["judge"]["score"] for r in results if r.get("judge") and isinstance(r["judge"].get("score"), (int, float))]
    by_cat: dict[str, list[bool]] = {}
    for r in results:
        by_cat.setdefault(r["categoria"], []).append(r["aprobado"])

    lines = [
        "# Reporte de evaluación del agente RAG",
        "",
        f"- Fecha: {meta['fecha']}",
        f"- Endpoint: `{meta['url']}`",
        f"- Modelo: `{meta.get('modelo', '?')}`",
        "",
        "## Métricas",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Exactitud (casos aprobados) | **{passed}/{total} = {passed / total:.0%}** |",
    ]
    for cat, vals in by_cat.items():
        lines.append(f"| Exactitud · {cat} | {sum(vals)}/{len(vals)} |")
    if cps:
        lines.append(f"| Precisión de citas (promedio) | {sum(cps) / len(cps):.0%} |")
    if lex:
        lines.append(f"| Groundedness léxica (promedio) | {sum(lex) / len(lex):.0%} |")
    if judge:
        lines.append(f"| Groundedness LLM-as-judge (promedio 1-5) | {sum(judge) / len(judge):.2f} |")
    lat = [r["latency_ms"] for r in results if r["latency_ms"]]
    if lat:
        lines.append(f"| Latencia promedio | {sum(lat) / len(lat) / 1000:.1f} s |")

    lines += ["", "## Resultados por pregunta", "", "| ID | Categoría | Pregunta | Criterio de aceptación | Resultado obtenido | ¿Aprueba? | Observación |", "|---|---|---|---|---|---|---|"]
    for r in results:
        resp = r["respuesta"].replace("\n", " ").replace("|", "\\|")
        resp = (resp[:280] + "…") if len(resp) > 280 else resp
        extra = []
        if r["herramientas"]:
            extra.append(f"herramientas: {', '.join(r['herramientas'])}")
        if r["fuentes_citadas"]:
            extra.append(f"fuentes: {', '.join(sorted(set(r['fuentes_citadas'])))}")
        if r["guardrail"]:
            extra.append(f"guardrail: {r['guardrail']}")
        if r.get("judge"):
            extra.append(f"judge: {r['judge'].get('score')}")
        obs = r["observacion"] + (f" ({'; '.join(extra)})" if extra else "")
        lines.append(f"| {r['id']} | {r['categoria']} | {r['pregunta']} | {r['criterio_aceptacion']} | {resp} | {'✅' if r['aprobado'] else '❌'} | {obs} |")

    path = out_dir / f"report-{stamp}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--judge", action="store_true", help="Evalúa groundedness con un LLM juez en Bedrock")
    parser.add_argument("--judge-model", default="us.amazon.nova-lite-v1:0")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--only", nargs="*", help="IDs a ejecutar (p. ej. Q01 Q13)")
    args = parser.parse_args()

    cases = json.loads((ROOT / "evals" / "eval_set.json").read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    client = ApiClient(args.url, args.api_key)
    results, model = [], None

    for case in cases:
        status, data = client.ask(case["pregunta"], session_id="eval")
        model = data.get("model_id", model)
        res = evaluate_case(case, data, status)
        if args.judge and res["respuesta"] and res["_context"] and not case.get("espera_bloqueo"):
            try:
                res["judge"] = judge_groundedness(args.judge_model, args.region, case["pregunta"], res["respuesta"], res["_context"])
            except Exception as exc:  # noqa: BLE001
                res["judge"] = {"score": None, "justificacion": f"error: {exc}"}
        res.pop("_context")
        results.append(res)
        print(f"{'PASS' if res['aprobado'] else 'FAIL'}  {case['id']}  {res['observacion']}")
        time.sleep(0.3)

    meta = {"fecha": datetime.now().isoformat(timespec="seconds"), "url": args.url, "modelo": model}
    path = write_report(results, meta, ROOT / "evals" / "results")
    print(f"\n{sum(r['aprobado'] for r in results)}/{len(results)} aprobados. Reporte: {path}")


if __name__ == "__main__":
    main()
