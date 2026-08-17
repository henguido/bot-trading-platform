"""BOT 2.0-04A · modelo deterministico de costes pre-trade."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.costes import (
    DISPONIBLE,
    NO_DISPONIBLE,
    ResumenCostes,
    estimar_roundtrip,
    spread_bps_desde_bid_ask,
)

RAIZ = Path(__file__).resolve().parents[1]
MODELO = RAIZ / "backend" / "economia" / "costes.py"


def test_spread_bid_ask_en_bps():
    # mid=100, bid=99.95, ask=100.05 -> spread completo = 10 bps
    assert spread_bps_desde_bid_ask("99.95", "100.05") == Decimal("10.000")


def test_spread_roundtrip_se_cobra_una_vez_no_dos():
    e = estimar_roundtrip(
        notional_usd=100,
        spread_bps=10,
        fee_taker_bps_por_lado=0,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )
    assert e.spread_usd == Decimal("0.1")
    assert e.total_usd == Decimal("0.1")
    assert e.total_bps == Decimal("10.0")


def test_fee_taker_se_aplica_entrada_y_salida():
    e = estimar_roundtrip(
        notional_usd=100,
        spread_bps=0,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )
    assert e.fees_usd == Decimal("0.2")
    assert e.total_bps == Decimal("20.0")


def test_slippage_se_aplica_por_lado():
    e = estimar_roundtrip(
        notional_usd=200,
        spread_bps=0,
        fee_taker_bps_por_lado=0,
        slippage_bps_por_lado=5,
        costo_ia_asignado_usd=0,
    )
    assert e.slippage_usd == Decimal("0.2")
    assert e.total_bps == Decimal("10.0")


def test_costo_ia_se_convierte_a_bps_sobre_el_notional():
    e = estimar_roundtrip(
        notional_usd=10,
        spread_bps=0,
        fee_taker_bps_por_lado=0,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd="0.01",
    )
    assert e.total_usd == Decimal("0.01")
    assert e.total_bps == Decimal("10.000")


def test_suma_de_componentes_completa():
    # 10 USDT, spread 10bps=.01, fees 2*10bps=.02,
    # slippage 2*5bps=.01, IA=.01 => total .05 = 50bps.
    e = estimar_roundtrip(
        notional_usd=10,
        spread_bps=10,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5,
        costo_ia_asignado_usd="0.01",
    )
    assert e.estado == DISPONIBLE
    assert e.faltantes == ()
    assert e.spread_usd == Decimal("0.01")
    assert e.fees_usd == Decimal("0.02")
    assert e.slippage_usd == Decimal("0.01")
    assert e.total_usd == Decimal("0.05")
    assert e.total_bps == Decimal("50.00")


@pytest.mark.parametrize("faltante", ["spread", "fee", "slippage", "ia"])
def test_desconocido_nunca_se_convierte_en_cero(faltante):
    kw = dict(
        notional_usd=10,
        spread_bps=10,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5,
        costo_ia_asignado_usd="0.01",
    )
    mapa = {
        "spread": "spread_bps",
        "fee": "fee_taker_bps_por_lado",
        "slippage": "slippage_bps_por_lado",
        "ia": "costo_ia_asignado_usd",
    }
    kw[mapa[faltante]] = None
    e = estimar_roundtrip(**kw)

    assert e.estado == NO_DISPONIBLE
    assert e.total_usd is None
    assert e.total_bps is None
    assert e.subtotal_conocido_usd > 0


def test_faltantes_son_explicitos():
    e = estimar_roundtrip(notional_usd=10, spread_bps=12)
    assert e.faltantes == ("fee_taker", "slippage", "costo_ia")


def test_ia_puede_declararse_no_aplicable_expresamente():
    e = estimar_roundtrip(
        notional_usd=10,
        spread_bps=10,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5,
        costo_ia_asignado_usd=None,
        exigir_costo_ia=False,
    )
    assert e.estado == DISPONIBLE
    assert e.total_usd == Decimal("0.04")


def test_bid_ask_y_spread_directo_son_excluyentes():
    with pytest.raises(ValueError):
        estimar_roundtrip(notional_usd=10, spread_bps=10, bid=99, ask=101)


@pytest.mark.parametrize("bid,ask", [
    (0, 1), (-1, 1), (2, 1), (float("nan"), 1), (1, float("inf")),
])
def test_bid_ask_invalido_falla_cerrado(bid, ask):
    with pytest.raises(ValueError):
        spread_bps_desde_bid_ask(bid, ask)


@pytest.mark.parametrize("notional", [0, -1, None, float("nan"), float("inf")])
def test_notional_invalido_no_produce_estimacion(notional):
    with pytest.raises(ValueError):
        estimar_roundtrip(notional_usd=notional, spread_bps=1)


@pytest.mark.parametrize("campo", [
    "spread_bps", "fee_taker_bps_por_lado", "slippage_bps_por_lado",
    "costo_ia_asignado_usd",
])
def test_costes_negativos_se_rechazan(campo):
    kw = dict(
        notional_usd=10,
        spread_bps=1,
        fee_taker_bps_por_lado=1,
        slippage_bps_por_lado=1,
        costo_ia_asignado_usd=1,
    )
    kw[campo] = -1
    with pytest.raises(ValueError):
        estimar_roundtrip(**kw)


def test_decimal_no_arrastra_error_binario():
    e = estimar_roundtrip(
        notional_usd=Decimal("0.3"),
        spread_bps=Decimal("0.1"),
        fee_taker_bps_por_lado=Decimal("0.1"),
        slippage_bps_por_lado=Decimal("0.1"),
        costo_ia_asignado_usd=Decimal("0.00001"),
    )
    assert isinstance(e.total_usd, Decimal)
    assert e.total_usd == Decimal("0.000025")


def test_como_dict_solo_serializa_primitivos():
    e = estimar_roundtrip(
        notional_usd=10, spread_bps=10, fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5, costo_ia_asignado_usd="0.01")
    d = e.como_dict()
    assert d["estado"] == DISPONIBLE
    assert d["total_usd"] == pytest.approx(0.05)
    assert d["faltantes"] == []


def test_resumen_no_decide_y_agrega_observabilidad():
    completo = estimar_roundtrip(
        notional_usd=10, spread_bps=10, fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5, costo_ia_asignado_usd="0.01")
    incompleto = estimar_roundtrip(notional_usd=10, spread_bps=10)
    r = ResumenCostes()
    r.anotar(completo)
    r.anotar(incompleto)

    assert r.evaluados == 2
    assert r.completos == 1
    assert r.incompletos == 1
    assert r.faltantes == {"fee_taker": 1, "slippage": 1, "costo_ia": 1}
    linea = r.linea(3)
    assert "evaluados=2" in linea and "3 ms" in linea


def test_modulo_es_puro_sin_red_bd_llm_ni_riskengine():
    arbol = ast.parse(MODELO.read_text(encoding="utf-8"))
    prohibidos = (
        "requests", "sqlalchemy", "openai", "binance", "MotorRiesgo",
        "real_trading", "SessionLocal",
    )
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto


def test_modelo_no_contiene_umbrales_de_rentabilidad():
    fuente = MODELO.read_text(encoding="utf-8")
    for prohibido in ("expected_edge", "beneficio_esperado", "COMPRAR", "VENDER"):
        assert prohibido not in fuente
