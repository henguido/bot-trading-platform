"""
P0-1 y P0-2 · Semantica de unidades y confirmacion de ejecucion.

P0-1  main.py llamaba vender(symbol, cantidad_usdt=precio*cantidad). Doble
      error: el keyword no existia (TypeError) y la unidad era un importe en
      USDT donde se esperaba cantidad de activo base. Con BTC a 100.000 y
      0.001 BTC, habria intentado vender 100 BTC en lugar de 0.001.

P0-2  comprar()/vender() capturaban toda excepcion y devolvian None. El
      llamador no comprobaba el retorno y registraba igualmente la operacion
      en el simulador y en la base de datos, aunque la orden real hubiese
      fallado.

NINGUNA prueba contacta con Binance: el conector se construye sin __init__ y
se le inyecta un cliente falso. Se comprueba ademas que el cliente falso nunca
reciba ordenes cuando la validacion debe rechazarlas antes.
"""
import ast
import math
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import (
    EstadoOrden,
    Lado,
    ResultadoOrden,
    es_cantidad_valida,
    interpretar_respuesta_binance,
)
from backend.app.services.real_trading import (
    cargar_contexto_usuario,
    ejecutar_y_registrar_compra,
    ejecutar_y_registrar_venta,
)
from backend.config import settings
from backend.connectors.apis.real_trading_connector import RealTradingConnector

RAIZ = Path(__file__).resolve().parents[1]
PRECIO_BTC = 100000.0
SIMBOLO = "BTCUSDT"


# ─────────────────────────────────────────────────────────────────────────────
# Dobles de prueba
# ─────────────────────────────────────────────────────────────────────────────
class ClienteBinanceFalso:
    """Sustituto de binance.Client. Registra lo que se le pide. Cero red."""

    def __init__(self, precio=PRECIO_BTC, respuesta=None, excepcion=None, step="0.00000100"):
        self.precio = precio
        self.respuesta = respuesta
        self.excepcion = excepcion
        self.step = step
        self.ordenes_recibidas = []

    def get_symbol_ticker(self, symbol):
        return {"price": str(self.precio)}

    def get_symbol_info(self, symbol):
        return {"filters": [{"filterType": "LOT_SIZE", "stepSize": self.step}]}

    def _orden(self, lado, symbol, quantity):
        self.ordenes_recibidas.append({"side": lado, "symbol": symbol, "quantity": quantity})
        if self.excepcion:
            raise self.excepcion
        return self.respuesta

    def order_market_buy(self, symbol, quantity, newClientOrderId=None):
        self.ultimo_client_order_id = newClientOrderId
        return self._orden("BUY", symbol, quantity)

    def order_market_sell(self, symbol, quantity, newClientOrderId=None):
        self.ultimo_client_order_id = newClientOrderId
        return self._orden("SELL", symbol, quantity)


def respuesta_llena(base, quote, order_id="12345"):
    return {"status": "FILLED", "executedQty": str(base),
            "cummulativeQuoteQty": str(quote), "orderId": order_id}


def conector_con(cliente, monkeypatch):
    """
    Construye el conector SIN ejecutar __init__ (que crearia un Client real de
    python-binance) y habilita la rama LIVE en memoria. Con un cliente falso
    inyectado no se emite ninguna orden real.
    """
    monkeypatch.setattr(settings, "MODO_REAL", True)
    conector = RealTradingConnector.__new__(RealTradingConnector)
    conector.client = cliente
    return conector


class TraderFalso:
    """Doble del conector para probar la regla de persistencia."""

    def __init__(self, resultado_compra=None, resultado_venta=None):
        self.resultado_compra = resultado_compra
        self.resultado_venta = resultado_venta
        self.llamadas = []

    def comprar(self, symbol, quote_amount, client_order_id=None):
        self.llamadas.append(("comprar", symbol, {"quote_amount": quote_amount}))
        self.ultimo_cid = client_order_id
        return self.resultado_compra

    def vender(self, symbol, base_quantity, client_order_id=None):
        self.llamadas.append(("vender", symbol, {"base_quantity": base_quantity}))
        self.ultimo_cid = client_order_id
        return self.resultado_venta


@pytest.fixture
def fabrica_sesiones():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def usuario(fabrica_sesiones):
    with fabrica_sesiones() as db:
        u = models.User(nombre="T", email="t@e.com", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        return u.id


def contar_transacciones(fabrica):
    with fabrica() as db:
        return db.query(models.Transaction).count()


def ejecutada(base, quote, side=Lado.COMPRA):
    return ResultadoOrden(symbol=SIMBOLO, side=side, estado=EstadoOrden.EJECUTADA,
                          executed_base_quantity=base, executed_quote_amount=quote,
                          average_fill_price=quote / base, order_id="1")


# ═════════════════════════════════════════════════════════════════════════════
# COMPRA EXITOSA
# ═════════════════════════════════════════════════════════════════════════════
def test_compra_exitosa_convierte_quote_a_base(monkeypatch):
    """100 USDT a 100.000 USDT/BTC deben pedirse como 0.001 BTC, no como 100."""
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(0.001, 100))
    conector = conector_con(cliente, monkeypatch)

    res = conector.comprar(SIMBOLO, quote_amount=100.0)

    assert cliente.ordenes_recibidas[0]["quantity"] == pytest.approx(0.001), \
        "se debe pedir 0.001 BTC, no 100"
    assert res.success is True
    assert res.estado is EstadoOrden.EJECUTADA
    assert res.executed_base_quantity == pytest.approx(0.001)
    assert res.average_fill_price == pytest.approx(PRECIO_BTC)
    assert res.order_id == "12345"
    assert res.requested_quote_amount == pytest.approx(100.0)


def test_compra_exitosa_persiste_exactamente_una_transaccion(fabrica_sesiones, usuario):
    trader = TraderFalso(resultado_compra=ejecutada(0.001, 100.0))

    res = ejecutar_y_registrar_compra(
        trader=trader, usuario_id=usuario, symbol=SIMBOLO, quote_amount=100.0,
        precio_referencia=PRECIO_BTC, session_factory=fabrica_sesiones)

    assert res.success is True
    assert contar_transacciones(fabrica_sesiones) == 1

    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.estado[SIMBOLO]["cantidad"] == pytest.approx(0.001)
    assert ctx.estado[SIMBOLO]["precio_promedio"] == pytest.approx(PRECIO_BTC)


def test_se_persiste_la_cantidad_EJECUTADA_no_la_solicitada(fabrica_sesiones, usuario):
    """Fill parcial: se pidieron 100 USDT pero solo se llenaron 0.0006 BTC."""
    parcial = ResultadoOrden(symbol=SIMBOLO, side=Lado.COMPRA, estado=EstadoOrden.EJECUTADA,
                             requested_quote_amount=100.0,
                             executed_base_quantity=0.0006, executed_quote_amount=60.0,
                             average_fill_price=100000.0, order_id="9")
    trader = TraderFalso(resultado_compra=parcial)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica_sesiones)

    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.estado[SIMBOLO]["cantidad"] == pytest.approx(0.0006), \
        "debe guardarse lo ejecutado, no lo solicitado"


# ═════════════════════════════════════════════════════════════════════════════
# COMPRA RECHAZADA
# ═════════════════════════════════════════════════════════════════════════════
def test_compra_rechazada_por_el_broker_no_persiste_nada(fabrica_sesiones, usuario, monkeypatch):
    cliente = ClienteBinanceFalso(respuesta={"status": "REJECTED", "executedQty": "0",
                                             "cummulativeQuoteQty": "0", "orderId": 7})
    conector = conector_con(cliente, monkeypatch)

    res = ejecutar_y_registrar_compra(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica_sesiones)

    assert res.success is False
    assert res.estado is EstadoOrden.RECHAZADA
    assert res.executed_base_quantity == 0.0, "no se inventan fills"
    assert contar_transacciones(fabrica_sesiones) == 0

    ctx = cargar_contexto_usuario(session_factory=fabrica_sesiones)
    assert ctx.estado == {}, "el contexto posterior no debe cambiar"


def test_orden_aceptada_pero_sin_fill_no_es_ejecucion(fabrica_sesiones, usuario, monkeypatch):
    cliente = ClienteBinanceFalso(respuesta={"status": "NEW", "executedQty": "0",
                                             "cummulativeQuoteQty": "0", "orderId": 8})
    conector = conector_con(cliente, monkeypatch)
    res = ejecutar_y_registrar_compra(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica_sesiones)
    assert res.estado is EstadoOrden.NO_EJECUTADA
    assert res.success is False
    assert contar_transacciones(fabrica_sesiones) == 0


# ═════════════════════════════════════════════════════════════════════════════
# EXCEPCION DEL BROKER
# ═════════════════════════════════════════════════════════════════════════════
def test_excepcion_del_broker_no_rompe_el_flujo_ni_persiste(fabrica_sesiones, usuario, monkeypatch):
    cliente = ClienteBinanceFalso(excepcion=ConnectionError("timeout hablando con Binance"))
    conector = conector_con(cliente, monkeypatch)

    res = ejecutar_y_registrar_compra(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica_sesiones)

    # P0-10: la excepcion ocurre durante el POST, asi que la orden PUDO llegar.
    assert res.estado is EstadoOrden.ESTADO_DESCONOCIDO, \
        "un fallo tras enviar no puede darse por no ejecutado"
    assert res.estado is not EstadoOrden.NO_EJECUTADA
    assert res.client_order_id, "debe conservarse la identidad para reconciliar"
    assert res.success is False
    assert "ConnectionError" in res.error and "timeout" in res.error
    assert contar_transacciones(fabrica_sesiones) == 0


# ═════════════════════════════════════════════════════════════════════════════
# VENTA
# ═════════════════════════════════════════════════════════════════════════════
def test_venta_envia_cantidad_base_no_importe(monkeypatch):
    """Posicion 0.001 BTC a 100.000 -> debe venderse 0.001, jamas 100."""
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(0.001, 100))
    conector = conector_con(cliente, monkeypatch)

    res = conector.vender(SIMBOLO, base_quantity=0.001)

    enviado = cliente.ordenes_recibidas[0]["quantity"]
    assert enviado == pytest.approx(0.001), f"se envio {enviado}, se esperaba 0.001"
    assert enviado != pytest.approx(100.0), "100 seria el importe en USDT, no la cantidad de BTC"
    assert res.success is True
    assert res.requested_base_quantity == pytest.approx(0.001)


def test_venta_correcta_persiste_una_transaccion(fabrica_sesiones, usuario):
    trader = TraderFalso(resultado_venta=ejecutada(0.001, 100.0, side=Lado.VENTA))
    res = ejecutar_y_registrar_venta(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                     base_quantity=0.001, session_factory=fabrica_sesiones)
    assert res.success is True
    assert trader.llamadas == [("vender", SIMBOLO, {"base_quantity": 0.001})]
    assert contar_transacciones(fabrica_sesiones) == 1


def test_venta_rechazada_no_persiste_y_deja_la_posicion_intacta(fabrica_sesiones, usuario, monkeypatch):
    # Posicion previa real: una compra confirmada.
    ejecutar_y_registrar_compra(trader=TraderFalso(resultado_compra=ejecutada(0.001, 100.0)),
                                usuario_id=usuario, symbol=SIMBOLO, quote_amount=100.0,
                                session_factory=fabrica_sesiones)
    antes = cargar_contexto_usuario(session_factory=fabrica_sesiones).estado[SIMBOLO]

    cliente = ClienteBinanceFalso(respuesta={"status": "REJECTED", "executedQty": "0",
                                             "cummulativeQuoteQty": "0", "orderId": 3})
    conector = conector_con(cliente, monkeypatch)
    res = ejecutar_y_registrar_venta(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                     base_quantity=0.001, session_factory=fabrica_sesiones)

    assert res.success is False
    assert contar_transacciones(fabrica_sesiones) == 1, "sigue existiendo solo la compra"
    despues = cargar_contexto_usuario(session_factory=fabrica_sesiones).estado[SIMBOLO]
    assert despues == antes, "la posicion no debe cambiar tras una venta rechazada"


# ═════════════════════════════════════════════════════════════════════════════
# CANTIDADES INVALIDAS
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("valor", [0, 0.0, -1, -0.001, float("nan"),
                                   float("inf"), float("-inf"), None, "0.001", True])
def test_cantidades_invalidas_se_rechazan_antes_del_broker(valor, monkeypatch):
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(1, 1))
    conector = conector_con(cliente, monkeypatch)

    compra = conector.comprar(SIMBOLO, quote_amount=valor)
    venta = conector.vender(SIMBOLO, base_quantity=valor)

    assert compra.estado is EstadoOrden.RECHAZADA, f"compra con {valor!r} debe rechazarse"
    assert venta.estado is EstadoOrden.RECHAZADA, f"venta con {valor!r} debe rechazarse"
    assert cliente.ordenes_recibidas == [], f"{valor!r} nunca debe llegar al broker"


@pytest.mark.parametrize("simbolo", ["", "   ", None, "BTC/USDT", 123])
def test_simbolos_invalidos_se_rechazan_antes_del_broker(simbolo, monkeypatch):
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(1, 1))
    conector = conector_con(cliente, monkeypatch)
    assert conector.comprar(simbolo, quote_amount=100).estado is EstadoOrden.RECHAZADA
    assert cliente.ordenes_recibidas == []


def test_es_cantidad_valida():
    assert es_cantidad_valida(0.001) and es_cantidad_valida(100)
    for malo in (0, -1, float("nan"), float("inf"), None, "1", True):
        assert not es_cantidad_valida(malo), f"{malo!r} no deberia ser valido"


# ═════════════════════════════════════════════════════════════════════════════
# PAPER vs LIVE
# ═════════════════════════════════════════════════════════════════════════════
def test_en_paper_no_se_intenta_ninguna_orden_real():
    """MODO_REAL=False: el conector bloquea sin llegar al cliente."""
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(1, 1))
    conector = RealTradingConnector.__new__(RealTradingConnector)
    conector.client = cliente
    assert settings.MODO_REAL is False

    res = conector.comprar(SIMBOLO, quote_amount=100.0)
    assert res.estado is EstadoOrden.BLOQUEADA_PAPER
    assert res.success is False
    assert cliente.ordenes_recibidas == []


def test_una_orden_live_fallida_no_se_convierte_en_paper_ejecutada(fabrica_sesiones, usuario, monkeypatch):
    """Separacion estricta: LIVE fallido no debe aparecer como PAPER ejecutado."""
    from backend.simulation.simulator import Simulator

    simulador = Simulator()
    cliente = ClienteBinanceFalso(excepcion=RuntimeError("broker caido"))
    conector = conector_con(cliente, monkeypatch)

    res = ejecutar_y_registrar_compra(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica_sesiones)

    assert res.success is False
    assert contar_transacciones(fabrica_sesiones) == 0
    assert simulador.positions == {}, "un fallo en LIVE no puede crear posicion simulada"
    assert simulador.history == []


# ═════════════════════════════════════════════════════════════════════════════
# REGRESION P0-1
# ═════════════════════════════════════════════════════════════════════════════
def test_regresion_p0_1_la_llamada_antigua_es_imposible(monkeypatch):
    """La firma antigua vender(cantidad_usdt=...) ya no puede ni invocarse."""
    conector = conector_con(ClienteBinanceFalso(respuesta=respuesta_llena(0.001, 100)), monkeypatch)
    with pytest.raises(TypeError):
        conector.vender(SIMBOLO, cantidad_usdt=PRECIO_BTC * 0.001)


def test_regresion_p0_1_pasar_el_importe_como_base_seria_catastrofico(monkeypatch):
    """
    Demuestra la magnitud del bug antiguo: precio * cantidad = 100. Si eso se
    pasa como base_quantity, se pide vender 100 BTC en vez de 0.001.
    """
    cliente = ClienteBinanceFalso(respuesta=respuesta_llena(100, 10_000_000))
    conector = conector_con(cliente, monkeypatch)

    quote_amount_erroneo = PRECIO_BTC * 0.001  # = 100, el calculo del codigo antiguo
    conector.vender(SIMBOLO, base_quantity=quote_amount_erroneo)

    assert cliente.ordenes_recibidas[0]["quantity"] == pytest.approx(100.0)
    assert cliente.ordenes_recibidas[0]["quantity"] / 0.001 == pytest.approx(100000.0), \
        "seria 100.000 veces la posicion real"


RUTA_EJECUCION = Path("backend", "portafolio", "carteras.py")


def test_la_ejecucion_vive_en_un_unico_modulo():
    """
    main.py no debe llamar directamente a la ejecucion: pasa por la cartera.
    Asi la separacion PAPER/LIVE no depende de ifs dispersos (P0-15).
    """
    arbol = ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))
    directas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) in ("ejecutar_y_registrar_compra",
                                                    "ejecutar_y_registrar_venta")]
    assert not directas, "main.py debe ejecutar a traves de la cartera, no directamente"


def test_regresion_p0_1_la_venta_no_multiplica_precio_por_cantidad():
    """Guarda estructural: la venta nunca puede pasar un importe como cantidad."""
    arbol = ast.parse(Path(RAIZ, RUTA_EJECUCION).read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "ejecutar_y_registrar_venta"]
    assert llamadas, f"no se encontro la ejecucion de venta en {RUTA_EJECUCION}"
    for llamada in llamadas:
        claves = {k.arg for k in llamada.keywords}
        assert "base_quantity" in claves, "la venta debe recibir base_quantity"
        assert "cantidad_usdt" not in claves and "quote_amount" not in claves
        arg = next(k.value for k in llamada.keywords if k.arg == "base_quantity")
        assert not isinstance(arg, ast.BinOp), \
            "base_quantity no puede ser el resultado de una multiplicacion"


# ═════════════════════════════════════════════════════════════════════════════
# REGRESION P0-2
# ═════════════════════════════════════════════════════════════════════════════
def test_regresion_p0_2_el_codigo_antiguo_habria_persistido_una_compra_fallida(
        fabrica_sesiones, usuario, monkeypatch):
    """
    Contraste explicito. El patron antiguo era:

        try:
            real_trader.comprar(...)          # traga la excepcion, devuelve None
            simulator.simulate_trade(...)     # se ejecuta igual
            guardar_transaccion_real(...)     # se ejecuta igual
        except Exception: print(...)

    Con el broker caido, aquello persistia 1 transaccion inexistente.
    El codigo nuevo persiste 0.
    """
    from backend.app.services.real_trading import guardar_transaccion_real
    from backend.simulation.simulator import Simulator

    cliente = ClienteBinanceFalso(excepcion=RuntimeError("broker caido"))
    conector = conector_con(cliente, monkeypatch)
    simulador_antiguo = Simulator()
    # Capital suficiente para que la simulacion no se frene por falta de fondos:
    # lo que se quiere demostrar es el registro indebido, no el limite de capital.
    simulador_antiguo.capital_usd = 1000.0

    # --- COMPORTAMIENTO ANTIGUO reproducido ---
    try:
        conector.comprar(SIMBOLO, quote_amount=100.0)   # no lanza: devuelve ERROR
        simulador_antiguo.simulate_trade(SIMBOLO, "COMPRAR", PRECIO_BTC, 0.001)
        with fabrica_sesiones() as db:
            guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                     action="COMPRAR", price=PRECIO_BTC, quantity=0.001)
    except Exception:
        pass

    persistidas_antiguo = contar_transacciones(fabrica_sesiones)
    assert persistidas_antiguo == 1, \
        "el patron antiguo persistia una compra que nunca se ejecuto"
    assert simulador_antiguo.positions[SIMBOLO].quantity > 0, \
        "y ademas la reflejaba en el simulador"

    # --- COMPORTAMIENTO NUEVO ---
    with fabrica_sesiones() as db:
        db.query(models.Transaction).delete()
        db.commit()

    res = ejecutar_y_registrar_compra(trader=conector, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica_sesiones)

    assert res.success is False
    assert contar_transacciones(fabrica_sesiones) == 0, \
        "el codigo nuevo NO persiste una compra que el broker no confirmo"


def test_regresion_p0_2_main_solo_persiste_tras_confirmacion():
    """
    Guarda estructural: main.py ya no llama a guardar_transaccion_real desde el
    bucle. La persistencia vive tras la comprobacion de .success dentro de
    ejecutar_y_registrar_*.
    """
    arbol = ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "trading_loop":
            llamadas = [n for n in ast.walk(nodo)
                        if isinstance(n, ast.Call)
                        and getattr(n.func, "id", None) == "guardar_transaccion_real"]
            assert not llamadas, (
                "trading_loop no debe persistir transacciones directamente; "
                "debe hacerlo ejecutar_y_registrar_* tras confirmar el fill"
            )
            return
    pytest.fail("no se encontro trading_loop")


# ═════════════════════════════════════════════════════════════════════════════
# LECTURA DE LA RESPUESTA DEL BROKER
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("respuesta,estado", [
    # Sin respuesta legible no podemos afirmar que no se ejecuto.
    (None, EstadoOrden.ESTADO_DESCONOCIDO),
    ("texto", EstadoOrden.ESTADO_DESCONOCIDO),
    ({"status": "FILLED", "executedQty": "abc"}, EstadoOrden.ESTADO_DESCONOCIDO),
    ({"status": "EXPIRED", "executedQty": "0"}, EstadoOrden.EXPIRADA),
    ({"status": "CANCELED", "executedQty": "0"}, EstadoOrden.CANCELADA),
    ({"status": "NEW", "executedQty": "0"}, EstadoOrden.NO_EJECUTADA),
    ({}, EstadoOrden.NO_EJECUTADA),
])
def test_interpretacion_de_respuestas_sin_fill(respuesta, estado):
    res = interpretar_respuesta_binance(respuesta, SIMBOLO, Lado.COMPRA, quote_amount=100)
    assert res.estado is estado
    assert res.success is False
    assert res.executed_base_quantity == 0.0, "jamas se inventan fills"


def test_precio_medio_se_calcula_del_fill_real():
    res = interpretar_respuesta_binance(
        {"status": "FILLED", "executedQty": "0.002", "cummulativeQuoteQty": "220",
         "orderId": 42}, SIMBOLO, Lado.COMPRA, quote_amount=220)
    assert res.success is True
    assert res.average_fill_price == pytest.approx(110000.0)
    assert res.order_id == "42"
