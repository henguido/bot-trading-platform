from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.simulation.paper_api import historial_paper, resumen_paper


@pytest.fixture
def fabrica():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


def crear_usuario(db, email):
    u = models.User(nombre=email, email=email, password_hash="x")
    db.add(u)
    db.flush()
    return u


def agregar_operacion(
    db,
    *,
    ledger,
    symbol="BTCUSDT",
    side="BUY",
    qty=0.1,
    reference=100.0,
    fill=100.0,
    gross=10.0,
    fee=0.01,
    net=10.01,
    creada_en=None,
):
    row = models.PaperOperacion(
        ledger_id=ledger.id,
        symbol=symbol,
        side=side,
        reference_price=reference,
        fill_price=fill,
        base_quantity=qty,
        quote_gross=gross,
        fee_usd=fee,
        quote_net=net,
        slippage_bps=(fill / reference - 1.0) * 10_000.0 if side == "BUY" else 0.0,
        fee_taker_bps=10.0,
        strategy="05A",
        expected_edge_bps=40.0,
        expected_cost_bps=20.0,
        expected_net_bps=20.0,
        creada_en=creada_en or datetime(2026, 8, 26, 6, 0, 0),
    )
    db.add(row)
    db.flush()
    return row


def test_resumen_sin_ledger_es_lectura_pura_y_muestra_capital_inicial(fabrica):
    with fabrica() as db:
        u = crear_usuario(db, "sin-ledger@test.local")
        db.commit()
        uid = u.id

    llamadas = []
    with fabrica() as db:
        salida = resumen_paper(
            db,
            usuario_id=uid,
            initial_capital_usd=500.0,
            obtener_precio=lambda symbol: llamadas.append(symbol),
        )
        assert db.query(models.PaperLedger).count() == 0

    assert llamadas == []
    assert salida["modo"] == "PAPER"
    assert salida["capital_disponible_usd"] == pytest.approx(500.0)
    assert salida["valor_total_usd"] == pytest.approx(500.0)
    assert salida["pnl_total"] == pytest.approx(0.0)
    assert salida["fees_total_usd"] == pytest.approx(0.0)
    assert salida["operaciones"] == 0
    assert salida["resumen"] == [{
        "symbol": "USDT",
        "cantidad": 500.0,
        "precio_actual": 1.0,
        "valor_actual": 500.0,
        "average_price": 1.0,
        "average_price_status": "DISPONIBLE",
        "pnl": 0.0,
        "pnl_status": "DISPONIBLE",
    }]


def test_resumen_paper_sale_del_ledger_y_marca_posicion_a_mercado(fabrica):
    with fabrica() as db:
        u = crear_usuario(db, "uno@test.local")
        ledger = models.PaperLedger(usuario_id=u.id, initial_capital_usd=500.0)
        db.add(ledger)
        db.flush()
        agregar_operacion(db, ledger=ledger)
        db.commit()
        uid = u.id

    llamadas = []
    with fabrica() as db:
        salida = resumen_paper(
            db,
            usuario_id=uid,
            initial_capital_usd=9999.0,
            obtener_precio=lambda symbol: llamadas.append(symbol) or 110.0,
        )

    assert llamadas == ["BTCUSDT"]
    assert salida["initial_capital_usd"] == pytest.approx(500.0)
    assert salida["capital_disponible_usd"] == pytest.approx(489.99)
    assert salida["fees_total_usd"] == pytest.approx(0.01)
    assert salida["pnl_realizado_usd"] == pytest.approx(0.0)
    assert salida["pnl_no_realizado_usd"] == pytest.approx(0.99)
    assert salida["pnl_total"] == pytest.approx(0.99)
    assert salida["valor_total_usd"] == pytest.approx(500.99)

    btc = next(x for x in salida["resumen"] if x["symbol"] == "BTCUSDT")
    assert btc["cantidad"] == pytest.approx(0.1)
    assert btc["average_price"] == pytest.approx(100.1)
    assert btc["precio_actual"] == pytest.approx(110.0)
    assert btc["pnl"] == pytest.approx(0.99)


def test_resumen_no_oculta_posicion_si_precio_publico_falla(fabrica):
    with fabrica() as db:
        u = crear_usuario(db, "precio@test.local")
        ledger = models.PaperLedger(usuario_id=u.id, initial_capital_usd=500.0)
        db.add(ledger)
        db.flush()
        agregar_operacion(db, ledger=ledger)
        db.commit()
        uid = u.id

    def falla(symbol):
        raise ConnectionError(symbol)

    with fabrica() as db:
        salida = resumen_paper(
            db,
            usuario_id=uid,
            initial_capital_usd=500.0,
            obtener_precio=falla,
        )

    btc = next(x for x in salida["resumen"] if x["symbol"] == "BTCUSDT")
    assert btc["cantidad"] == pytest.approx(0.1)
    assert btc["precio_actual"] is None
    assert btc["valor_actual"] is None
    assert btc["pnl"] is None
    assert btc["pnl_status"] == "NO_DISPONIBLE"
    assert salida["valor_total_usd"] is None
    assert salida["valor_total_usd_status"] == "NO_DISPONIBLE"
    assert salida["pnl_total"] is None
    assert salida["pnl_total_status"] == "NO_DISPONIBLE"


def test_historial_paper_es_ejecucion_real_del_usuario_y_no_decision_gpt(fabrica):
    with fabrica() as db:
        u1 = crear_usuario(db, "hist1@test.local")
        u2 = crear_usuario(db, "hist2@test.local")
        l1 = models.PaperLedger(usuario_id=u1.id, initial_capital_usd=500.0)
        l2 = models.PaperLedger(usuario_id=u2.id, initial_capital_usd=700.0)
        db.add_all([l1, l2])
        db.flush()
        propia = agregar_operacion(
            db,
            ledger=l1,
            fill=100.5,
            gross=10.05,
            fee=0.01005,
            net=10.06005,
            creada_en=datetime(2026, 8, 26, 6, 0, 0),
        )
        agregar_operacion(
            db,
            ledger=l2,
            symbol="ETHUSDT",
            qty=1.0,
            reference=2000.0,
            fill=2000.0,
            gross=2000.0,
            fee=2.0,
            net=2002.0,
        )
        db.commit()
        uid1 = u1.id
        propia_id = propia.id

    with fabrica() as db:
        historial = historial_paper(db, usuario_id=uid1)

    assert len(historial) == 1
    fila = historial[0]
    assert fila["paper_operation_id"] == propia_id
    assert fila["symbol"] == "BTCUSDT"
    assert fila["action"] == "COMPRAR"
    assert fila["side"] == "BUY"
    assert fila["price"] == pytest.approx(100.5)
    assert fila["reference_price"] == pytest.approx(100.0)
    assert fila["fee_usd"] == pytest.approx(0.01005)
    assert fila["quote_net"] == pytest.approx(10.06005)
    assert fila["expected_net_bps"] == pytest.approx(20.0)
    assert fila["decision_gpt"] is None
    assert fila["risk_score"] is None
    assert fila["timestamp"] == "2026-08-26 00:00:00"
    assert all(x["symbol"] != "ETHUSDT" for x in historial)


def test_historial_sin_ledger_devuelve_vacio_y_no_crea_nada(fabrica):
    with fabrica() as db:
        u = crear_usuario(db, "vacio@test.local")
        db.commit()
        uid = u.id

    with fabrica() as db:
        assert historial_paper(db, usuario_id=uid) == []
        assert db.query(models.PaperLedger).count() == 0
