"""Persistencia: documentos (S3 / disco), historial (DynamoDB / JSONL) y
solicitudes mock (DynamoDB / JSON). Cada repositorio tiene versión local y AWS
con la misma interfaz."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------------------
# Documentos originales
# --------------------------------------------------------------------------------------
class LocalDocumentStore:
    def __init__(self, base: Path):
        self.base = base / "documents"
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, data: bytes) -> str:
        path = self.base / name
        path.write_bytes(data)
        return f"file://{path}"

    def list(self) -> list[dict[str, Any]]:
        return [{"document": p.name, "size_bytes": p.stat().st_size} for p in sorted(self.base.iterdir()) if p.is_file()]


class S3DocumentStore:
    def __init__(self, bucket: str, region: str, prefix: str = "documents/"):
        import boto3

        if not bucket:
            raise ValueError("DOCS_BUCKET no está configurado")
        self.bucket, self.prefix = bucket, prefix
        self._s3 = boto3.client("s3", region_name=region)

    def save(self, name: str, data: bytes) -> str:
        key = f"{self.prefix}{name}"
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return f"s3://{self.bucket}/{key}"

    def list(self) -> list[dict[str, Any]]:
        resp = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        return [
            {"document": o["Key"][len(self.prefix):], "size_bytes": o["Size"], "last_modified": o["LastModified"].isoformat()}
            for o in resp.get("Contents", [])
            if not o["Key"].endswith("/")
        ]


# --------------------------------------------------------------------------------------
# Historial / trazabilidad
# --------------------------------------------------------------------------------------
# Campos con estructuras anidadas se guardan como JSON string (evita problemas de
# float/Decimal en DynamoDB y mantiene el item simple).
_JSON_FIELDS = ("sources", "tool_calls", "usage")


class LocalHistoryStore:
    def __init__(self, base: Path):
        self.path = base / "history.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def put(self, item: dict[str, Any]) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def list(self, limit: int = 20, session_id: str | None = None) -> list[dict[str, Any]]:
        items = self._all()
        if session_id:
            items = [i for i in items if i.get("session_id") == session_id]
        return list(reversed(items))[:limit]

    def get(self, trace_id: str) -> dict[str, Any] | None:
        return next((i for i in self._all() if i["trace_id"] == trace_id), None)


class DynamoHistoryStore:
    """Tabla con clave de partición `pk` (String) y de orden `sk` (String).

    pk = "HISTORY", sk = "<timestamp ISO>#<trace_id>" -> consultas "las últimas N"
    ordenadas por tiempo con un solo Query. Para alto volumen se usaría una
    partición por día o un GSI (ver docs/RIESGOS_Y_PRODUCCION.md).
    """

    def __init__(self, table: str, region: str):
        import boto3

        if not table:
            raise ValueError("HISTORY_TABLE no está configurado")
        self._table = boto3.resource("dynamodb", region_name=region).Table(table)

    @staticmethod
    def _encode(item: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in item.items() if v is not None}
        for f in _JSON_FIELDS:
            if f in out:
                out[f] = json.dumps(out[f], ensure_ascii=False)
        if "latency_ms" in out:
            out["latency_ms"] = int(out["latency_ms"])
        return out

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        out = dict(item)
        for f in _JSON_FIELDS:
            if isinstance(out.get(f), str):
                out[f] = json.loads(out[f])
        if "latency_ms" in out:
            out["latency_ms"] = int(out["latency_ms"])
        out.pop("pk", None)
        out.pop("sk", None)
        return out

    def put(self, item: dict[str, Any]) -> None:
        record = self._encode(item)
        record["pk"] = "HISTORY"
        record["sk"] = f"{item['timestamp']}#{item['trace_id']}"
        self._table.put_item(Item=record)

    def list(self, limit: int = 20, session_id: str | None = None) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Attr, Key

        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq("HISTORY"), "ScanIndexForward": False, "Limit": limit}
        if session_id:
            kwargs["FilterExpression"] = Attr("session_id").eq(session_id)
            kwargs["Limit"] = max(limit * 5, 50)
        resp = self._table.query(**kwargs)
        return [self._decode(i) for i in resp.get("Items", [])][:limit]

    def get(self, trace_id: str) -> dict[str, Any] | None:
        from boto3.dynamodb.conditions import Attr, Key

        resp = self._table.query(
            KeyConditionExpression=Key("pk").eq("HISTORY"),
            FilterExpression=Attr("trace_id").eq(trace_id),
            ScanIndexForward=False,
        )
        items = resp.get("Items", [])
        return self._decode(items[0]) if items else None


# --------------------------------------------------------------------------------------
# Solicitudes internas (datos mock que consulta la herramienta del agente)
# --------------------------------------------------------------------------------------
class JsonRequestsRepo:
    def __init__(self, seed_file: Path):
        self._data = {r["request_id"]: r for r in json.loads(seed_file.read_text(encoding="utf-8"))}

    def get(self, request_id: str) -> dict[str, Any] | None:
        return self._data.get(request_id)


class DynamoRequestsRepo:
    """Tabla con clave de partición `request_id` (String)."""

    def __init__(self, table: str, region: str):
        import boto3

        if not table:
            raise ValueError("REQUESTS_TABLE no está configurado")
        self._table = boto3.resource("dynamodb", region_name=region).Table(table)

    def get(self, request_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"request_id": request_id}).get("Item")
        if item:
            # Decimal -> int/float para serializar a JSON
            item = json.loads(json.dumps(item, default=lambda d: int(d) if d == int(d) else float(d)))
        return item
