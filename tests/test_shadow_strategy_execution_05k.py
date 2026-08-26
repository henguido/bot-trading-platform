from datetime import datetime, timedelta, timezone

import pytest

from scripts import shadow_strategy_execution_05k as s


class BinanceFalso:
    def __init__(self):
        self.precio = 100.0
        self.calls = []

    def get_order_book(self, symbol, *, limit=100):
        self.calls.append((symbol, limit, self.precio))
        return {
            "asks": [[str(self.precio), "1000"]],
            "bids": [[str(self.precio), "1000"]],
        }


def estado_05i(observed_at):
    bucket = observed_at.replace(minute=0, second=0, microsecond=0).isoformat()
    observations = []
    for rank in range(1, 21):
        # Todas las features mantienen el mismo orden para que base/challenger
        # compartan Top-5 en esta prueba; la comparación debe dar diferencia 0.
        f = 1.0 - (rank - 1) / 20.0
        observations.append({
            "run_bucket": bucket,
            "observed_at": observed_at.isoformat(),
            "due_at": (observed_at + timedelta(hours=4)).isoformat(),
            "symbol": f"S{rank:02d}USDT",
            "rank": rank,
            "entry_price": 100.0,
            "score": f,
            "features": {
                "estrechez": f,
                "recorrido": f,
                "liquidez": f,
                "actividad": f,
                "momentum": f,
            },
            "fee_taker_bps_por_lado": 10.0,
        })
    return {
        "last_run_bucket": bucket,
        "observations": observations,
    }


def test_bucket_fresco_se_ejecuta_y_cierra_con_pnl_neto():
    observed = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    now = observed + timedelta(seconds=30)
    source = estado_05i(observed)
    state = s.nuevo_estado(500.0)
    binance = BinanceFalso()

    abiertas, cerradas, resumen = s.procesar(source, state, binance, now)

    assert abiertas == 10  # cinco por cada cartera virtual independiente
    assert cerradas == 0
    assert resumen["processed_buckets"] == 1
    assert resumen["paired_complete_buckets"] == 0
    # Como ambas carteras eligen los mismos cinco símbolos, el book se reutiliza.
    assert len(binance.calls) == 5

    base = state["portfolios"][s.PORTFOLIO_BASE]
    assert len(base["open_positions"]) == 5
    assert base["open_positions"][0]["entry_quote_net"] <= 10.0 + 1e-9
    assert base["open_positions"][1]["entry_quote_net"] < base["open_positions"][0]["entry_quote_net"]
    assert base["capital_usd"] < 500.0

    # A las 4h+, el mismo tamaño se vende a mejor precio usando bids reales.
    binance.precio = 110.0
    exit_now = observed + timedelta(hours=4, seconds=30)
    abiertas2, cerradas2, resumen2 = s.procesar(source, state, binance, exit_now)

    assert abiertas2 == 0
    assert cerradas2 == 10
    assert resumen2["paired_complete_buckets"] == 1
    assert resumen2["portfolios"][s.PORTFOLIO_BASE]["closed_trades"] == 5
    assert resumen2["portfolios"][s.PORTFOLIO_BASE]["realized_pnl_usd"] > 0
    assert resumen2["portfolios"][s.PORTFOLIO_CHALLENGER]["realized_pnl_usd"] > 0
    assert resumen2["challenger_minus_base_net_bps"]["mean"] == pytest.approx(0.0)
    assert len(binance.calls) == 10


def test_bucket_viejo_no_hace_backfill_ni_llama_order_book():
    observed = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    source = estado_05i(observed)
    state = s.nuevo_estado(500.0)
    binance = BinanceFalso()

    abiertas, cerradas, resumen = s.procesar(
        source,
        state,
        binance,
        observed + timedelta(minutes=30),
    )

    assert abiertas == 0
    assert cerradas == 0
    assert binance.calls == []
    assert resumen["processed_buckets"] == 0
    assert resumen["ignored_stale_buckets"] == 1
    assert state["ignored_stale_buckets"][0]["reason"] == "BUCKET_NO_FRESCO_SIN_BACKFILL"


def test_resumen_declara_limitacion_min_notional_y_cero_ordenes():
    resumen = s.construir_resumen(s.nuevo_estado(500.0))
    assert resumen["orders_executed"] is False
    assert resumen["database_touched"] is False
    assert resumen["llm_called"] is False
    assert resumen["backfill_allowed"] is False
    assert resumen["risk_engine_used_for_sizing"] is True
    assert resumen["exchange_min_notional_checked"] is False
