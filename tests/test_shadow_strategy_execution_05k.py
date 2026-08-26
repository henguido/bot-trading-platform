from datetime import datetime, timedelta, timezone

import pytest

from scripts import shadow_strategy_execution_05k as s


class BinanceFalso:
    def __init__(self, *, con_filtros=True):
        self.precio = 100.0
        self.calls = []
        self.exchange_info_calls = 0
        self.con_filtros = con_filtros

    def get_order_book(self, symbol, *, limit=100):
        self.calls.append((symbol, limit, self.precio))
        return {
            "asks": [[str(self.precio), "1000"]],
            "bids": [[str(self.precio), "1000"]],
        }

    def get_exchange_symbols_info(self):
        self.exchange_info_calls += 1
        if not self.con_filtros:
            return {}
        return {
            f"S{rank:02d}USDT": {
                "symbol": f"S{rank:02d}USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.001",
                        "maxQty": "10000",
                        "stepSize": "0.001",
                    },
                    {"filterType": "NOTIONAL", "minNotional": "5"},
                ],
            }
            for rank in range(1, 21)
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


def test_bucket_fresco_se_ejecuta_y_cierra_con_pnl_neto_y_filtros_reales():
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
    assert resumen["exchange_min_notional_checked"] is True
    assert resumen["exchange_lot_size_checked"] is True
    # Un único exchangeInfo se comparte por las dos carteras y todos los símbolos.
    assert binance.exchange_info_calls == 1
    assert resumen["exchange_info_calls"] == 1
    # Como ambas carteras eligen los mismos cinco símbolos, el book se reutiliza.
    assert len(binance.calls) == 5

    base = state["portfolios"][s.PORTFOLIO_BASE]
    assert len(base["open_positions"]) == 5
    assert base["open_positions"][0]["entry_quote_net"] <= 10.0 + 1e-9
    assert base["open_positions"][1]["entry_quote_net"] < base["open_positions"][0]["entry_quote_net"]
    assert base["open_positions"][0]["entry_step_size"] == pytest.approx(0.001)
    assert base["open_positions"][0]["entry_min_notional"] == pytest.approx(5.0)
    assert base["capital_usd"] < 500.0

    # A las 4h+, el mismo tamaño se vende a mejor precio usando bids reales y
    # los filtros ACTUALES se vuelven a consultar en este nuevo proceso/ciclo.
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
    assert binance.exchange_info_calls == 2
    assert resumen2["exchange_info_calls"] == 2


def test_bucket_viejo_no_hace_backfill_ni_llama_market_data():
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
    assert binance.exchange_info_calls == 0, "bucket stale no necesita filtros ni red"
    assert resumen["processed_buckets"] == 0
    assert resumen["ignored_stale_buckets"] == 1
    assert state["ignored_stale_buckets"][0]["reason"] == "BUCKET_NO_FRESCO_SIN_BACKFILL"


def test_filtros_desconocidos_bloquean_entrada_sin_consultar_order_book():
    observed = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    source = estado_05i(observed)
    state = s.nuevo_estado(500.0)
    binance = BinanceFalso(con_filtros=False)

    abiertas, cerradas, resumen = s.procesar(
        source, state, binance, observed + timedelta(seconds=30))

    assert abiertas == 0
    assert cerradas == 0
    assert binance.exchange_info_calls == 1
    assert binance.calls == []
    for nombre in s.PORTFOLIOS:
        saltadas = state["portfolios"][nombre]["skipped_entries"]
        assert len(saltadas) == 5
        assert {x["reason"] for x in saltadas} == {"FILTROS_EXCHANGE_NO_DISPONIBLES"}
    assert resumen["processed_buckets"] == 1


def test_resumen_declara_filtros_exchange_y_cero_ordenes():
    resumen = s.construir_resumen(s.nuevo_estado(500.0))
    assert resumen["orders_executed"] is False
    assert resumen["database_touched"] is False
    assert resumen["llm_called"] is False
    assert resumen["backfill_allowed"] is False
    assert resumen["risk_engine_used_for_sizing"] is True
    assert resumen["exchange_min_notional_checked"] is True
    assert resumen["exchange_lot_size_checked"] is True
    assert resumen["exchange_filters_source"] == "BINANCE_EXCHANGE_INFO_CURRENT"
