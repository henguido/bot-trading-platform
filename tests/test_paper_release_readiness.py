from types import SimpleNamespace

from backend.release_readiness import evaluar, resumen_publico


FEE_ENV = {
    "RESEARCH_TAKER_FEE_BPS": "10.0",
    "RESEARCH_TAKER_FEE_SOURCE": "manual:test",
    "RESEARCH_TAKER_FEE_VERIFIED_AT": "2026-09-04T18:47:00Z",
}


def _config(**overrides):
    base = dict(
        MODO_REAL=False,
        TRADING_MODE="PAPER",
        INITIAL_CAPITAL_USD=500.0,
        LIMITE_ASIGNACION_POR_OPERACION=0.02,
        MAX_DAILY_LOSS_USDT=20.0,
        DECISION_ENGINE="SAFE_NO_TRADE",
        OPENAI_API_KEY=None,
        BINANCE_API_KEY="synthetic",
        BINANCE_API_SECRET="synthetic",
        CORS_ORIGINS=("http://localhost:5173",),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _schema(ok=True):
    return SimpleNamespace(
        alineado=ok,
        estado="OK" if ok else "SCHEMA_MIGRATION_REQUIRED",
        revision_actual="0007_decision_cycle_audit" if ok else "0006_paper_ledger",
        revision_esperada="0007_decision_cycle_audit",
    )


def _env(*, kill_switch=True, fee=True):
    env = {}
    if kill_switch:
        env["MAX_DAILY_LOSS_USDT"] = "20"
    if fee:
        env.update(FEE_ENV)
    return env


def test_release_ready_con_paper_seguro_y_config_explicita():
    from datetime import datetime, timezone

    r = evaluar(
        _config(),
        _schema(),
        profitability_gate_enabled=False,
        environ=_env(),
        now=datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc),
    )
    assert r["ready"] is True
    assert r["status"] == "READY"
    assert r["blockers"] == 0
    assert r["warnings"] == 0
    assert r["fee_evidence"]["status"] == "VERIFICADA"
    assert r["fee_evidence"]["bps_per_side"] == 10.0


def test_release_bloquea_capital_distinto_al_baseline_paper_v1():
    r = evaluar(
        _config(INITIAL_CAPITAL_USD=20.0),
        _schema(),
        profitability_gate_enabled=False,
        environ=_env(),
    )
    assert r["ready"] is False
    capital = next(c for c in r["checks"] if c["codigo"] == "CAPITAL_PAPER")
    assert capital["nivel"] == "BLOCKER"
    assert "20.00" in capital["detalle"]
    assert "500.00" in capital["detalle"]


def test_release_bloquea_live_gate_no_promovido_y_asignacion_mayor_a_2pct():
    r = evaluar(
        _config(MODO_REAL=True, TRADING_MODE="LIVE", LIMITE_ASIGNACION_POR_OPERACION=0.03),
        _schema(),
        profitability_gate_enabled=True,
        environ=_env(),
    )
    assert r["ready"] is False
    codigos = {c["codigo"] for c in r["checks"] if c["nivel"] == "BLOCKER"}
    assert {"MODO_PAPER", "ASIGNACION", "PROFITABILITY_GATE_05E"} <= codigos


def test_gpt_sin_api_key_y_binance_sin_fee_source_son_blockers():
    r = evaluar(
        _config(DECISION_ENGINE="GPT", BINANCE_API_KEY=None, BINANCE_API_SECRET=None),
        _schema(),
        profitability_gate_enabled=False,
        environ=_env(fee=False),
    )
    codigos = {c["codigo"] for c in r["checks"] if c["nivel"] == "BLOCKER"}
    assert "DECISION_ENGINE" in codigos
    assert "BINANCE_FEE_SOURCE" in codigos


def test_default_de_perdida_diaria_es_warning_no_falso_ready_blocker():
    from datetime import datetime, timezone

    r = evaluar(
        _config(),
        _schema(),
        profitability_gate_enabled=False,
        environ=_env(kill_switch=False),
        now=datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc),
    )
    assert r["ready"] is True
    assert r["warnings"] == 1
    warning = [c for c in r["checks"] if c["nivel"] == "WARN"][0]
    assert warning["codigo"] == "KILL_SWITCH_EXPLICITO"


def test_schema_desalineado_bloquea_release():
    r = evaluar(
        _config(),
        _schema(ok=False),
        profitability_gate_enabled=False,
        environ=_env(),
    )
    assert r["ready"] is False
    assert any(c["codigo"] == "ALEMBIC" and c["nivel"] == "BLOCKER" for c in r["checks"])


def test_resumen_publico_no_expone_detalle_de_checks_ni_secretos():
    completo = evaluar(
        _config(DECISION_ENGINE="GPT", OPENAI_API_KEY=None,
                BINANCE_API_KEY=None, BINANCE_API_SECRET=None),
        _schema(),
        profitability_gate_enabled=False,
        environ=_env(fee=False),
    )
    publico = resumen_publico(completo)

    assert publico == {
        "release": "PAPER_V1",
        "ready": False,
        "status": "NOT_READY",
        "blockers": completo["blockers"],
        "warnings": completo["warnings"],
        "fee": {
            "status": "NO_DISPONIBLE",
            "source": None,
            "bps_per_side": None,
            "verified_at": None,
            "age_seconds": None,
            "max_age_seconds": 604800,
        },
    }
    assert "checks" not in publico
    texto = repr(publico)
    assert "OPENAI" not in texto
    assert "BINANCE_FEE_SOURCE" not in texto
