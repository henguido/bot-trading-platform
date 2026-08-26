"""Contexto financiero del LLM debe salir de la misma cartera que opera.

PAPER usa exclusivamente su ledger persistente; LIVE usa saldos del broker y
contexto LIVE. Ningun balance real puede filtrarse de un modo al otro.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.portafolio.carteras import (
    CarteraLive,
    CarteraPaper,
    contexto_posicion_para_llm,
    construir_cartera,
    portafolio_para_llm,
)

RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


@pytest.fixture
def fabrica_paper():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def ledger_paper(fabrica_paper):
    """Ledger coherente: compra 0.011 BTC y vende 0.001; quedan 0.010 BTC."""
    with fabrica_paper() as db:
        u = models.User(nombre="Paper", email="paper-llm@test.local", password_hash="x")
        db.add(u)
        db.flush()
        ledger = models.PaperLedger(usuario_id=u.id, initial_capital_usd=1000.0)
        db.add(ledger)
        db.flush()
        db.add_all([
            models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="BUY",
                reference_price=50_000.0,
                fill_price=50_000.0,
                base_quantity=0.011,
                quote_gross=550.0,
                fee_usd=0.55,
                quote_net=550.55,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                creada_en=datetime(2026, 8, 17, 10, 0, 0),
            ),
            models.PaperOperacion(
                ledger_id=ledger.id,
                symbol="BTCUSDT",
                side="SELL",
                reference_price=55_000.0,
                fill_price=55_000.0,
                base_quantity=0.001,
                quote_gross=55.0,
                fee_usd=0.055,
                quote_net=54.945,
                slippage_bps=0.0,
                fee_taker_bps=10.0,
                creada_en=datetime(2026, 8, 17, 11, 0, 0),
            ),
        ])
        db.commit()
        return u.id


def test_paper_expone_capital_y_posicion_del_ledger(fabrica_paper, ledger_paper):
    cartera = CarteraPaper(
        usuario_id=ledger_paper,
        session_factory=fabrica_paper,
        initial_capital_usd=1000.0,
    )

    ctx = cartera.contexto_posicion_llm("BTCUSDT")

    assert cartera.capital_disponible() == pytest.approx(504.395)
    assert ctx.cantidad == pytest.approx(0.01)
    # El coste abierto incluye la fee de entrada: 550.55 / 0.011.
    assert ctx.precio_medio == pytest.approx(50_050.0)
    # No se inventa equivalencia con el timestamp mutable del Simulator.
    assert ctx.ultimo_movimiento is None
    assert ctx.ultimo_precio_venta == pytest.approx(55_000.0)
    assert cartera.portafolio_para_llm() == [
        {"moneda": "USDT", "cantidad": 504.395},
        {"moneda": "BTC", "cantidad": 0.01},
    ]


def test_paper_ignora_balance_y_contexto_live_aunque_se_entreguen_al_selector(
    fabrica_paper, ledger_paper
):
    cartera = construir_cartera(
        modo_real=False,
        simulador=object(),
        usuario_id=ledger_paper,
        saldos_broker={"USDT": 1.11, "BTC": 9.0, "ETH": 7.0},
        usdt_broker=1.11,
        session_factory=fabrica_paper,
        paper_initial_capital_usd=1000.0,
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
    assert cartera.capital_disponible() == pytest.approx(504.395)
    assert btc.cantidad == pytest.approx(0.01)
    assert btc.precio_medio == pytest.approx(50_050.0)
    assert btc.ultimo_movimiento is None
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
    assert "capital_disponible=cartera.capital_disponible()" in fuente


def test_main_pasa_contexto_persistente_solo_al_selector_de_cartera():
    fuente = MAIN.read_text(encoding="utf-8")
    for fragmento in (
        "estado_persistente=contexto.estado",
        "ultimos_movimientos=contexto.ultimos_movimientos",
        "ultimos_precios_venta=contexto.ultimos_precios_venta",
    ):
        assert fragmento in fuente
    bloque = fuente.split("for asset in activos_evaluar:", 1)[1].split(
        "print(gate.linea", 1)[0]
    assert "contexto.estado" not in bloque
    assert "contexto.ultimos_movimientos" not in bloque
    assert "contexto.ultimos_precios_venta" not in bloque
