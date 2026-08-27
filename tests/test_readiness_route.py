from types import SimpleNamespace

from backend.routes import binance_routes


def test_readiness_route_devuelve_solo_resumen_publico(monkeypatch):
    esquema = SimpleNamespace(
        alineado=False,
        estado="SCHEMA_MIGRATION_REQUIRED",
        revision_actual="0006_paper_ledger",
        revision_esperada="0007_decision_cycle_audit",
    )
    completo = {
        "release": "PAPER_V1",
        "ready": False,
        "status": "NOT_READY",
        "blockers": 2,
        "warnings": 1,
        "checks": [
            {"codigo": "BINANCE_FEE_SOURCE", "nivel": "BLOCKER", "detalle": "sensible"},
            {"codigo": "DECISION_ENGINE", "nivel": "BLOCKER", "detalle": "sensible"},
        ],
    }

    monkeypatch.setattr(binance_routes, "estado_esquema", lambda: esquema)
    monkeypatch.setattr(
        binance_routes,
        "evaluar_readiness",
        lambda config, estado, profitability_gate_enabled: completo,
    )

    resultado = binance_routes.get_paper_readiness(
        current_user=SimpleNamespace(id=123)
    )

    assert resultado == {
        "release": "PAPER_V1",
        "ready": False,
        "status": "NOT_READY",
        "blockers": 2,
        "warnings": 1,
    }
    assert "checks" not in resultado
    assert "BINANCE_FEE_SOURCE" not in repr(resultado)
