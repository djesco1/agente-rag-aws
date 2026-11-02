"""Carga las solicitudes de ejemplo (data/requests.json) en la tabla DynamoDB.

Uso (CloudShell o tu PC con AWS CLI configurado):
    python3 scripts/seed_requests.py --table ic7-rag-requests
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="ic7-rag-requests")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--file", default=str(ROOT / "data" / "requests.json"))
    args = parser.parse_args()

    items = json.loads(Path(args.file).read_text(encoding="utf-8"), parse_float=Decimal)
    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"{len(items)} solicitudes cargadas en {args.table}")


if __name__ == "__main__":
    main()
