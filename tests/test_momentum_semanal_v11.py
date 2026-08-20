"""Tests de features semanales BOT 2.0-04B-v11."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from backend.economia.edge_historico import Vela
from backend.economia.momentum_semanal_v11 import construir_observaciones_momentum_v11
from backend.economia.protocolo_edge_v11 import HORIZONTE_HORAS_V11

HORA = 60 * 60 * 1000
PASO = 4 * HORA
INICIO = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)  # lunes 00 UTC
RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "momentum_semanal_v11.py"


def serie(n=240, *, plana=False):
    salida = []
    for i in range(n):
        if plana:
            c = Decimal("100")
        else:
            # Tendencia + oscilación para que la volatilidad diaria no sea cero.
            c = Decimal("100") + Decimal(i) / Decimal("10") + Decimal((i % 12) - 6) / Decimal("20")
        t0 = INICIO + i * PASO
        salida.append(Vela(
            open_time_ms=t0,
            open=c,
            high=c + Decimal("1"),
            low=c - Decimal("1"),
            close=c,
            volume=Decimal("10"),
            close_time_ms=t0 + PASO - 1,
            quote_volume=Decimal("1000"),
            trades=100,
            taker_buy_base_volume=Decimal("5"),
            taker_buy_quote_volume=Decimal("500"),
        ))
    return tuple(salida)


def test_produce_cierre_semanal_y_label_7_dias():
    obs = construir_observaciones_momentum_v11({"BTCUSDT": serie()})
    assert len(obs) == 1
    o = obs[0]
    limite = datetime.fromtimestamp((o.estado.timestamp_ms + 1) / 1000, tz=timezone.utc)
    assert limite.weekday() == 0 and limite.hour == 0
    assert o.etiqueta(HORIZONTE_HORAS_V11).horizonte_horas == 168


def test_mom1_usa_exactamente_una_semana_hacia_atras():
    velas = serie()
    o = construir_observaciones_momentum_v11({"BTCUSDT": velas})[0]
    i = next(i for i, v in enumerate(velas) if v.close_time_ms == o.estado.timestamp_ms)
    esperado = velas[i].close / velas[i - 42].close - Decimal("1")
    assert o.estado.mom1 == esperado
    assert o.estado.rmom1.is_finite()
    assert o.estado.rmom2.is_finite()
    assert o.estado.rmom3.is_finite()


def test_futuro_no_contamina_features():
    base = list(serie())
    a = construir_observaciones_momentum_v11({"BTCUSDT": tuple(base)})[0]
    i = next(i for i, v in enumerate(base) if v.close_time_ms == a.estado.timestamp_ms)
    j = i + 42
    vieja = base[j]
    nuevo_close = vieja.close * Decimal("1.5")
    base[j] = Vela(
        open_time_ms=vieja.open_time_ms,
        open=nuevo_close,
        high=nuevo_close + Decimal("1"),
        low=nuevo_close - Decimal("1"),
        close=nuevo_close,
        volume=vieja.volume,
        close_time_ms=vieja.close_time_ms,
        quote_volume=vieja.quote_volume,
        trades=vieja.trades,
        taker_buy_base_volume=vieja.taker_buy_base_volume,
        taker_buy_quote_volume=vieja.taker_buy_quote_volume,
    )
    b = construir_observaciones_momentum_v11({"BTCUSDT": tuple(base)})[0]
    assert a.estado == b.estado
    assert a.etiqueta(168).retorno_cierre != b.etiqueta(168).retorno_cierre


def test_volatilidad_cero_no_se_imputa_a_rmom_cero():
    assert construir_observaciones_momentum_v11({"BTCUSDT": serie(plana=True)}) == ()


def test_gap_en_historia_o_futuro_descarta_observacion():
    velas = list(serie())
    del velas[100]
    assert construir_observaciones_momentum_v11({"BTCUSDT": tuple(velas)}) == ()


def test_intervalo_distinto_de_4h_falla_cerrado():
    try:
        construir_observaciones_momentum_v11({"BTCUSDT": serie()}, intervalo_horas=1)
    except ValueError as e:
        assert "requiere intervalo_horas=4" in str(e)
    else:
        raise AssertionError("debio fallar")


def test_modulo_es_puro_sin_red_bd_llm_scanner_riskengine():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    prohibidos = (
        "requests", "sqlalchemy", "openai", "binance", "scanner",
        "MotorRiesgo", "SessionLocal", "real_trading",
    )
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto
