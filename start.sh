#!/usr/bin/env bash
set -euo pipefail

# Arranque backend production-like desde la raiz real del repositorio.
#
# - un solo worker: evita multiplicar procesos de trading;
# - sin recarga automatica: no respawnea el proceso operativo;
# - no aplica migraciones automaticamente: Alembic sigue siendo una operacion
#   explicita de despliegue (`alembic upgrade head`);
# - cualquier arranque que NO sea LIVE explicitamente autorizado ejecuta el
#   preflight PAPER de solo lectura antes de exponer la app;
# - PORT puede ser inyectado por cualquier plataforma; local usa 8000.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${API_HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
MODE="${TRADING_MODE:-PAPER}"
LIVE_OPT_IN="${ALLOW_LIVE_TRADING:-}"

MODE_UPPER="${MODE^^}"
LIVE_OPT_IN_LOWER="${LIVE_OPT_IN,,}"

# settings.py solo considera LIVE real cuando existen las DOS señales:
# TRADING_MODE=LIVE + ALLOW_LIVE_TRADING=yes-i-understand-the-risk.
# Si alguien deja TRADING_MODE=LIVE sin el opt-in, settings fuerza PAPER. Antes
# start.sh saltaba el readiness por mirar solo TRADING_MODE y podia arrancar un
# PAPER forzado sin preflight. Ahora ese caso falla cerrado mediante el mismo
# readiness de PAPER.
if [ "$MODE_UPPER" != "LIVE" ] || [ "$LIVE_OPT_IN_LOWER" != "yes-i-understand-the-risk" ]; then
  echo "[START] Verificando readiness PAPER v1..."
  python scripts/check_paper_release.py
fi

echo "[START] BOT Trading Platform backend ${HOST}:${PORT} modo=${MODE_UPPER}"
exec python -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --workers 1
