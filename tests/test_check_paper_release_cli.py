import json
import os
import subprocess
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]


def test_cli_readiness_funciona_ejecutado_desde_raiz(tmp_path):
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'readiness.db'}",
        "TRADING_MODE": "PAPER",
        "ALLOW_LIVE_TRADING": "",
        "INITIAL_CAPITAL_USD": "500",
        "LIMITE_ASIGNACION_POR_OPERACION": "0.02",
        "MAX_DAILY_LOSS_USDT": "20",
        "SECRET_KEY": "test-only-readiness-secret-key",
        "DECISION_ENGINE": "SAFE_NO_TRADE",
        "CORS_ORIGINS": "http://localhost:5173",
    })

    proc = subprocess.run(
        [sys.executable, "scripts/check_paper_release.py"],
        cwd=RAIZ,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    # La BD temporal no está migrada: NOT_READY/exit 2 es correcto. Lo que se
    # congela aquí es que el CLI directo importe backend y produzca JSON.
    assert proc.returncode == 2, proc.stderr
    assert "ModuleNotFoundError" not in proc.stderr
    resultado = json.loads(proc.stdout)
    assert resultado["release"] == "PAPER_V1"
    assert resultado["status"] == "NOT_READY"
    alembic = next(c for c in resultado["checks"] if c["codigo"] == "ALEMBIC")
    assert alembic["nivel"] == "BLOCKER"
