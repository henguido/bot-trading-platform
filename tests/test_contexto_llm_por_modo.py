"""Contexto financiero del LLM debe salir de la misma cartera que opera.

Hallazgo 03B: en PAPER, RiskEngine/CarteraPaper veian 500 USDT pero GPT recibia
1.11 USDT desde `balances_reales` del broker. Ademas el coste base y los
movimientos se tomaban del contexto persistente aunque la posicion fuese del
Simulator. Estas pruebas fijan la separacion completa por modo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.portafolio.carteras import (
    CarteraLive,
    CarteraPaper,
    contexto_posicion_para_llm,
    construir_cartera,
    portafolio_para_llm,
)
from backend.simulation.simulator import CryptoPosition, Simulator

RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


def _simulador_paper():
    sim = Simulator()
    sim.capital_usd = 500.0
    movimiento = datetime(2026, 8, 17, 12, 0, 0)
    sim.positions["BTCUSDT"] = CryptoPosition(
        quantity=0.01, average_price=50_000.0, last_movement=movimiento)
    sim.history.append({
        "symbol": "BTCUSDT", "action": "VENTA", "price": 55_000.0,
        "quantity": 0.001, "timestamp": "2026-08-17 11:00:00",
    })
    return sim, movimiento


def test_paper_expone_capital_y_posicion_del_simulador():
    sim, movimiento = _simulador_paper()
    cartera = CarteraPaper(sim)

    ctx = cartera.contexto_posicion_llm("BTCUSDT")

    assert cartera.capital_disponible() == pytest.approx(500.0)
    assert ctx.cantidad == pytest.approx(0.01)
    assert ctx.precio_medio == pytest.approx(50_000.0)
    assert ctx.ultimo_movimiento == movimiento
    assert ctx.ultimo_precio_venta == pytest.approx(55_000.0)
    assert cartera.portafolio_para_llm() == [
        {"moneda": "USDT", "cantidad": 500.0},
        {"moneda": "BTC", "cantidad": 0.01},
    ]


def test_paper_ignora_balance_y_contexto_live_aunque_se_entreguen_al_selector():
    sim, movimiento = _simulador_paper()
    cartera = construir_cartera(
        modo_real=False,
        simulador=sim,
        usuario_id=99,
        saldos_broker={"USDT": 1.11, "BTC": 9.0, "ETH": 7.0},
        usdt_broker=1.11,
        estado_persistente={
            "BTCUSDT": {"cantidad": 9.0, "precio_promedio": 99_999.0},
            "ETHUSDT": {"cantidad": 7.0, "precio_promedio": 2_000.0},
        },
        ultimos_movimientos={"BTCUSDT": "LIVE-MOV"},
        ultimos_precios_venta={"BTCUSDT": 123_456.0},
    )

    btc = cartera.contexto_posicion_llm("BTCUSDT")
    eth = cartera.contexto_posicion_llm("ETHUSDT")

    assert isinstance(cartera, CarteraPaper)
    assert cartera.capital_disponible() == pytest.approx(500.0)
    assert btc.cantidad == pytest.approx(0.01)
    assert btc.precio_medio == pytest.approx(50_000.0)
    assert btc.ultimo_movimiento == movimiento
    assert btc.ultimo_precio_venta == pytest.approx(55_000.0)
    assert eth.cantidad == 0.0 and eth.precio_medio is None
    portafolio = cartera.portafolio_para_llm()
    assert {x["moneda"] for x in portafolio} == {"USDT", "BTC"}
    assert all(x["cantidad"] not in (1.11, 9.0, 7.0) for x in portafolio)


def test_live_expone_saldo_broker_y_coste_persistente():
    live = CarteraLive(
        usuario_id=7,
        saldos_broker={"USDT": 1.11, "BTC": 0.02, "ETH": 0.0},
        usdt_broker=1.11,
        estado_persistente={
            "BTCUSDT": {"cantidad": 0.02, "precio_promedio": 48_000.0}
        },
        ultimos_movimientos={"BTCUSDT": "2026-08-17 12:00:00"},
        ultimos_precios_venta={"BTCUSDT": 52_000.0},
    )

    ctx = live.contexto_posicion_llm("BTCUSDT")

    assert live.capital_disponible() == pytest.approx(1.11)
    assert ctx.cantidad == pytest.approx(0.02)
    assert ctx.precio_medio == pytest.approx(48_000.0)
    assert ctx.ultimo_movimiento == "2026-08-17 12:00:00"
    assert ctx.ultimo_precio_venta == pytest.approx(52_000.0)
    assert live.portafolio_para_llm() == [
        {"moneda": "BTC", "cantidad": 0.02},
        {"moneda": "USDT", "cantidad": 1.11},
    ]


def test_adaptadores_degradan_seguro_para_dobles_antiguos():
    doble = SimpleNamespace(
        capital_disponible=lambda: 123.0,
        cantidad_disponible=lambda symbol: 0.5 if symbol == "BTCUSDT" else 0.0,
    )

    ctx = contexto_posicion_para_llm(doble, "BTCUSDT")

    assert ctx.cantidad == pytest.approx(0.5)
    assert ctx.precio_medio is None
    assert ctx.ultimo_movimiento is None
    assert ctx.ultimo_precio_venta is None
    assert portafolio_para_llm(doble) == [{"moneda": "USDT", "cantidad": 123.0}]


def test_main_usa_una_sola_fuente_financiera_para_gpt_y_riesgo():
    fuente = MAIN.read_text(encoding="utf-8")

    assert "contexto_posicion_para_llm(cartera, symbol)" in fuente
    assert "portafolio_contexto = portafolio_para_llm(cartera)" in fuente
    assert "usdt_disponible = cartera.capital_disponible()" in fuente
    assert "precio_medio_de(contexto.estado, symbol)" not in fuente
    assert "usdt_disponible = next(" not in fuente
    assert "portafolio_real = [" not in fuente
    # El mismo metodo sigue alimentando el MotorRiesgo despues del LLM.
    assert "capital_disponible=cartera.capital_disponible()" in fuente


def test_main_pasa_contexto_persistente_solo_al_selector_de_cartera():
    fuente = MAIN.read_text(encoding="utf-8")
    for fragmento in (
        "estado_persistente=contexto.estado",
        "ultimos_movimientos=contexto.ultimos_movimientos",
        "ultimos_precios_venta=contexto.ultimos_precios_venta",
    ):
        assert fragmento in fuente
    # No debe volver a usarse ese contexto directamente para construir activos
    # que se mandan al LLM; esa decision pertenece a CarteraPaper/CarteraLive.
    bloque = fuente.split("for asset in activos_evaluar:", 1)[1].split(
        "print(gate.linea", 1)[0]
    assert "contexto.estado" not in bloque
    assert "contexto.ultimos_movimientos" not in bloque
    assert "contexto.ultimos_precios_venta" not in bloque
