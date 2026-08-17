"""BOT 2.0-04B-0 · validacion temporal sin leakage."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_historico import EstadoHistorico, ObservacionEdge
from backend.economia.validacion_edge import HORA_MS, particionar_temporal

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "validacion_edge.py"


def obs(hora, symbol="BTCUSDT"):
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol,
            timestamp_ms=hora * HORA_MS,
            close=Decimal("100"),
            quote_volume_24h=Decimal("1000000"),
            trades_24h=10000,
            rango_24h=Decimal("0.05"),
            momentum_cierre_24h_pct=Decimal("2"),
        ),
        etiquetas=(),
    )


def test_split_es_cronologico_no_aleatorio():
    datos = [obs(210), obs(10), obs(120), obs(30)]
    p = particionar_temporal(
        datos, corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=0)
    assert [o.estado.timestamp_ms // HORA_MS for o in p.train] == [10, 30]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.validacion] == [120]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.test] == [210]


def test_embargo_excluye_labels_que_pisarian_validacion():
    datos = [obs(75), obs(76), obs(99), obs(100)]
    p = particionar_temporal(
        datos, corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=24)
    assert [o.estado.timestamp_ms // HORA_MS for o in p.train] == [75]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.descartadas_embargo] == [76, 99]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.validacion] == [100]


def test_embargo_tambien_protege_el_corte_de_test():
    datos = [obs(175), obs(176), obs(199), obs(200), obs(201)]
    p = particionar_temporal(
        datos, corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=24)
    assert [o.estado.timestamp_ms // HORA_MS for o in p.validacion] == [175]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.descartadas_embargo] == [176, 199]
    assert [o.estado.timestamp_ms // HORA_MS for o in p.test] == [200, 201]


def test_mismo_timestamp_de_distintos_simbolos_no_se_separa():
    datos = [obs(120, "ETHUSDT"), obs(120, "BTCUSDT"), obs(120, "SOLUSDT")]
    p = particionar_temporal(
        datos, corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=24)
    assert [o.estado.symbol for o in p.validacion] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert not p.train and not p.test


def test_resultado_no_depende_del_orden_de_entrada():
    datos = [obs(210, "ETHUSDT"), obs(10), obs(120), obs(210, "BTCUSDT")]
    a = particionar_temporal(
        datos, corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=0)
    b = particionar_temporal(
        reversed(datos), corte_validacion_ms=100 * HORA_MS,
        corte_test_ms=200 * HORA_MS, embargo_horas=0)
    assert a == b


@pytest.mark.parametrize("kwargs", [
    {"corte_validacion_ms": -1, "corte_test_ms": 10},
    {"corte_validacion_ms": 10, "corte_test_ms": 10},
    {"corte_validacion_ms": 20, "corte_test_ms": 10},
    {"corte_validacion_ms": True, "corte_test_ms": 10},
    {"corte_validacion_ms": 10, "corte_test_ms": 20, "embargo_horas": -1},
    {"corte_validacion_ms": 10, "corte_test_ms": 20, "embargo_horas": 1.5},
])
def test_parametros_invalidos_fallan_cerrado(kwargs):
    with pytest.raises(ValueError):
        particionar_temporal([], **kwargs)


def test_modulo_no_importa_random_ml_red_ni_bd():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    prohibidos = ("random", "sklearn", "numpy", "pandas", "requests",
                  "sqlalchemy", "openai", "binance", "SessionLocal")
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto
