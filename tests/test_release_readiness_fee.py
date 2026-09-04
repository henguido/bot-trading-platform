from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.release_readiness import evaluar, resumen_publico


NOW = datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)


def _config(*, con_credenciales=False):
    return SimpleNamespace(
        MODO_REAL=False,
        TRADING_MODE="PAPER",
        INITIAL_CAPITAL_USD=500.0,
        LIMITE_ASIGNACION_POR_OPERACION=0.02,
        MAX_DAILY_LOSS_USDT=25.0,
        DECISION_ENGINE="SAFE_NO_TRADE",
        OPENAI_API_KEY=None,
        BINANCE_API_KEY="key-sintetica" if con_credenciales else "",
        BINANCE_API_SECRET="secret-sintetico" if con_credenciales else "",
        CORS_ORIGINS=("http://localhost:5173",),
    )


def _esquema():
    return SimpleNamespace(
        alineado=True,
        revision_actual="0007_decision_cycle_audit",
        revision_esperada="0007_decision_cycle_audit",
        estado="ALINEADO",
    )


def _env_fee(fecha):
    return {
        "MAX_DAILY_LOSS_USDT": "25",
        "RESEARCH_TAKER_FEE_BPS": "10.0",
        "RESEARCH_TAKER_FEE_SOURCE": "manual:binance_account.commissionRates.taker",
        "RESEARCH_TAKER_FEE_VERIFIED_AT": fecha.isoformat().replace("+00:00", "Z"),
    }


def test_readiness_acepta_fee_manual_verificada_y_la_expone_sin_secretos():
    resultado = evaluar(
        _config(),
        _esquema(),
        profitability_gate_enabled=False,
        environ=_env_fee(NOW - timedelta(hours=2)),
        now=NOW,
    )

    assert resultado["ready"] is True
    assert resultado["fee_evidence"]["status"] == "VERIFICADA"
    assert resultado["fee_evidence"]["bps_per_side"] == 10.0
    assert resultado["fee_evidence"]["source"] == "MANUAL_VERIFIED"
    assert resultado["fee_evidence"]["age_seconds"] == 7200.0

    publico = resumen_publico(resultado)
    assert publico["fee"]["status"] == "VERIFICADA"
    assert publico["fee"]["bps_per_side"] == 10.0
    assert publico["fee"]["source"] == "MANUAL_VERIFIED"
    assert "commissionRates" not in str(publico)
    assert "key-sintetica" not in str(publico)
    assert "secret-sintetico" not in str(publico)


def test_readiness_bloquea_fee_manual_vencida():
    resultado = evaluar(
        _config(),
        _esquema(),
        profitability_gate_enabled=False,
        environ=_env_fee(NOW - timedelta(days=8)),
        now=NOW,
    )

    assert resultado["ready"] is False
    assert resultado["fee_evidence"]["status"] == "VENCIDA"
    check = next(c for c in resultado["checks"] if c["codigo"] == "BINANCE_FEE_SOURCE")
    assert check["nivel"] == "BLOCKER"


def test_credenciales_solas_no_se_confunden_con_fee_verificada():
    resultado = evaluar(
        _config(con_credenciales=True),
        _esquema(),
        profitability_gate_enabled=False,
        environ={"MAX_DAILY_LOSS_USDT": "25"},
        now=NOW,
    )

    assert resultado["ready"] is True
    assert resultado["fee_evidence"]["status"] == "CUENTA_DISPONIBLE_SIN_VERIFICAR"
    assert resultado["fee_evidence"]["bps_per_side"] is None
    check = next(c for c in resultado["checks"] if c["codigo"] == "BINANCE_FEE_SOURCE")
    assert check["nivel"] == "WARN"


def test_sin_fee_ni_credenciales_permanece_fail_closed():
    resultado = evaluar(
        _config(),
        _esquema(),
        profitability_gate_enabled=False,
        environ={"MAX_DAILY_LOSS_USDT": "25"},
        now=NOW,
    )

    assert resultado["ready"] is False
    assert resultado["fee_evidence"]["status"] == "NO_DISPONIBLE"
    check = next(c for c in resultado["checks"] if c["codigo"] == "BINANCE_FEE_SOURCE")
    assert check["nivel"] == "BLOCKER"
