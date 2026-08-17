"""BOT 2.0-04B · auditoria de cobertura del dataset."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.dataset_edge import HORA_MS, construir_dataset
from backend.economia.edge_historico import Vela

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "dataset_edge.py"


def vela(i):
    c = Decimal(100 + i)
    return Vela(
        open_time_ms=i * HORA_MS,
        open=c, high=c + 1, low=c - 1, close=c,
        volume=Decimal("10"), close_time_ms=(i + 1) * HORA_MS - 1,
        quote_volume=Decimal("1000"), trades=100)


def test_manifiesto_declara_sesgo_supervivencia_explicitamente():
    d = construir_dataset(
        {"BTCUSDT": tuple(vela(i) for i in range(60))},
        universo_fuente="pares spot USDT activos al 2026-08-17",
        sesgo_supervivencia_pendiente=True)
    assert d.sesgo_supervivencia_pendiente is True
    assert "activos" in d.universo_fuente
    assert d.n_symbols == 1
    assert d.n_observaciones == 12


def test_cobertura_detecta_gap_y_horas_faltantes():
    serie = tuple(vela(i) for i in list(range(10)) + list(range(12, 60)))
    d = construir_dataset(
        {"BTCUSDT": serie}, universo_fuente="fixture",
        sesgo_supervivencia_pendiente=False)
    c = d.coberturas[0]
    assert c.n_gaps == 1
    assert c.horas_faltantes_estimadas == 2
    # edge_historico descarta ventanas contaminadas por el gap.
    assert c.n_observaciones < 12


def test_simbolos_y_observaciones_se_ordenan_establemente():
    series = {
        "ETHUSDT": tuple(vela(i) for i in range(60)),
        "BTCUSDT": tuple(vela(i) for i in range(60)),
    }
    a = construir_dataset(series, universo_fuente="fixture",
                          sesgo_supervivencia_pendiente=False)
    b = construir_dataset(dict(reversed(list(series.items()))), universo_fuente="fixture",
                          sesgo_supervivencia_pendiente=False)
    assert a == b
    assert [c.symbol for c in a.coberturas] == ["BTCUSDT", "ETHUSDT"]


def test_serie_vacia_queda_auditada_no_desaparece():
    d = construir_dataset(
        {"NUEVOUSDT": ()}, universo_fuente="fixture",
        sesgo_supervivencia_pendiente=True)
    c = d.coberturas[0]
    assert c.n_velas == 0
    assert c.inicio_open_ms is None and c.fin_open_ms is None
    assert c.n_observaciones == 0


def test_flag_supervivencia_debe_ser_booleano_no_truthy():
    with pytest.raises(ValueError):
        construir_dataset({}, universo_fuente="fixture",
                          sesgo_supervivencia_pendiente="si")
    with pytest.raises(ValueError):
        construir_dataset({}, universo_fuente="",
                          sesgo_supervivencia_pendiente=True)


def test_modulo_no_importa_red_ml_llm_bd_scanner_risk_ni_costes():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    texto = ast.dump(arbol)
    for prohibido in (
        "requests", "binance", "sklearn", "numpy", "pandas", "openai",
        "sqlalchemy", "scanner", "MotorRiesgo", "costes", "SessionLocal",
    ):
        assert prohibido not in texto
