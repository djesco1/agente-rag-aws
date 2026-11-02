#!/usr/bin/env bash
# Empaqueta la Lambda (código + dependencias para Linux x86_64 / Python 3.13).
# Pensado para correr en AWS CloudShell, pero funciona en cualquier Linux/macOS con pip.
# Uso: bash scripts/build_lambda.sh
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build && mkdir -p build/package

python3 -m pip install --upgrade pip --quiet || true
python3 -m pip install -r requirements.txt \
  --target build/package \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --upgrade --quiet

cp -r app build/package/

find build/package -type d -name "__pycache__" -prune -exec rm -rf {} +
# Comprimir con Python (no depende de que exista el comando zip)
python3 - <<'PY'
import os, zipfile
src = "build/package"
with zipfile.ZipFile("build/lambda.zip", "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            zf.write(full, os.path.relpath(full, src))
PY
cd build
echo "Paquete listo: $(pwd)/lambda.zip ($(du -h lambda.zip | cut -f1))"
