"""Contratos estructurales PAPER / LIVE y flujo persistente PAPER v1."""
import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import EstadoOrden, Lado, ResultadoOrden
from backend.portafolio.carteras import CarteraLive, CarteraPaper, construir_cartera
from backend.risk.motor import DecisionRiesgo
from backend.simulation.simulator import Simulator

RAIZ = Path(__file__).resolve().parents[1]
SIMBOLO = "BTCUSDT"
PRECIO = 100.0


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


@pytest.fixture
def usuario_id(fabrica):
    with fabrica() as db:
        u = models.User(nombre="Paper", email="paper@test.local", password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


@pytest.fixture
def simulador():
    sim = Simulator()
    sim.capital_usd = 1000.0
    return sim


class BookProvider:
    def __init__(self, book=None):
        self.book = book or {
            "asks": [["100", "0.5"], ["101", "2"]],
            "bids": [["99", "2"]],
        }
        self.calls = []

    def __call__(self, symbol):
        self.calls.append(symbol)
        return self.book


def veredicto(side=Lado.COMPRA, base=0.1, quote=100.0):
    return DecisionRiesgo(
        aprobado=True,
        symbol=SIMBOLO,
        side=side,
        approved_base_quantity=base,
        approved_quote_amount=quote,
    )


def cartera_paper(fabrica, usuario_id, provider, *, fee_bps=10.0):
    return CarteraPaper(
        usuario_id=usuario_id,
        session_factory=fabrica,
        initial_capital_usd=500.0,
        fee_taker_bps_por_lado=fee_bps,
        order_book_provider=provider,
    )


class BrokerProhibido:
    """Si PAPER lo toca, la prueba falla."""

    def comprar(self, *a, **k):
        raise AssertionError("PAPER no debe llamar al broker")

    def vender(self, *a, **k):
        raise AssertionError("PAPER no debe llamar al broker")


# ── PAPER v1: compra -> persistencia -> reinicio -> venta -> P&L neto ───────
def test_paper_persiste_compra_reinicia_y_cierra_con_pnl_neto(fabrica, usuario_id):
    provider = BookProvider()
    cartera = cartera_paper(fabrica, usuario_id, provider)

    compra = cartera.ejecutar(
        veredicto(Lado.COMPRA, quote=100.0),
        PRECIO,
        trader=BrokerProhibido(),
    )
    assert compra.success is True
    assert compra.average_fill_price > PRECIO, "debe reflejar slippage al caminar asks"
    assert cartera.capital_disponible() == pytest.approx(400.0, abs=1e-8)
    cantidad = cartera.cantidad_disponible(SIMBOLO)
    assert cantidad > 0

    # Simula un reinicio real: instancia nueva, mismo ledger, sin Simulator.
    reiniciada = cartera_paper(fabrica, usuario_id, provider)
    assert reiniciada.cantidad_disponible(SIMBOLO) == pytest.approx(cantidad)
    assert reiniciada.capital_disponible() == pytest.approx(400.0, abs=1e-8)
    assert reiniciada.contexto_posicion_llm(SIMBOLO).precio_medio > PRECIO

    # El mercado sube. La venta usa bids y descuenta una segunda fee.
    provider.book = {
        "asks": [["111", "2"]],
        "bids": [["110", "2"]],
    }
    venta = reiniciada.ejecutar(
        veredicto(Lado.VENTA, base=cantidad, quote=0.0),
        110.0,
        trader=BrokerProhibido(),
    )
    assert venta.success is True
    assert reiniciada.cantidad_disponible(SIMBOLO) == pytest.approx(0.0, abs=1e-12)
    assert reiniciada.capital_disponible() > 500.0

    estado = reiniciada.estado_riesgo()
    assert estado.cantidad_disponible(SIMBOLO) == pytest.approx(0.0, abs=1e-12)
    assert estado.pnl_realizado_dia > 0

    with fabrica() as db:
        ops = db.query(models.PaperOperacion).order_by(models.PaperOperacion.id).all()
        assert len(ops) == 2
        assert ops[0].side == "BUY"
        assert ops[1].side == "SELL"
        assert ops[0].slippage_bps > 0
        assert ops[0].fee_usd > 0 and ops[1].fee_usd > 0
        # El ledger PAPER no contamina ninguna tabla de ejecución LIVE.
        assert db.query(models.Transaction).count() == 0
        assert db.query(models.Order).count() == 0
        assert db.query(models.Fill).count() == 0


def test_compra_paper_nunca_supera_el_presupuesto_aprobado(fabrica, usuario_id):
    provider = BookProvider({
        "asks": [["100", "10"]],
        "bids": [["99", "10"]],
    })
    cartera = cartera_paper(fabrica, usuario_id, provider, fee_bps=10.0)

    resultado = cartera.ejecutar(veredicto(Lado.COMPRA, quote=100.0), 100.0)
    assert resultado.success is True

    with fabrica() as db:
        op = db.query(models.PaperOperacion).one()
        assert op.quote_net <= 100.0 + 1e-9
        assert op.quote_gross < 100.0
        assert op.fee_usd > 0
    assert cartera.capital_disponible() >= 400.0 - 1e-9


def test_fee_desconocida_falla_cerrado_y_no_persiste(fabrica, usuario_id):
    provider = BookProvider()
    cartera = cartera_paper(fabrica, usuario_id, provider, fee_bps=None)

    resultado = cartera.ejecutar(veredicto(Lado.COMPRA, quote=100.0), 100.0)

    assert resultado.success is False
    assert resultado.estado is EstadoOrden.ERROR_PRE_ENVIO
    assert "fee_taker_bps_por_lado" in (resultado.error or "")
    assert provider.calls == [], "sin fee conocida ni siquiera debe pedir profundidad"
    with fabrica() as db:
        assert db.query(models.PaperOperacion).count() == 0


def test_profundidad_insuficiente_falla_cerrado_y_no_persiste(fabrica, usuario_id):
    provider = BookProvider({
        "asks": [["100", "0.01"]],
        "bids": [["99", "0.01"]],
    })
    cartera = cartera_paper(fabrica, usuario_id, provider)

    resultado = cartera.ejecutar(veredicto(Lado.COMPRA, quote=100.0), 100.0)

    assert resultado.success is False
    assert resultado.estado is EstadoOrden.ERROR_PRE_ENVIO
    with fabrica() as db:
        assert db.query(models.PaperOperacion).count() == 0


# ── Aislamiento estructural PAPER / LIVE ────────────────────────────────────
def test_saldo_broker_cero_no_altera_posicion_paper(fabrica, usuario_id):
    provider = BookProvider({
        "asks": [["100", "10"]],
        "bids": [["99", "10"]],
    })
    cartera = cartera_paper(fabrica, usuario_id, provider)
    assert cartera.ejecutar(veredicto(Lado.COMPRA, quote=50.0), 100.0).success
    cantidad = cartera.cantidad_disponible(SIMBOLO)

    for saldos in ({}, {"BTC": 0.0}, {"BTC": 0.0, "USDT": 0.0}, None):
        assert cartera.limpiar_posiciones_sin_respaldo(saldos) == 0
        assert cartera.cantidad_disponible(SIMBOLO) == pytest.approx(cantidad)


def test_cartera_paper_no_admite_saldos_broker_ni_simulador():
    firma = inspect.signature(CarteraPaper.__init__)
    parametros = set(firma.parameters) - {"self"}
    assert "saldos_broker" not in parametros
    assert "usdt_broker" not in parametros
    assert "simulador" not in parametros
    assert "trader" not in parametros
    assert CarteraPaper.usa_broker is False


def test_cartera_paper_no_referencia_ejecucion_live():
    fuente = Path(RAIZ, "backend", "portafolio", "carteras.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    clase = next(
        n for n in ast.walk(arbol)
        if isinstance(n, ast.ClassDef) and n.name == "CarteraPaper"
    )
    volcado = ast.dump(clase)
    for prohibido in (
        "_saldos",
        "guardar_transaccion_real",
        "ejecutar_y_registrar_compra",
        "ejecutar_y_registrar_venta",
        "simulate_trade",
    ):
        assert prohibido not in volcado, f"CarteraPaper no debe referenciar {prohibido}"


def test_main_no_compara_posiciones_simuladas_con_saldos_reales_y_cablea_paper():
    fuente = Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8")
    assert "Limpiando simulador y BD" not in fuente
    assert "balance_inicial = 0.0" not in fuente
    assert "incluir_costes_cuenta=True" in fuente
    assert "paper_fee_taker_bps_por_lado" in fuente
    assert "paper_order_book_provider" in fuente
    assert '"paper_order_book"' in fuente

    arbol = ast.parse(fuente)
    bucle = next(
        n for n in ast.walk(arbol)
        if isinstance(n, ast.FunctionDef) and n.name == "trading_loop"
    )
    for nodo in ast.walk(bucle):
        if isinstance(nodo, ast.Attribute) and nodo.attr == "positions":
            pytest.fail("trading_loop no debe acceder a simulator.positions")


def test_construir_cartera_elige_fuente_correcta(
    simulador, fabrica, usuario_id
):
    provider = BookProvider()
    paper = construir_cartera(
        modo_real=False,
        simulador=simulador,
        usuario_id=usuario_id,
        saldos_broker={"BTC": 5.0},
        usdt_broker=999.0,
        session_factory=fabrica,
        paper_initial_capital_usd=500.0,
        paper_fee_taker_bps_por_lado=10.0,
        paper_order_book_provider=provider,
    )
    assert isinstance(paper, CarteraPaper)
    assert paper.modo == "PAPER"
    assert paper.cantidad_disponible(SIMBOLO) == 0.0
    assert paper.capital_disponible() == pytest.approx(500.0), (
        "PAPER sale del ledger, no de los 1000 del Simulator ni de 999 del broker"
    )

    live = construir_cartera(
        modo_real=True,
        simulador=simulador,
        usuario_id=usuario_id,
        saldos_broker={"BTC": 5.0},
        usdt_broker=999.0,
        session_factory=fabrica,
    )
    assert isinstance(live, CarteraLive)
    assert live.modo == "LIVE"
    assert live.cantidad_disponible(SIMBOLO) == pytest.approx(5.0)
    assert live.capital_disponible() == pytest.approx(999.0)


def test_cartera_live_persiste_solo_tras_confirmacion(fabrica, usuario_id):
    class TraderQueFalla:
        def comprar(self, symbol, quote_amount, client_order_id=None):
            return ResultadoOrden(
                symbol=symbol,
                side=Lado.COMPRA,
                estado=EstadoOrden.ESTADO_DESCONOCIDO,
                error="broker caido",
            )

    live = CarteraLive(
        usuario_id=usuario_id,
        saldos_broker={},
        usdt_broker=100.0,
        session_factory=fabrica,
    )
    res = live.ejecutar(veredicto(Lado.COMPRA, quote=10.0), 100.0, trader=TraderQueFalla())

    assert res.success is False
    with fabrica() as db:
        assert db.query(models.Transaction).count() == 0
