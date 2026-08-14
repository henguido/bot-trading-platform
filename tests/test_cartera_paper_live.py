"""
P0-15 · PAPER debe ser realmente independiente de LIVE.

El bloque de limpieza antiguo comparaba las posiciones del Simulator con los
saldos reales de Binance. En PAPER el saldo real siempre es 0 para una posicion
simulada, asi que la borraba en cada ciclo y ademas escribia en la base de
datos. PAPER era inutilizable y contaminaba el ledger real.

La correccion es estructural: CarteraPaper no admite saldos del broker en su
constructor, de modo que no existe ningun camino por el que puedan entrar.
"""
import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.portafolio.carteras import CarteraLive, CarteraPaper, construir_cartera
from backend.risk.motor import DecisionRiesgo
from backend.simulation.simulator import Simulator

RAIZ = Path(__file__).resolve().parents[1]
SIMBOLO = "BTCUSDT"
PRECIO = 100000.0


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def simulador():
    sim = Simulator()
    sim.capital_usd = 1000.0
    return sim


def veredicto(side=Lado.COMPRA, base=0.001, quote=100.0):
    return DecisionRiesgo(aprobado=True, symbol=SIMBOLO, side=side,
                          approved_base_quantity=base, approved_quote_amount=quote)


class BrokerProhibido:
    """Si PAPER lo toca, la prueba falla."""
    def comprar(self, *a, **k):
        raise AssertionError("PAPER no debe llamar al broker")

    def vender(self, *a, **k):
        raise AssertionError("PAPER no debe llamar al broker")


# ── 1 · La posicion PAPER sobrevive entre ciclos ─────────────────────────────
def test_la_posicion_paper_sobrevive_entre_ciclos(simulador):
    cartera = CarteraPaper(simulador)
    cartera.ejecutar(veredicto(), PRECIO, trader=BrokerProhibido())
    assert cartera.cantidad_disponible(SIMBOLO) == pytest.approx(0.001)

    # Cinco ciclos completos: cada uno "limpia" con saldos de broker vacios.
    for _ in range(5):
        cartera.limpiar_posiciones_sin_respaldo({})
        assert cartera.cantidad_disponible(SIMBOLO) == pytest.approx(0.001), \
            "la posicion PAPER no puede desaparecer entre ciclos"


# ── 2 · Saldo de Binance = 0 no modifica la posicion PAPER ───────────────────
@pytest.mark.parametrize("saldos", [{}, {"BTC": 0.0}, {"BTC": 0.0, "USDT": 0.0}, None])
def test_saldo_broker_cero_no_altera_la_posicion_paper(simulador, saldos):
    cartera = CarteraPaper(simulador)
    cartera.ejecutar(veredicto(), PRECIO, trader=BrokerProhibido())

    tocadas = cartera.limpiar_posiciones_sin_respaldo(saldos)

    assert tocadas == 0
    assert cartera.cantidad_disponible(SIMBOLO) == pytest.approx(0.001)


# ── 3 · PAPER no escribe una transaccion como LIVE ──────────────────────────
def test_paper_no_escribe_transacciones_en_la_bd(simulador, fabrica):
    cartera = CarteraPaper(simulador)
    for _ in range(3):
        cartera.ejecutar(veredicto(), PRECIO, trader=BrokerProhibido())

    with fabrica() as db:
        assert db.query(models.Transaction).count() == 0, \
            "una operacion PAPER jamas puede aparecer en el ledger real"
        assert db.query(models.Portfolio).count() == 0


# ── 4 · PAPER no puede consultar el balance real ────────────────────────────
def test_cartera_paper_no_admite_saldos_del_broker():
    """
    Garantia estructural, no una comprobacion en tiempo de ejecucion:
    el constructor no tiene por donde recibir datos del exchange.
    """
    firma = inspect.signature(CarteraPaper.__init__)
    parametros = set(firma.parameters) - {"self"}
    assert parametros == {"simulador"}, (
        f"CarteraPaper solo debe recibir el simulador, recibe {parametros}"
    )
    assert CarteraPaper.usa_broker is False


def test_cartera_paper_no_referencia_saldos_ni_bd():
    """AST: la clase PAPER no menciona saldos del broker ni sesiones de BD."""
    fuente = Path(RAIZ, "backend", "portafolio", "carteras.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    clase = next(n for n in ast.walk(arbol)
                 if isinstance(n, ast.ClassDef) and n.name == "CarteraPaper")
    volcado = ast.dump(clase)
    for prohibido in ("_saldos", "session_factory", "guardar_transaccion_real",
                      "ejecutar_y_registrar_compra", "ejecutar_y_registrar_venta"):
        assert prohibido not in volcado, (
            f"CarteraPaper no debe referenciar {prohibido}"
        )


def test_main_no_compara_posiciones_simuladas_con_saldos_reales():
    """Regresion P0-15: el bloque de limpieza contra saldos reales desaparecio."""
    fuente = Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8")
    assert "Limpiando simulador y BD" not in fuente
    assert "balance_inicial = 0.0" not in fuente
    arbol = ast.parse(fuente)
    bucle = next(n for n in ast.walk(arbol)
                 if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")
    # En el bucle ya no se itera sobre simulator.positions.
    for nodo in ast.walk(bucle):
        if isinstance(nodo, ast.Attribute) and nodo.attr == "positions":
            assert False, "trading_loop no debe acceder a simulator.positions"


# ── 5 · Reiniciar un ciclo no destruye el estado PAPER ──────────────────────
def test_reiniciar_el_ciclo_no_destruye_el_estado_paper(simulador):
    cartera = CarteraPaper(simulador)
    cartera.ejecutar(veredicto(), PRECIO, trader=BrokerProhibido())
    estado_inicial = cartera.estado_riesgo()
    assert estado_inicial.cantidad_disponible(SIMBOLO) == pytest.approx(0.001)

    # Se reconstruye la cartera como haria el bucle en cada iteracion.
    for _ in range(3):
        nueva = construir_cartera(modo_real=False, simulador=simulador,
                                  saldos_broker={"BTC": 0.0}, usdt_broker=0.0)
        nueva.limpiar_posiciones_sin_respaldo({"BTC": 0.0})
        assert nueva.cantidad_disponible(SIMBOLO) == pytest.approx(0.001)
        assert nueva.estado_riesgo().cantidad_disponible(SIMBOLO) == pytest.approx(0.001)


# ── Selector de modo ────────────────────────────────────────────────────────
def test_construir_cartera_elige_el_modo_correcto(simulador):
    paper = construir_cartera(modo_real=False, simulador=simulador,
                              saldos_broker={"BTC": 5.0}, usdt_broker=999.0)
    assert isinstance(paper, CarteraPaper)
    assert paper.modo == "PAPER"
    assert paper.cantidad_disponible(SIMBOLO) == 0.0, \
        "los 5 BTC del broker NO deben filtrarse a la cartera PAPER"
    assert paper.capital_disponible() == pytest.approx(1000.0), \
        "el capital PAPER sale del simulador, no de los 999 USDT del broker"

    live = construir_cartera(modo_real=True, simulador=simulador, usuario_id=1,
                             saldos_broker={"BTC": 5.0}, usdt_broker=999.0)
    assert isinstance(live, CarteraLive)
    assert live.modo == "LIVE"
    assert live.cantidad_disponible(SIMBOLO) == pytest.approx(5.0)
    assert live.capital_disponible() == pytest.approx(999.0)


def test_cartera_live_persiste_solo_tras_confirmacion(fabrica):
    """LIVE mantiene el contrato de P0-2: sin fill confirmado, sin transaccion."""
    from backend.app.services.ordenes import EstadoOrden, ResultadoOrden

    class TraderQueFalla:
        def comprar(self, symbol, quote_amount, client_order_id=None):
            return ResultadoOrden(symbol=symbol, side=Lado.COMPRA,
                                  estado=EstadoOrden.ESTADO_DESCONOCIDO,
                                  error="broker caido")

    with fabrica() as db:
        u = models.User(nombre="T", email="t@e.com", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        uid = u.id

    live = CarteraLive(usuario_id=uid, saldos_broker={}, usdt_broker=100.0,
                       session_factory=fabrica)
    res = live.ejecutar(veredicto(), PRECIO, trader=TraderQueFalla())

    assert res.success is False
    with fabrica() as db:
        assert db.query(models.Transaction).count() == 0
