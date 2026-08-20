"""BOT 2.0-04B-0 · dataset historico y labels de Expected Edge."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_historico import (
    HORIZONTES_EXPLORATORIOS_HORAS,
    construir_observaciones,
    vela_desde_kline,
    velas_desde_klines,
)

HORA = 60 * 60 * 1000
RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "edge_historico.py"


def kline(i, *, close=None, high=None, low=None, qv=None, trades=None,
          intervalo_horas=1, desplazar_ms=0):
    c = Decimal(str(close if close is not None else 100 + i))
    h = Decimal(str(high if high is not None else c + Decimal("1")))
    l = Decimal(str(low if low is not None else c - Decimal("1")))
    o = c
    paso = intervalo_horas * HORA
    t0 = i * paso + desplazar_ms
    return [
        t0, str(o), str(h), str(l), str(c), "10", t0 + paso - 1,
        str(qv if qv is not None else 1000 + i),
        int(trades if trades is not None else 100 + i),
        "0", "0", "0",
    ]


def serie(n=60, **kw):
    return velas_desde_klines([kline(i, **kw) for i in range(n)])


def test_parsea_kline_binance_y_usa_decimal():
    v = vela_desde_kline(kline(3, close="123.45", high="124", low="122"))
    assert v.open_time_ms == 3 * HORA
    assert v.close == Decimal("123.45")
    assert v.high == Decimal("124")
    assert v.low == Decimal("122")
    assert isinstance(v.quote_volume, Decimal)


@pytest.mark.parametrize("fila", [
    None,
    [],
    [0, "1"],
])
def test_kline_incompleto_falla_cerrado(fila):
    with pytest.raises(ValueError):
        vela_desde_kline(fila)


def test_ohlc_inconsistente_falla_cerrado():
    with pytest.raises(ValueError):
        vela_desde_kline(kline(0, close=100, high=99, low=98))


def test_velas_se_ordenan_y_duplicados_se_rechazan():
    velas = velas_desde_klines([kline(2), kline(0), kline(1)])
    assert [v.open_time_ms for v in velas] == [0, HORA, 2 * HORA]
    with pytest.raises(ValueError):
        velas_desde_klines([kline(0), kline(0)])


def test_horizontes_exploratorios_no_eligen_un_unico_holding_period():
    assert HORIZONTES_EXPLORATORIOS_HORAS == (4, 8, 12, 24)


def test_con_60_velas_horarias_hay_12_observaciones_completas():
    obs = construir_observaciones("BTCUSDT", serie(60))
    assert len(obs) == 12
    assert obs[0].estado.timestamp_ms == 25 * HORA - 1  # vela i=24
    assert [e.horizonte_horas for e in obs[0].etiquetas] == [4, 8, 12, 24]


def test_estado_24h_usa_solo_pasado_y_presente():
    velas = serie(60)
    o = construir_observaciones("BTCUSDT", velas)[0]  # i=24

    # quote volume usa i=1..24 (24 barras), NO i=0 ni futuro.
    esperado_qv = sum(Decimal(str(1000 + i)) for i in range(1, 25))
    esperado_trades = sum(100 + i for i in range(1, 25))
    assert o.estado.quote_volume_24h == esperado_qv
    assert o.estado.trades_24h == esperado_trades

    # close(t)=124 y close(t-24h)=100.
    assert o.estado.momentum_cierre_24h_pct == Decimal("24.00")
    # highs 102..125, lows 100..123 para barras i=1..24.
    assert o.estado.rango_24h == (Decimal("125") - Decimal("100")) / Decimal("100")


def test_label_retorno_cierre_4h_es_futuro_y_no_feature():
    o = construir_observaciones("BTCUSDT", serie(60))[0]  # entrada close=124
    e4 = o.etiqueta(4)
    assert e4.retorno_cierre == Decimal("128") / Decimal("124") - Decimal("1")
    assert not hasattr(o.estado, "retorno_cierre")
    assert not hasattr(o.estado, "mfe")
    assert not hasattr(o.estado, "mae")


def test_mfe_mae_long_se_acotan_por_cero():
    filas = [kline(i, close=100, high=101, low=99) for i in range(49)]
    # t es i=24. Las cuatro primeras futuras quedan completamente por encima.
    for i in range(25, 29):
        filas[i] = kline(i, close=110 + i, high=111 + i, low=109 + i)
    obs = construir_observaciones("XUSDT", velas_desde_klines(filas))
    e4 = obs[0].etiqueta(4)
    assert e4.mfe > 0
    assert e4.mae == Decimal("0")

    filas = [kline(i, close=100, high=101, low=99) for i in range(49)]
    for i in range(25, 29):
        filas[i] = kline(i, close=80, high=90, low=70)
    e4 = construir_observaciones("XUSDT", velas_desde_klines(filas))[0].etiqueta(4)
    assert e4.mfe == Decimal("0")
    assert e4.mae < 0


def test_cambiar_futuro_despues_de_4h_no_contamina_feature_ni_label_4h():
    base = [kline(i) for i in range(60)]
    alterada = [list(f) for f in base]
    # Primera observacion t=i24; alteramos i=30, despues del horizonte 4h.
    alterada[30] = kline(30, close=1000, high=1001, low=999)

    a = construir_observaciones("BTCUSDT", velas_desde_klines(base))[0]
    b = construir_observaciones("BTCUSDT", velas_desde_klines(alterada))[0]
    assert a.estado == b.estado
    assert a.etiqueta(4) == b.etiqueta(4)
    assert a.etiqueta(24) != b.etiqueta(24)


def test_un_gap_en_la_ventana_completa_elimina_la_observacion():
    filas = [kline(i) for i in range(49)]  # exactamente una observacion posible
    filas[10] = kline(10, desplazar_ms=5 * 60 * 1000)
    obs = construir_observaciones("BTCUSDT", velas_desde_klines(filas))
    assert obs == ()


def test_no_se_etiqueta_si_falta_el_futuro_maximo():
    assert construir_observaciones("BTCUSDT", serie(48)) == ()


def test_parametros_incompatibles_fallan_cerrado():
    velas = serie(60)
    with pytest.raises(ValueError):
        construir_observaciones("BTCUSDT", velas, intervalo_horas=0)
    with pytest.raises(ValueError):
        construir_observaciones("BTCUSDT", velas, intervalo_horas=4, ventana_horas=23)
    with pytest.raises(ValueError):
        construir_observaciones("BTCUSDT", velas, horizontes_horas=(4, 4))
    with pytest.raises(ValueError):
        construir_observaciones("", velas)


def test_soporta_barras_4h_sin_cambiar_semantica_temporal():
    velas = velas_desde_klines([kline(i, intervalo_horas=4) for i in range(20)])
    obs = construir_observaciones(
        "BTCUSDT", velas, intervalo_horas=4,
        horizontes_horas=(4, 8, 24),
    )
    assert obs
    assert [e.horizonte_horas for e in obs[0].etiquetas] == [4, 8, 24]


def test_modulo_es_puro_sin_red_bd_llm_scanner_ni_riskengine():
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
