"""API FastAPI del Agente RAG empresarial.

Local:   uvicorn app.main:app --reload   ->  http://localhost:8000/docs
AWS:     handler de Lambda = app.main.handler (Mangum adapta Function URL -> ASGI)
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Security, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.container import get_agent, get_history, get_pipeline
from app.logging_conf import log_event, setup_logging, trace_id_var
from app.providers.base import ProviderError
from app.schemas import AskRequest, AskResponse, DocumentInfo, DocumentIngestResponse, ErrorResponse, HistoryItem
from app.security import api_key_is_valid, get_expected_api_key

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("app")

DESCRIPTION = """
Asistente inteligente para consultar documentación interna, responder con base en fuentes
y ejecutar acciones simples mediante herramientas.

**Autenticación:** envía la cabecera `X-API-Key` (botón *Authorize*).

**Flujo típico:** `POST /documents` (cargar documentos) → `POST /ask` (preguntar) → `GET /history` (trazabilidad).
"""

app = FastAPI(
    title="Agente RAG empresarial — Solicitudes internas",
    version="1.0.0",
    description=DESCRIPTION,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    expected = get_expected_api_key(settings)
    if not expected and settings.app_env != "local":
        # Fail closed: en AWS nunca se expone la API sin key configurada.
        raise HTTPException(status_code=500, detail="API key no configurada en el servidor")
    if not api_key_is_valid(key, expected):
        raise HTTPException(status_code=401, detail="API key inválida o ausente")


# --------------------------------------------------------------------------------------
# Middleware de trazabilidad
# --------------------------------------------------------------------------------------
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    trace_id = incoming if incoming.isalnum() and len(incoming) <= 64 else uuid.uuid4().hex
    token = trace_id_var.set(trace_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        log_event(
            logger,
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return response
    finally:
        trace_id_var.reset(token)


# --------------------------------------------------------------------------------------
# Manejo de errores homogéneo (sin filtrar detalles internos al cliente)
# --------------------------------------------------------------------------------------
def _error(status: int, error: str, detail=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "detail": detail, "trace_id": trace_id_var.get()})


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return _error(exc.status_code, "http_error", exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    details = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
    return _error(422, "validation_error", details)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return _error(400, "bad_request", str(exc))


@app.exception_handler(ProviderError)
async def provider_error_handler(_: Request, exc: ProviderError):
    logger.error("provider_error: %s", exc)
    return _error(502, "model_provider_error", "El servicio de modelos no está disponible. Intenta de nuevo en unos segundos.")


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    logger.exception("unhandled_error")
    return _error(500, "internal_error", "Error interno. Usa el trace_id para revisar los logs.")


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------
@app.get("/health", tags=["operación"], summary="Estado del servicio (sin autenticación)")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model_id,
        "embeddings_provider": settings.embeddings_provider,
        "vector_store": settings.vector_store,
        "storage_backend": settings.storage_backend,
    }


@app.post("/ask", response_model=AskResponse, tags=["asistente"], summary="Preguntar al asistente", dependencies=[Depends(require_api_key)])
def ask(body: AskRequest):
    """Responde con base en los documentos cargados, usando herramientas cuando hace falta.
    Devuelve las fuentes citadas, las herramientas usadas y un `trace_id` para auditoría."""
    if len(body.question) > settings.max_question_chars:
        raise HTTPException(status_code=422, detail=f"La pregunta supera {settings.max_question_chars} caracteres")
    return get_agent().ask(body.question, body.session_id, body.top_k)


@app.post(
    "/documents",
    response_model=DocumentIngestResponse,
    status_code=201,
    tags=["documentos"],
    summary="Cargar y procesar un documento (.md, .txt, .pdf)",
    dependencies=[Depends(require_api_key)],
)
async def upload_document(file: UploadFile = File(...)):
    """Guarda el original, lo divide en fragmentos, genera embeddings y los indexa.
    Volver a cargar un archivo con el mismo nombre reemplaza su versión anterior."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx. {settings.max_upload_bytes} bytes)")
    return get_pipeline().ingest(file.filename or "", data)


@app.get("/documents", response_model=list[DocumentInfo], tags=["documentos"], summary="Listar documentos cargados", dependencies=[Depends(require_api_key)])
def list_documents():
    return get_pipeline().documents.list()


@app.get("/history", response_model=list[HistoryItem], tags=["trazabilidad"], summary="Últimas interacciones", dependencies=[Depends(require_api_key)])
def list_history(limit: int = Query(20, ge=1, le=100), session_id: str | None = Query(None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")):
    return get_history().list(limit, session_id)


@app.get("/history/{trace_id}", response_model=HistoryItem, tags=["trazabilidad"], summary="Detalle de una interacción", dependencies=[Depends(require_api_key)])
def get_history_item(trace_id: str):
    if not trace_id.isalnum() or len(trace_id) > 64:
        raise HTTPException(status_code=422, detail="trace_id inválido")
    item = get_history().get(trace_id)
    if not item:
        raise HTTPException(status_code=404, detail="No existe una interacción con ese trace_id")
    return item


# Handler para AWS Lambda
try:
    from mangum import Mangum

    handler = Mangum(app, lifespan="off")
except ImportError:  # pragma: no cover - mangum solo es necesario en Lambda
    handler = None
