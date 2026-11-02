"""Carga de documentos y chunking.

Estrategia: *recursive splitting* consciente de la estructura. Primero se respetan
los títulos Markdown (cada fragmento sabe a qué sección pertenece), luego párrafos,
luego oraciones; los fragmentos se empaquetan hasta CHUNK_SIZE caracteres con un
solapamiento de CHUNK_OVERLAP para no cortar ideas en el borde. Es la recomendación
de las arquitecturas de referencia de AWS (chunks de tamaño medio, 10-20 % de overlap).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


@dataclass
class Chunk:
    chunk_id: str
    document: str
    text: str
    section: str = ""
    position: int = 0
    metadata: dict = field(default_factory=dict)


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if lower.endswith((".md", ".txt")):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")
    raise ValueError(f"Formato no soportado: {filename}. Usa {', '.join(sorted(SUPPORTED_EXTENSIONS))}.")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Divide por títulos Markdown y devuelve (ruta_de_sección, contenido)."""
    sections: list[tuple[str, str]] = []
    heading_stack: list[str] = []
    buffer: list[str] = []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections.append((" > ".join(heading_stack), body))
        buffer.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            heading_stack[:] = heading_stack[: level - 1] + [m.group(2).strip()]
        else:
            buffer.append(line)
    flush()
    return sections or [("", text.strip())]


def _split_units(text: str, max_len: int) -> list[str]:
    """Párrafos; si un párrafo es demasiado largo, se parte en oraciones."""
    units = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_len:
            units.append(para)
            continue
        for sent in re.split(r"(?<=[.!?;:])\s+", para):
            while len(sent) > max_len:  # oración gigante: corte duro
                units.append(sent[:max_len])
                sent = sent[max_len:]
            if sent:
                units.append(sent)
    return units


def chunk_text(document: str, text: str, chunk_size: int = 800, overlap: int = 120) -> list[Chunk]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size debe ser mayor que chunk_overlap")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", document)
    chunks: list[Chunk] = []
    for section, body in _split_sections(text):
        current = ""
        for unit in _split_units(body, chunk_size):
            candidate = f"{current}\n\n{unit}".strip() if current else unit
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            chunks.append(Chunk("", document, current, section))
            tail = current[-overlap:]
            # empieza el solape en un límite de palabra
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            current = f"{tail}\n\n{unit}".strip()
        if current:
            chunks.append(Chunk("", document, current, section))
    for i, ch in enumerate(chunks):
        ch.chunk_id = f"{slug}::{i:04d}"
        ch.position = i
    return chunks
