"""Vector stores: local (archivo JSON) y Amazon S3 Vectors.

S3 Vectors se eligió para AWS porque se paga por uso (sin cluster encendido) y
encaja en el presupuesto de una prueba; OpenSearch Serverless cobra capacidad
mínima aunque no se use. Ver docs/DECISIONES_TECNICAS.md.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.rag.chunking import Chunk


@dataclass
class Hit:
    chunk_id: str
    document: str
    section: str
    text: str
    score: float  # similitud coseno (1 = idéntico)
    flagged: bool = False


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[Hit]: ...
    def delete_document(self, document: str) -> int: ...


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class LocalVectorStore:
    """Búsqueda exacta (fuerza bruta) persistida en JSON. Suficiente para cientos de
    fragmentos; para más volumen se usa S3 Vectors / OpenSearch."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        if path.exists():
            self._items = json.loads(path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._items, ensure_ascii=False), encoding="utf-8")

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        with self._lock:
            for ch, vec in zip(chunks, vectors):
                self._items[ch.chunk_id] = {
                    "vector": vec,
                    "document": ch.document,
                    "section": ch.section,
                    "text": ch.text,
                    "flagged": bool(ch.metadata.get("flagged")),
                }
            self._save()

    def query(self, vector: list[float], top_k: int) -> list[Hit]:
        scored = [
            Hit(cid, it["document"], it["section"], it["text"], _cosine(vector, it["vector"]), it.get("flagged", False))
            for cid, it in self._items.items()
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def delete_document(self, document: str) -> int:
        with self._lock:
            keys = [k for k, v in self._items.items() if v["document"] == document]
            for k in keys:
                del self._items[k]
            self._save()
            return len(keys)

    def count(self) -> int:
        return len(self._items)


class S3VectorStore:
    """Amazon S3 Vectors. El índice debe crearse con métrica coseno, dimensión igual
    a EMBEDDINGS_DIMENSION y claves de metadata no filtrables: text, section."""

    def __init__(self, bucket: str, index: str, region: str):
        import boto3

        if not bucket:
            raise ValueError("VECTOR_BUCKET no está configurado")
        self.bucket = bucket
        self.index = index
        self._client = boto3.client("s3vectors", region_name=region)

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        items = [
            {
                "key": ch.chunk_id,
                "data": {"float32": [float(x) for x in vec]},
                "metadata": {
                    "document": ch.document,
                    "section": ch.section[:500] or "-",
                    "text": ch.text,
                    "flagged": bool(ch.metadata.get("flagged")),
                },
            }
            for ch, vec in zip(chunks, vectors)
        ]
        for i in range(0, len(items), 100):  # lotes (límite del API: 500 por llamada)
            self._client.put_vectors(vectorBucketName=self.bucket, indexName=self.index, vectors=items[i:i + 100])

    def query(self, vector: list[float], top_k: int) -> list[Hit]:
        resp = self._client.query_vectors(
            vectorBucketName=self.bucket,
            indexName=self.index,
            queryVector={"float32": [float(x) for x in vector]},
            topK=top_k,
            returnMetadata=True,
            returnDistance=True,
        )
        hits = []
        for v in resp.get("vectors", []):
            md = v.get("metadata", {}) or {}
            # Con métrica coseno, S3 Vectors devuelve distancia = 1 - similitud.
            score = 1.0 - float(v.get("distance", 1.0))
            section = md.get("section", "")
            hits.append(Hit(v["key"], md.get("document", ""), "" if section == "-" else section, md.get("text", ""), score, bool(md.get("flagged", False))))
        return hits

    def delete_document(self, document: str) -> int:
        keys, token = [], None
        while True:
            kwargs = {"vectorBucketName": self.bucket, "indexName": self.index, "returnMetadata": True, "maxResults": 500}
            if token:
                kwargs["nextToken"] = token
            resp = self._client.list_vectors(**kwargs)
            keys += [v["key"] for v in resp.get("vectors", []) if (v.get("metadata") or {}).get("document") == document]
            token = resp.get("nextToken")
            if not token:
                break
        for i in range(0, len(keys), 500):
            self._client.delete_vectors(vectorBucketName=self.bucket, indexName=self.index, keys=keys[i:i + 500])
        return len(keys)
