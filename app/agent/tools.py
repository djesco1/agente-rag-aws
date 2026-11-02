"""Herramientas del agente.

Cada herramienta: esquema JSON (lo ve el modelo), validación Pydantic de los
argumentos (no se confía en lo que genera el modelo) y lógica determinista.
Las reglas de prioridad y esfuerzo replican las de los documentos internos
(data/docs/procedimiento_gestion_solicitudes.md) para que agente y RAG coincidan.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, ValidationError

from app.providers.base import ToolSpec


# --------------------------------------------------------------------------------------
# 1. Consultar estado de una solicitud
# --------------------------------------------------------------------------------------
class EstadoInput(BaseModel):
    request_id: str = Field(..., pattern=r"^SOL-\d{4}$")


def consultar_estado_solicitud(repo, args: EstadoInput) -> dict[str, Any]:
    item = repo.get(args.request_id)
    if not item:
        return {"encontrada": False, "request_id": args.request_id, "mensaje": "No existe una solicitud con ese ID."}
    return {"encontrada": True, **item}


# --------------------------------------------------------------------------------------
# 2. Clasificar prioridad
# --------------------------------------------------------------------------------------
SLA = {
    "P1": {"nombre": "Crítica", "respuesta": "1 hora", "resolucion": "4 horas"},
    "P2": {"nombre": "Alta", "respuesta": "4 horas", "resolucion": "1 día hábil"},
    "P3": {"nombre": "Media", "respuesta": "1 día hábil", "resolucion": "3 días hábiles"},
    "P4": {"nombre": "Baja", "respuesta": "2 días hábiles", "resolucion": "10 días hábiles"},
}


class PrioridadInput(BaseModel):
    impacto: Literal["alto", "medio", "bajo"]
    usuarios_afectados: int = Field(..., ge=0, le=1_000_000)
    servicio_critico: bool = False
    tiene_workaround: bool = True


def clasificar_prioridad(_repo, a: PrioridadInput) -> dict[str, Any]:
    if a.servicio_critico and not a.tiene_workaround:
        p, regla = "P1", "Servicio crítico afectado sin alternativa de trabajo"
    elif a.impacto == "alto" and a.usuarios_afectados >= 100:
        p, regla = "P1", "Impacto alto con 100 o más usuarios afectados"
    elif a.impacto == "alto" or a.servicio_critico or a.usuarios_afectados >= 20:
        p, regla = "P2", "Impacto alto, servicio crítico con workaround o 20+ usuarios afectados"
    elif a.impacto == "medio" or a.usuarios_afectados >= 5:
        p, regla = "P3", "Impacto medio o 5+ usuarios afectados"
    else:
        p, regla = "P4", "Impacto bajo y pocos usuarios afectados"
    return {"prioridad": p, **SLA[p], "regla_aplicada": regla, "fuente": "procedimiento_gestion_solicitudes.md §3"}


# --------------------------------------------------------------------------------------
# 3. Estimar esfuerzo
# --------------------------------------------------------------------------------------
BASE_HORAS = {"correccion": 8, "reporte": 16, "nueva_funcionalidad": 40, "integracion": 60, "migracion": 120}
FACTOR_COMPLEJIDAD = {"baja": 0.75, "media": 1.0, "alta": 1.6}
HORAS_SPRINT = 60  # horas productivas por desarrollador en un sprint de 2 semanas


class EsfuerzoInput(BaseModel):
    tipo: Literal["correccion", "reporte", "nueva_funcionalidad", "integracion", "migracion"]
    complejidad: Literal["baja", "media", "alta"]
    componentes: int = Field(1, ge=1, le=50, description="Número de componentes o sistemas involucrados")
    requiere_migracion_datos: bool = False


def estimar_esfuerzo(_repo, a: EsfuerzoInput) -> dict[str, Any]:
    horas = BASE_HORAS[a.tipo] * FACTOR_COMPLEJIDAD[a.complejidad]
    horas += 8 * (a.componentes - 1)
    if a.requiere_migracion_datos:
        horas *= 1.30
    horas *= 1.15  # contingencia
    horas = round(horas)
    return {
        "horas_estimadas": horas,
        "rango_horas": [round(horas * 0.8), round(horas * 1.2)],
        "sprints_1_dev": math.ceil(horas / HORAS_SPRINT),
        "supuestos": [
            f"Base {BASE_HORAS[a.tipo]} h para '{a.tipo}', factor {FACTOR_COMPLEJIDAD[a.complejidad]} por complejidad {a.complejidad}",
            "+8 h por cada componente adicional",
            "+30 % si hay migración de datos" if a.requiere_migracion_datos else "Sin migración de datos",
            "+15 % de contingencia; rango ±20 %",
        ],
        "fuente": "procedimiento_gestion_solicitudes.md §5",
    }


# --------------------------------------------------------------------------------------
# 4. Servicios cloud sugeridos
# --------------------------------------------------------------------------------------
CATALOGO = {
    "computo_serverless": [("AWS Lambda", "Azure Functions"), ("Amazon API Gateway", "Azure API Management")],
    "contenedores": [("Amazon ECS con Fargate", "Azure Container Apps"), ("Amazon EKS", "Azure Kubernetes Service")],
    "base_datos_relacional": [("Amazon RDS / Aurora PostgreSQL", "Azure Database for PostgreSQL")],
    "base_datos_nosql": [("Amazon DynamoDB", "Azure Cosmos DB")],
    "almacenamiento": [("Amazon S3", "Azure Blob Storage")],
    "mensajeria": [("Amazon SQS / SNS", "Azure Service Bus"), ("Amazon EventBridge", "Azure Event Grid")],
    "ia_generativa": [("Amazon Bedrock", "Azure OpenAI / AI Foundry"), ("Amazon S3 Vectors / OpenSearch", "Azure AI Search")],
    "observabilidad": [("Amazon CloudWatch + X-Ray", "Azure Monitor + Application Insights")],
    "seguridad": [("AWS Secrets Manager / SSM", "Azure Key Vault"), ("AWS WAF", "Azure Front Door WAF"), ("Amazon Cognito", "Microsoft Entra ID")],
    "integracion": [("AWS Step Functions", "Azure Logic Apps")],
}


class ServiciosInput(BaseModel):
    necesidad: Literal[tuple(CATALOGO.keys())]  # type: ignore[valid-type]


def consultar_servicios_cloud(_repo, a: ServiciosInput) -> dict[str, Any]:
    return {
        "necesidad": a.necesidad,
        "servicios": [{"aws": aws, "azure": az} for aws, az in CATALOGO[a.necesidad]],
        "fuente": "catalogo_servicios_cloud.md",
    }


# --------------------------------------------------------------------------------------
# Registro
# --------------------------------------------------------------------------------------
class Tool:
    def __init__(self, spec: ToolSpec, model: type[BaseModel], fn: Callable):
        self.spec, self.model, self.fn = spec, model, fn


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


TOOLS: dict[str, Tool] = {
    t.spec.name: t
    for t in [
        Tool(
            ToolSpec(
                "consultar_estado_solicitud",
                "Consulta el estado, prioridad, responsable e historial de una solicitud interna por su ID (formato SOL-0000). "
                "Úsala cuando el usuario pregunte por una solicitud concreta o pida un resumen ejecutivo de ella.",
                _schema(EstadoInput),
            ),
            EstadoInput,
            consultar_estado_solicitud,
        ),
        Tool(
            ToolSpec(
                "clasificar_prioridad",
                "Clasifica una solicitud o incidente en prioridad P1-P4 y devuelve su SLA, aplicando las reglas del procedimiento interno.",
                _schema(PrioridadInput),
            ),
            PrioridadInput,
            clasificar_prioridad,
        ),
        Tool(
            ToolSpec(
                "estimar_esfuerzo",
                "Calcula el esfuerzo estimado en horas y sprints de un trabajo según reglas simples (tipo, complejidad, componentes, migración de datos).",
                _schema(EsfuerzoInput),
            ),
            EsfuerzoInput,
            estimar_esfuerzo,
        ),
        Tool(
            ToolSpec(
                "consultar_servicios_cloud",
                "Devuelve servicios cloud sugeridos (AWS y su equivalente en Azure) para una necesidad técnica de modernización.",
                _schema(ServiciosInput),
            ),
            ServiciosInput,
            consultar_servicios_cloud,
        ),
    ]
}


def run_tool(name: str, raw_input: dict[str, Any], repo) -> tuple[dict[str, Any], str]:
    """Ejecuta una herramienta de la allowlist. Devuelve (resultado, status)."""
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"Herramienta desconocida: {name}"}, "error"
    try:
        args = tool.model.model_validate(raw_input or {})
    except ValidationError as exc:
        return {"error": "Argumentos inválidos", "detalle": exc.errors(include_url=False, include_context=False)}, "error"
    try:
        return tool.fn(repo, args), "success"
    except Exception as exc:  # noqa: BLE001 - el error vuelve al modelo, no rompe la petición
        return {"error": f"Fallo ejecutando {name}: {type(exc).__name__}"}, "error"
