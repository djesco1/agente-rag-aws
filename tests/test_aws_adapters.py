"""Valida los adaptadores AWS contra los modelos de servicio oficiales de botocore.

botocore.Stubber rechaza cualquier parámetro que no exista en el API real, así que
estas pruebas detectan nombres de parámetros inventados o mal formados sin llamar a AWS.
"""
import io
import json

from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.providers.base import ToolSpec
from app.providers.bedrock import BedrockEmbeddings, BedrockLLM
from app.rag.chunking import Chunk
from app.rag.vectorstore import S3VectorStore


def test_bedrock_converse_tool_use_loop():
    llm = BedrockLLM("us.amazon.nova-lite-v1:0", "us-east-1")
    tools = [ToolSpec("consultar_estado_solicitud", "desc", {"type": "object", "properties": {"request_id": {"type": "string"}}, "required": ["request_id"]})]
    with Stubber(llm._client) as stub:
        stub.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "consultar_estado_solicitud", "input": {"request_id": "SOL-1001"}}}]}},
                "stopReason": "tool_use",
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                "metrics": {"latencyMs": 100},
            },
            {"modelId": "us.amazon.nova-lite-v1:0", "system": ANY, "messages": ANY, "inferenceConfig": ANY, "toolConfig": ANY},
        )
        resp = llm.chat("sys", [{"role": "user", "content": [{"type": "text", "text": "estado SOL-1001"}]}], tools)
        assert resp.tool_calls[0].input == {"request_id": "SOL-1001"}

        # Segundo turno: el resultado de la herramienta vuelve al modelo (Nova: sin campo status)
        stub.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": [{"text": "Está En desarrollo."}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
                "metrics": {"latencyMs": 100},
            },
            {"modelId": "us.amazon.nova-lite-v1:0", "system": ANY, "messages": ANY, "inferenceConfig": ANY, "toolConfig": ANY},
        )
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "estado SOL-1001"}]},
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": [{"type": "tool_result", "id": "t1", "content": {"estado": "En desarrollo"}, "status": "success"}]},
        ]
        final = llm.chat("sys", messages, tools)
        assert final.text == "Está En desarrollo." and final.usage["input_tokens"] == 20


def test_bedrock_titan_embeddings():
    emb = BedrockEmbeddings("amazon.titan-embed-text-v2:0", "us-east-1", 1024)
    payload = json.dumps({"embedding": [0.1] * 1024}).encode()
    with Stubber(emb._client) as stub:
        stub.add_response(
            "invoke_model",
            {"body": StreamingBody(io.BytesIO(payload), len(payload)), "contentType": "application/json"},
            {"modelId": "amazon.titan-embed-text-v2:0", "body": ANY, "contentType": "application/json", "accept": "application/json"},
        )
        assert len(emb.embed(["hola"])[0]) == 1024


def test_s3vectors_put_query_delete():
    store = S3VectorStore("ic7-rag-vectors-123", "docs-index", "us-east-1")
    chunk = Chunk("doc.md::0000", "doc.md", "texto", "", 0, {"flagged": False})
    with Stubber(store._client) as stub:
        stub.add_response("put_vectors", {}, {"vectorBucketName": "ic7-rag-vectors-123", "indexName": "docs-index", "vectors": ANY})
        store.upsert([chunk], [[0.5] * 4])

        stub.add_response(
            "query_vectors",
            {"vectors": [{"key": "doc.md::0000", "distance": 0.25, "metadata": {"document": "doc.md", "section": "-", "text": "texto", "flagged": False}}], "distanceMetric": "cosine"},
            {"vectorBucketName": "ic7-rag-vectors-123", "indexName": "docs-index", "queryVector": {"float32": [0.5] * 4}, "topK": 3, "returnMetadata": True, "returnDistance": True},
        )
        hits = store.query([0.5] * 4, 3)
        assert hits[0].score == 0.75 and hits[0].section == ""

        stub.add_response(
            "list_vectors",
            {"vectors": [{"key": "doc.md::0000", "metadata": {"document": "doc.md"}}, {"key": "otro::0000", "metadata": {"document": "otro"}}]},
            {"vectorBucketName": "ic7-rag-vectors-123", "indexName": "docs-index", "returnMetadata": True, "maxResults": 500},
        )
        stub.add_response("delete_vectors", {}, {"vectorBucketName": "ic7-rag-vectors-123", "indexName": "docs-index", "keys": ["doc.md::0000"]})
        assert store.delete_document("doc.md") == 1


def test_dynamo_history_put_list_get():
    from app.storage.repositories import DynamoHistoryStore

    store = DynamoHistoryStore("ic7-rag-history", "us-east-1")
    client = store._table.meta.client
    item = {
        "trace_id": "abc123", "timestamp": "2026-10-31T19:00:00.000+00:00", "session_id": None,
        "question": "¿SLA P2?", "answer": "1 día hábil [1]", "grounded": True, "guardrail": None,
        "sources": [{"ref": 1, "score": 0.61}], "tool_calls": [], "model_id": "m", "latency_ms": 1200, "usage": {"input_tokens": 1},
    }
    stored = {
        "pk": {"S": "HISTORY"}, "sk": {"S": "2026-10-31T19:00:00.000+00:00#abc123"}, "trace_id": {"S": "abc123"},
        "timestamp": {"S": item["timestamp"]}, "question": {"S": item["question"]}, "answer": {"S": item["answer"]},
        "grounded": {"BOOL": True}, "sources": {"S": json.dumps(item["sources"])}, "tool_calls": {"S": "[]"},
        "model_id": {"S": "m"}, "latency_ms": {"N": "1200"}, "usage": {"S": json.dumps(item["usage"])},
    }
    with Stubber(client) as stub:
        # El Stubber del recurso ve los parámetros en tipos Python (antes de serializar)
        expected_item = {
            "pk": "HISTORY", "sk": "2026-10-31T19:00:00.000+00:00#abc123", "trace_id": "abc123",
            "timestamp": item["timestamp"], "question": item["question"], "answer": item["answer"], "grounded": True,
            "sources": json.dumps(item["sources"]), "tool_calls": "[]", "model_id": "m", "latency_ms": 1200,
            "usage": json.dumps(item["usage"]),
        }
        stub.add_response("put_item", {}, {"TableName": "ic7-rag-history", "Item": expected_item})
        store.put(item)
        stub.add_response("query", {"Items": [stored]}, {"TableName": "ic7-rag-history", "KeyConditionExpression": ANY, "ScanIndexForward": False, "Limit": 5})
        out = store.list(5)
        assert out[0]["sources"][0]["score"] == 0.61 and out[0]["latency_ms"] == 1200 and "pk" not in out[0]


def test_dynamo_requests_repo_decimal():
    from app.storage.repositories import DynamoRequestsRepo

    repo = DynamoRequestsRepo("ic7-rag-requests", "us-east-1")
    with Stubber(repo._table.meta.client) as stub:
        stub.add_response(
            "get_item",
            {"Item": {"request_id": {"S": "SOL-1001"}, "usuarios_afectados": {"N": "45"}, "estado": {"S": "En desarrollo"}}},
            {"TableName": "ic7-rag-requests", "Key": {"request_id": "SOL-1001"}},
        )
        item = repo.get("SOL-1001")
        assert item["usuarios_afectados"] == 45 and isinstance(item["usuarios_afectados"], int)


def test_s3_document_store():
    from app.storage.repositories import S3DocumentStore

    store = S3DocumentStore("ic7-rag-docs-123", "us-east-1")
    with Stubber(store._s3) as stub:
        stub.add_response("put_object", {}, {"Bucket": "ic7-rag-docs-123", "Key": "documents/a.md", "Body": b"hola", "ServerSideEncryption": "AES256"})
        assert store.save("a.md", b"hola") == "s3://ic7-rag-docs-123/documents/a.md"
