"""Pipeline RAG: ingesta (extraer -> chunking -> embeddings -> vector store) y
recuperación (embedding de la pregunta -> top-k -> filtro por umbral)."""
from __future__ import annotations

import logging
import re

from app.logging_conf import log_event
from app.rag.chunking import SUPPORTED_EXTENSIONS, chunk_text, extract_text
from app.rag.vectorstore import Hit
from app.security import detect_prompt_injection

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,120}$")


def validate_filename(name: str) -> str:
    name = name.strip().replace("\\", "/").split("/")[-1]  # sin rutas (path traversal)
    if not _SAFE_NAME.match(name):
        raise ValueError("Nombre de archivo inválido: usa letras, números, espacios, . _ - ( )")
    if not any(name.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise ValueError(f"Extensión no soportada. Permitidas: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    return name


class RagPipeline:
    def __init__(self, settings, embeddings, vector_store, document_store):
        self.s = settings
        self.embeddings = embeddings
        self.vectors = vector_store
        self.documents = document_store

    def ingest(self, filename: str, data: bytes) -> dict:
        name = validate_filename(filename)
        if len(data) > self.s.max_upload_bytes:
            raise ValueError(f"Archivo demasiado grande (máx. {self.s.max_upload_bytes} bytes)")
        text = extract_text(name, data)
        if len(text.strip()) < 20:
            raise ValueError("El documento no contiene texto extraíble")

        chunks = chunk_text(name, text, self.s.chunk_size, self.s.chunk_overlap)
        flagged = 0
        for ch in chunks:
            # Indirect prompt injection: se marca el fragmento para que el prompt lo
            # trate como sospechoso y quede trazado en logs.
            hits = detect_prompt_injection(ch.text)
            if hits:
                ch.metadata["flagged"] = True
                flagged += 1
                log_event(logger, "chunk_flagged", logging.WARNING, chunk_id=ch.chunk_id, categories=hits)

        vectors = self.embeddings.embed([f"{ch.section}\n{ch.text}" if ch.section else ch.text for ch in chunks])
        removed = self.vectors.delete_document(name)  # re-ingesta idempotente
        self.vectors.upsert(chunks, vectors)
        uri = self.documents.save(name, data)
        log_event(logger, "document_ingested", document=name, chunks=len(chunks), replaced=removed, flagged=flagged)
        return {"document": name, "chunks": len(chunks), "characters": len(text), "flagged_chunks": flagged, "storage_uri": uri}

    def retrieve(self, question: str, top_k: int | None = None) -> tuple[list[Hit], list[Hit]]:
        """Devuelve (fragmentos relevantes sobre el umbral, todos los candidatos)."""
        k = top_k or self.s.top_k
        qvec = self.embeddings.embed([question])[0]
        candidates = self.vectors.query(qvec, k)
        relevant = [h for h in candidates if h.score >= self.s.min_relevance]
        log_event(
            logger,
            "retrieval",
            top_k=k,
            candidates=[{"chunk_id": h.chunk_id, "score": round(h.score, 3)} for h in candidates],
            relevant=len(relevant),
        )
        return relevant, candidates
