#!/usr/bin/env bash
set -euo pipefail

# Arranque backend production-like desde la raiz real del repositorio.
#
# - un solo worker: evita multiplicar procesos de trading;
# - sin recarga automatica: no respawnea el proceso operativo;
# - no aplica migraciones automaticamente: Alembic sigue siendo una operacion
#   explicita de despliegue (`alembic upgrade head`);
# - PORT puede ser inyectado por cualquier plataforma; local usa 8000.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${API_HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[START] BOT Trading Platform backend ${HOST}:${PORT}"
exec python -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --workers 1
