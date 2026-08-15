"""
P0-10 / P0-11 / P0-14 · Ciclo de vida confiable de una orden.

EL RESULTADO DEL TRANSPORTE NO ES EL ESTADO DE LA ORDEN.

Todo con brokers falsos. No se instancia ningun binance.Client real ni se envia
ninguna orden.
"""
import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services import ordenes_repo
from backend.app.services.ordenes import (
    ESTADOS_NO_TERMINALES,
    EstadoOrden,
    Lado,
    es_terminal,
    nuevo_client_order_id,
)
from backend.app.services.real_trading import ejecutar_y_registrar_compra
from backend.config import settings
from backend.connectors.apis.real_trading_connector import RealTradingConnector
from backend.reconciliacion import reconciliar_pendientes
from backend.risk.estado import calcular_estado_riesgo
from backend.risk.motor import MotorRiesgo, PropuestaOperacion

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
def usuario(fabrica):
    with fabrica() as db:
        u = models.User(nombre="T", email="t@e.com", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        return u.id


class ClienteFalso:
    """Sustituto de binance.Client. Cuenta cuantas ordenes recibe."""

    def __init__(self, *, precio=PRECIO, fallo_pre_envio=None, fallo_envio=None,
                 respuesta=None, orden_en_broker=None, trades=None):
        self.precio = precio
        self.fallo_pre_envio = fallo_pre_envio
        self.fallo_envio = fallo_envio
        self.respuesta = respuesta
        self.orden_en_broker = orden_en_broker
        self.trades = trades or []
        self.creaciones = 0
        self.consultas = 0

    def get_symbol_ticker(self, symbol):
        if self.fallo_pre_envio:
            raise self.fallo_pre_envio
        return {"price": str(self.precio)}

    def get_symbol_info(self, symbol):
        return {"filters": [{"filterType": "LOT_SIZE", "stepSize": "0.00000100"}]}

    def order_market_buy(self, symbol, quantity, newClientOrderId=None):
        self.creaciones += 1
        self.ultimo_cid = newClientOrderId
        if self.fallo_envio:
            raise self.fallo_envio
        return self.respuesta

    def order_market_sell(self, symbol, quantity, newClientOrderId=None):
        return self.order_market_buy(symbol, quantity, newClientOrderId)

    def get_order(self, symbol, origClientOrderId=None):
        self.consultas += 1
        if self.orden_en_broker is None:
            raise Exception("APIError(code=-2013): Order does not exist.")
        return dict(self.orden_en_broker, clientOrderId=origClientOrderId)

    def get_my_trades(self, symbol):
        return self.trades


def conector(cliente, monkeypatch):
    monkeypatch.setattr(settings, "MODO_REAL", True)
    c = RealTradingConnector.__new__(RealTradingConnector)
    c.client = cliente
    return c


def respuesta_llena(base=0.001, quote=100.0, fills=None):
    r = {"status": "FILLED", "executedQty": str(base), "origQty": str(base),
         "cummulativeQuoteQty": str(quote), "orderId": 555}
    if fills is not None:
        r["fills"] = fills
    return r


# ═══ 1 · Fallo ANTES del POST ════════════════════════════════════════════════
def test_1_fallo_antes_del_post_es_error_pre_envio(monkeypatch):
    cli = ClienteFalso(fallo_pre_envio=ConnectionError("no hay red para el ticker"))
    res = conector(cli, monkeypatch).comprar(SIMBOLO, quote_amount=100.0)

    assert res.estado is EstadoOrden.ERROR_PRE_ENVIO
    assert es_terminal(res.estado), "sin POST no hay orden: es terminal y seguro"
    assert cli.creaciones == 0, "el broker no debe haber recibido nada"


# ═══ 2 · Timeout DESPUES de enviar ═══════════════════════════════════════════
def test_2_timeout_tras_enviar_es_estado_desconocido(monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("read timeout"))
    res = conector(cli, monkeypatch).comprar(SIMBOLO, quote_amount=100.0)

    assert res.estado is EstadoOrden.ESTADO_DESCONOCIDO
    assert res.estado is not EstadoOrden.NO_EJECUTADA, \
        "un timeout NUNCA demuestra que la orden no exista"
    assert not es_terminal(res.estado)
    assert res.requiere_reconciliacion is True
    assert res.client_order_id and res.client_order_id.startswith("b-")
    assert cli.creaciones == 1


def test_2b_el_client_order_id_se_genera_antes_del_envio(monkeypatch):
    cli = ClienteFalso(respuesta=respuesta_llena())
    res = conector(cli, monkeypatch).comprar(SIMBOLO, quote_amount=100.0)
    assert cli.ultimo_cid == res.client_order_id, \
        "el broker debe recibir NUESTRA identidad de orden"
    assert len(res.client_order_id) <= 36, "Binance limita el clientOrderId a 36 chars"


# ═══ 3 · Timeout pero el broker SI ejecuto ═══════════════════════════════════
def test_3_reconciliador_descubre_el_fill_perdido(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(
        fallo_envio=TimeoutError("se perdio la respuesta"),
        orden_en_broker={"status": "FILLED", "executedQty": "0.001",
                         "cummulativeQuoteQty": "100", "orderId": 777},
        trades=[{"id": 9001, "orderId": 777, "price": "100000", "qty": "0.001",
                 "commission": "0.0000001", "commissionAsset": "BTC"}])
    trader = conector(cli, monkeypatch)

    res = ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                      quote_amount=100.0, session_factory=fabrica)
    assert res.estado is EstadoOrden.ESTADO_DESCONOCIDO
    with fabrica() as db:
        assert db.query(models.Transaction).count() == 0, "aun no sabemos nada"
        assert len(ordenes_repo.ordenes_no_terminales(db, usuario)) == 1

    resumen = reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica)

    assert resumen.resueltas == 1
    with fabrica() as db:
        orden = db.query(models.Orden).first()
        assert orden.estado == EstadoOrden.EJECUTADA.value
        assert db.query(models.Fill).count() == 1
        assert db.query(models.Transaction).count() == 1, \
            "el fill perdido se convierte en un apunte contable"


# ═══ 4 · El broker NO conoce el client_order_id ══════════════════════════════
def test_4_broker_no_conoce_la_orden_NO_se_concluye_no_ejecutada(
        fabrica, usuario, monkeypatch):
    """
    P0-17 cambio este contrato a proposito.

    Antes, una consulta negativa marcaba la orden como NO_EJECUTADA. En una
    operacion asincrona esa respuesta puede significar solo que el broker aun no
    ha propagado la orden; darla por inexistente y seguir comprando duplicaria
    una posicion real. Ahora se agotan los intentos y queda en un estado NO
    terminal que sigue bloqueando exposicion.
    """
    from backend.reconciliacion import PoliticaBackoff

    cli = ClienteFalso(fallo_envio=TimeoutError("timeout"), orden_en_broker=None)
    trader = conector(cli, monkeypatch)

    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)
    from datetime import datetime, timedelta
    momento = [datetime(2026, 8, 14, 12, 0, 0)]
    pol = PoliticaBackoff(intentos_maximos=2)
    for _ in range(pol.intentos_maximos):
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                               politica=pol, ahora=lambda: momento[0])
        momento[0] += timedelta(seconds=pol.espera_maxima_s + 1)

    with fabrica() as db:
        orden = db.query(models.Orden).first()
        assert orden.estado != EstadoOrden.NO_EJECUTADA.value, \
            "una consulta negativa NO es evidencia de que la orden no exista"
        assert orden.estado == EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA.value
        assert not es_terminal(orden.estado), "debe seguir bloqueando exposicion"
        assert db.query(models.Transaction).count() == 0


def test_4b_si_no_se_puede_consultar_sigue_desconocida(fabrica, usuario, monkeypatch):
    """Nunca se resuelve por omision ni por tiempo."""
    class ClienteSinConsulta(ClienteFalso):
        def get_order(self, symbol, origClientOrderId=None):
            raise ConnectionError("tampoco hay red para consultar")

    from backend.reconciliacion import PoliticaBackoff

    cli = ClienteSinConsulta(fallo_envio=TimeoutError("timeout"))
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)

    # Con un solo intento la orden ni siquiera agota la reconciliacion.
    resumen = reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                                     politica=PoliticaBackoff(intentos_maximos=3))
    assert resumen.sin_resolver == 1
    assert resumen.hay_incertidumbre is True
    with fabrica() as db:
        assert db.query(models.Orden).first().estado == EstadoOrden.ESTADO_DESCONOCIDO.value


# ═══ 5 y 6 · Reconciliar N veces no duplica ══════════════════════════════════
@pytest.mark.parametrize("veces", [2, 100])
def test_5_6_reconciliar_muchas_veces_no_duplica(fabrica, usuario, monkeypatch, veces):
    cli = ClienteFalso(
        fallo_envio=TimeoutError("timeout"),
        orden_en_broker={"status": "FILLED", "executedQty": "0.001",
                         "cummulativeQuoteQty": "100", "orderId": 777},
        trades=[{"id": 9001, "orderId": 777, "price": "100000", "qty": "0.001",
                 "commission": "0.0000001", "commissionAsset": "BTC"}])
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)

    for _ in range(veces):
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica)

    with fabrica() as db:
        assert db.query(models.Orden).count() == 1
        assert db.query(models.Fill).count() == 1, f"tras {veces} pasadas debe haber 1 fill"
        assert db.query(models.Transaction).count() == 1
        assert db.query(models.Transaction).first().cantidad == pytest.approx(0.001)


# ═══ 7 · Reinicio del proceso ════════════════════════════════════════════════
def test_7_reinicio_con_orden_desconocida_se_recupera(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("timeout"))
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)

    # "Reinicio": nada en memoria. El estado sale solo de la base de datos.
    with fabrica() as db:
        pendientes = ordenes_repo.ordenes_no_terminales(db, usuario)
        assert len(pendientes) == 1
        assert pendientes[0].estado == EstadoOrden.ESTADO_DESCONOCIDO.value

    cli.orden_en_broker = {"status": "FILLED", "executedQty": "0.001",
                           "cummulativeQuoteQty": "100", "orderId": 777}
    cli.trades = [{"id": 42, "orderId": 777, "price": "100000", "qty": "0.001",
                   "commission": "0.00000010", "commissionAsset": "BTC"}]
    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica)

    with fabrica() as db:
        assert ordenes_repo.hay_incertidumbre(db, usuario) is False


# ═══ 8 · El broker recibe UNA sola creacion ══════════════════════════════════
def test_8_sin_retry_ciego_el_broker_recibe_una_sola_creacion(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("timeout"),
                       orden_en_broker={"status": "FILLED", "executedQty": "0.001",
                                        "cummulativeQuoteQty": "100", "orderId": 1})
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)
    for _ in range(10):
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica)

    assert cli.creaciones == 1, \
        "la recuperacion consulta por client_order_id, nunca reenvia la orden"
    assert cli.consultas >= 1


# ═══ 9 · La BD impide duplicar la orden ══════════════════════════════════════
def test_9_dos_procesos_con_el_mismo_client_order_id(fabrica, usuario):
    cid = nuevo_client_order_id()
    with fabrica() as db:
        a = ordenes_repo.crear_intencion(db, client_order_id=cid, usuario_id=usuario,
                                         symbol=SIMBOLO, side="BUY",
                                         requested_quote_amount=100.0)
    with fabrica() as db:
        b = ordenes_repo.crear_intencion(db, client_order_id=cid, usuario_id=usuario,
                                         symbol=SIMBOLO, side="BUY",
                                         requested_quote_amount=100.0)
    assert a.id == b.id
    with fabrica() as db:
        assert db.query(models.Orden).count() == 1

    # Y la restriccion vive en la BASE DE DATOS, no solo en Python.
    with fabrica() as db:
        db.add(models.Orden(client_order_id=cid, broker="binance", symbol=SIMBOLO,
                            side="BUY", estado="CREADA"))
        with pytest.raises(IntegrityError):
            db.commit()


# ═══ 10 · La BD impide duplicar el fill ══════════════════════════════════════
def test_10_fill_repetido_lo_impide_la_base_de_datos(fabrica, usuario):
    with fabrica() as db:
        orden = ordenes_repo.crear_intencion(db, client_order_id=nuevo_client_order_id(),
                                             usuario_id=usuario, symbol=SIMBOLO, side="BUY")
        fill = {"trade_id": "555", "price": 100000.0, "qty": 0.001,
                "commission": 0.0000001, "commission_asset": "BTC"}
        for _ in range(5):
            ordenes_repo.procesar_fills(db, orden, [fill])
        assert db.query(models.Fill).count() == 1
        assert db.query(models.Transaction).count() == 1

        db.add(models.Fill(orden_id=orden.id, broker="binance", symbol=SIMBOLO,
                           trade_id="555", price=1.0, qty=1.0))
        with pytest.raises(IntegrityError):
            db.commit()


# ═══ 11 · La comision se conserva ════════════════════════════════════════════
def test_11_la_comision_del_fill_se_conserva(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(respuesta=respuesta_llena(fills=[
        {"tradeId": 1, "price": "100000", "qty": "0.0006",
         "commission": "0.00000060", "commissionAsset": "BTC"},
        {"tradeId": 2, "price": "100050", "qty": "0.0004",
         "commission": "0.00000040", "commissionAsset": "BTC"},
    ]))
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)

    with fabrica() as db:
        fills = db.query(models.Fill).order_by(models.Fill.trade_id).all()
        assert len(fills) == 2
        assert [f.commission for f in fills] == [pytest.approx(6e-7), pytest.approx(4e-7)]
        assert {f.commission_asset for f in fills} == {"BTC"}
        assert db.query(models.Transaction).count() == 2, "un apunte por fill"


# ═══ 12 · Una orden pendiente bloquea nueva compra ═══════════════════════════
def test_12_la_incertidumbre_bloquea_nueva_exposicion(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("timeout"))
    trader = conector(cli, monkeypatch)
    ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario, symbol=SIMBOLO,
                                quote_amount=100.0, session_factory=fabrica)

    estado = calcular_estado_riesgo(usuario, session_factory=fabrica)
    assert estado.ordenes_pendientes == 1

    motor = MotorRiesgo()
    compra = motor.evaluar(
        PropuestaOperacion(symbol=SIMBOLO, side=Lado.COMPRA, precio=PRECIO,
                           base_quantity_modelo=0.001),
        capital_disponible=1000.0, estado=estado)

    assert compra.aprobado is False
    assert compra.limite_violado == "RECONCILIACION_REQUERIDA"


# ═══ 13 · Politica de venta bajo incertidumbre ═══════════════════════════════
def test_13_bajo_incertidumbre_se_puede_reducir_riesgo(fabrica, usuario):
    """
    POLITICA EXPLICITA: la incertidumbre bloquea AUMENTAR exposicion, nunca
    reducirla. Poder salir de una posicion es justo lo que hay que preservar.
    La venta sigue acotada a la posicion confirmada: no se abre un corto.
    """
    from backend.risk.estado import EstadoRiesgo, Posicion
    from backend.risk import reloj

    estado = EstadoRiesgo(dia=reloj.dia_de_riesgo(),
                          posiciones={SIMBOLO: Posicion(cantidad=0.001, coste_medio=PRECIO)},
                          ordenes_pendientes=3)
    motor = MotorRiesgo()

    compra = motor.evaluar(PropuestaOperacion(symbol=SIMBOLO, side=Lado.COMPRA,
                                              precio=PRECIO, base_quantity_modelo=0.001),
                           capital_disponible=1000.0, estado=estado)
    assert compra.aprobado is False

    venta = motor.evaluar(PropuestaOperacion(symbol=SIMBOLO, side=Lado.VENTA,
                                             precio=PRECIO, base_quantity_modelo=0.01),
                          capital_disponible=1000.0, estado=estado)
    assert venta.aprobado is True, "reducir riesgo debe seguir permitido"
    assert venta.approved_base_quantity == pytest.approx(0.001), \
        "acotada a la posicion confirmada; nunca se abre un corto"


# ═══ 14 · Nadie puede saltarse el ciclo ══════════════════════════════════════
def test_14_toda_orden_pasa_por_el_ciclo_con_identidad():
    """AST: las ordenes se envian solo desde el conector, con client_order_id."""
    fuente = Path(RAIZ, "backend", "connectors", "apis",
                  "real_trading_connector.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    envios = [n for n in ast.walk(arbol)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ("order_market_buy", "order_market_sell")]
    assert envios, "no se encontraron envios de orden"
    for envio in envios:
        claves = {k.arg for k in envio.keywords}
        assert "newClientOrderId" in claves, (
            "toda creacion de orden debe llevar nuestro client_order_id; "
            "sin el no se puede reconciliar ni evitar duplicados"
        )


def test_14b_la_intencion_se_persiste_antes_del_envio():
    """AST: crear_intencion debe aparecer antes del envio en el flujo."""
    fuente = Path(RAIZ, "backend", "app", "services",
                  "real_trading.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_ejecutar_con_identidad")
    intencion = [n.lineno for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "crear_intencion"]
    envio = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "enviar"]
    assert intencion and envio
    assert min(intencion) < min(envio), \
        "la intencion debe persistirse ANTES de que el POST pueda salir"


def test_14c_no_hay_reintentos_ciegos_de_creacion():
    fuente = Path(RAIZ, "backend", "connectors", "apis",
                  "real_trading_connector.py").read_text(encoding="utf-8")
    assert "allowed_methods" not in fuente or "POST" not in fuente, \
        "no debe haber reintentos automaticos sobre POST de creacion de orden"
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.For, ast.While)):
            assert "order_market" not in ast.dump(nodo), \
                "una creacion de orden nunca puede estar dentro de un bucle de reintento"


# ═══ Estados ═════════════════════════════════════════════════════════════════
def test_clasificacion_de_estados():
    assert es_terminal(EstadoOrden.EJECUTADA)
    assert es_terminal(EstadoOrden.ERROR_PRE_ENVIO)
    assert es_terminal(EstadoOrden.NO_EJECUTADA)
    assert not es_terminal(EstadoOrden.ESTADO_DESCONOCIDO)
    assert not es_terminal(EstadoOrden.PARCIAL)
    assert EstadoOrden.ESTADO_DESCONOCIDO in ESTADOS_NO_TERMINALES
