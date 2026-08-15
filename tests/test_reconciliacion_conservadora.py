"""
P0-17 · La ausencia de evidencia no es evidencia de no ejecucion.

Antes, un unico `get_order` que respondia "no encontrada" bastaba para marcar la
orden como NO_EJECUTADA. En una operacion asincrona eso puede significar
simplemente que el broker aun no ha propagado la orden; darla por inexistente y
seguir comprando podria duplicar una posicion real.

Ningun test espera de verdad: el reloj se inyecta.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services import ordenes_repo
from backend.app.services.ordenes import ESTADOS_NO_TERMINALES, EstadoOrden, es_terminal
from backend.app.services.real_trading import ejecutar_y_registrar_compra
from backend.config import settings
from backend.connectors.apis.real_trading_connector import RealTradingConnector
from backend.reconciliacion import PoliticaBackoff, reconciliar_pendientes
from backend.risk.estado import calcular_estado_riesgo
from backend.risk.motor import MotorRiesgo, PropuestaOperacion
from backend.app.services.ordenes import Lado

SIMBOLO = "BTCUSDT"
PRECIO = 100000.0
RAPIDA = PoliticaBackoff(intentos_maximos=3, espera_inicial_s=1, factor=2)


class Reloj:
    """
    Reloj inyectable. Ninguna prueba espera de verdad: se adelanta el tiempo.

    El reconciliador no duerme; decide si toca reintentar comparando contra
    `ultimo_intento_en`. Por eso basta con avanzar el reloj.
    """
    def __init__(self, inicio=None):
        self.ahora = inicio or datetime(2026, 8, 14, 12, 0, 0)

    def __call__(self):
        return self.ahora

    def avanzar(self, segundos):
        self.ahora += timedelta(seconds=segundos)
        return self


def reconciliar_n_pasadas(trader, usuario, fabrica, reloj, politica, n, fuentes=None):
    """Invoca el reconciliador n veces, adelantando el reloj entre pasadas."""
    ultimo = None
    for i in range(n):
        ultimo = reconciliar_pendientes(trader, usuario_id=usuario,
                                        session_factory=fabrica, politica=politica,
                                        fuentes=fuentes, ahora=reloj)
        reloj.avanzar(politica.espera_maxima_s + 1)
    return ultimo


class ClienteFalso:
    def __init__(self, *, fallo_envio=None, respuesta=None, orden_en_broker=None,
                 trades=None, get_order_falla=False):
        self.fallo_envio = fallo_envio
        self.respuesta = respuesta
        self.orden_en_broker = orden_en_broker
        self.trades = trades or []
        self.get_order_falla = get_order_falla
        self.creaciones = 0
        self.consultas = 0

    def get_symbol_ticker(self, symbol):
        return {"price": str(PRECIO)}

    def get_symbol_info(self, symbol):
        return {"filters": [{"filterType": "LOT_SIZE", "stepSize": "0.00000100"}]}

    def order_market_buy(self, symbol, quantity, newClientOrderId=None):
        self.creaciones += 1
        if self.fallo_envio:
            raise self.fallo_envio
        return self.respuesta

    def order_market_sell(self, symbol, quantity, newClientOrderId=None):
        return self.order_market_buy(symbol, quantity, newClientOrderId)

    def get_order(self, symbol, origClientOrderId=None):
        self.consultas += 1
        if self.get_order_falla:
            raise ConnectionError("broker caido")
        if self.orden_en_broker is None:
            raise Exception("APIError(code=-2013): Order does not exist.")
        return dict(self.orden_en_broker, clientOrderId=origClientOrderId)

    def get_my_trades(self, symbol):
        return self.trades


@pytest.fixture
def fabrica():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    models.Base.metadata.create_all(bind=e)
    yield sessionmaker(autocommit=False, autoflush=False, bind=e)
    e.dispose()


@pytest.fixture
def usuario(fabrica):
    with fabrica() as db:
        u = models.User(nombre="T", email="t@e.com", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        return u.id


def conector(cli, monkeypatch):
    monkeypatch.setattr(settings, "MODO_REAL", True)
    c = RealTradingConnector.__new__(RealTradingConnector)
    c.client = cli
    return c


def compra_con_timeout(fabrica, usuario, cli, monkeypatch):
    trader = conector(cli, monkeypatch)
    res = ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario,
                                      symbol=SIMBOLO, quote_amount=100.0,
                                      session_factory=fabrica)
    return trader, res


def estado_de(fabrica):
    with fabrica() as db:
        return db.query(models.Orden).first().estado


# ── 1 · timeout POST -> desconocida ─────────────────────────────────────────
def test_1_timeout_post_deja_estado_desconocido(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("read timeout"))
    _, res = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    assert res.estado is EstadoOrden.ESTADO_DESCONOCIDO
    assert estado_de(fabrica) == EstadoOrden.ESTADO_DESCONOCIDO.value


# ── 2 y 3 · consultas negativas nunca concluyen NO_EJECUTADA ────────────────
def test_2_primer_get_negativo_sigue_desconocida(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=RAPIDA, ahora=reloj)

    assert estado_de(fabrica) == EstadoOrden.ESTADO_DESCONOCIDO.value, \
        "una consulta negativa no puede concluir nada"
    assert cli.consultas == 1, "una pasada = una consulta, sin polling agresivo"


def test_3_multiples_negativas_nunca_dan_no_ejecutada(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    resumen = reconciliar_n_pasadas(trader, usuario, fabrica, reloj, RAPIDA,
                                    RAPIDA.intentos_maximos)

    final = estado_de(fabrica)
    assert final != EstadoOrden.NO_EJECUTADA.value, \
        "jamas se concluye NO_EJECUTADA por consultas negativas"
    assert final == EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA.value
    assert not es_terminal(final), "debe seguir bloqueando exposicion"
    assert resumen.manuales == 1
    assert cli.consultas == RAPIDA.intentos_maximos


def test_3b_reconciliacion_manual_no_equivale_a_no_ejecutada():
    assert EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA != EstadoOrden.NO_EJECUTADA
    assert EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA in ESTADOS_NO_TERMINALES
    assert not es_terminal(EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA)


# ── Backoff acotado, sin polling agresivo ───────────────────────────────────
def test_backoff_es_creciente_y_acotado():
    pol = PoliticaBackoff(intentos_maximos=5, espera_inicial_s=2,
                          factor=2, espera_maxima_s=8)
    esperas = [pol.espera_para(i) for i in range(1, 6)]
    assert esperas == [0, 2, 4, 8, 8], f"backoff inesperado: {esperas}"
    assert max(esperas) <= pol.espera_maxima_s
    assert esperas == sorted(esperas), "debe ser no decreciente"


def test_no_hay_polling_agresivo(fabrica, usuario, monkeypatch):
    """Llamar al reconciliador dentro de la ventana no consulta al broker."""
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()
    pol = PoliticaBackoff(intentos_maximos=5, espera_inicial_s=30)

    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=pol, ahora=reloj)
    assert cli.consultas == 1

    for _ in range(20):          # el reloj NO avanza
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                               politica=pol, ahora=reloj)
    assert cli.consultas == 1, "dentro del backoff no debe consultarse al broker"

    reloj.avanzar(31)
    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=pol, ahora=reloj)
    assert cli.consultas == 2, "pasada la espera, si debe reintentarse"


# ── 4 · GET posterior FILLED -> exactamente 1 orden + 1 fill + 1 transaccion ─
def test_4_get_posterior_filled_resuelve_una_sola_vez(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    # Dos rondas negativas: sigue desconocida.
    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=PoliticaBackoff(intentos_maximos=2), ahora=reloj)
    assert estado_de(fabrica) == EstadoOrden.ESTADO_DESCONOCIDO.value

    # Ahora el broker si la conoce.
    cli.orden_en_broker = {"status": "FILLED", "executedQty": "0.001",
                           "cummulativeQuoteQty": "100", "orderId": 777}
    cli.trades = [{"id": 9001, "orderId": 777, "price": "100000", "qty": "0.001",
                   "commission": "0.0000001", "commissionAsset": "BTC"}]
    with fabrica() as db:                       # se rearman los intentos
        db.query(models.Orden).update({"intentos_reconciliacion": 0}); db.commit()

    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=RAPIDA, ahora=reloj)

    with fabrica() as db:
        assert db.query(models.Orden).count() == 1
        assert db.query(models.Orden).first().estado == EstadoOrden.EJECUTADA.value
        assert db.query(models.Fill).count() == 1
        assert db.query(models.Transaction).count() == 1


# ── 5 · Idempotencia con 100 pasadas ────────────────────────────────────────
def test_5_reconciliar_cien_veces_es_idempotente(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(
        fallo_envio=TimeoutError("t"),
        orden_en_broker={"status": "FILLED", "executedQty": "0.001",
                         "cummulativeQuoteQty": "100", "orderId": 777},
        trades=[{"id": 9001, "orderId": 777, "price": "100000", "qty": "0.001",
                 "commission": "0.0000001", "commissionAsset": "BTC"}])
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    for _ in range(100):
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                               politica=RAPIDA, ahora=reloj)

    with fabrica() as db:
        assert db.query(models.Orden).count() == 1
        assert db.query(models.Fill).count() == 1
        assert db.query(models.Transaction).count() == 1


# ── 6 · Reinicio conserva la incertidumbre ──────────────────────────────────
def test_6_reinicio_conserva_el_estado_y_los_intentos(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()
    reconciliar_n_pasadas(trader, usuario, fabrica, reloj,
                          PoliticaBackoff(intentos_maximos=3), 2)

    # "Reinicio": nada en memoria; todo sale de la base.
    with fabrica() as db:
        pend = ordenes_repo.ordenes_no_terminales(db, usuario)
        assert len(pend) == 1
        assert pend[0].estado == EstadoOrden.ESTADO_DESCONOCIDO.value
        assert pend[0].intentos_reconciliacion == 2, \
            "el contador debe persistir, no reiniciarse con el proceso"


# ── 7 · Broker caido -> permanece bloqueada ─────────────────────────────────
def test_7_broker_caido_permanece_bloqueada(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), get_order_falla=True)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    resumen = reconciliar_pendientes(trader, usuario_id=usuario,
                                     session_factory=fabrica,
                                     politica=RAPIDA, ahora=reloj)

    assert resumen.hay_incertidumbre is True
    assert estado_de(fabrica) != EstadoOrden.NO_EJECUTADA.value
    with fabrica() as db:
        assert ordenes_repo.hay_incertidumbre(db, usuario) is True


# ── 8 · Cero POST adicionales ───────────────────────────────────────────────
def test_8_nunca_se_reenvia_el_post(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()

    for _ in range(10):
        reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                               politica=RAPIDA, ahora=reloj)

    assert cli.creaciones == 1, "la recuperacion es por consulta, jamas reenviando"


# ── 9 · Compras bloqueadas; ventas permitidas ───────────────────────────────
def test_9_compras_bloqueadas_mientras_haya_incertidumbre(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()
    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=RAPIDA, ahora=reloj)

    estado = calcular_estado_riesgo(usuario, session_factory=fabrica)
    assert estado.ordenes_pendientes == 1, \
        "RECONCILIACION_MANUAL_REQUERIDA debe seguir contando como pendiente"

    motor = MotorRiesgo()
    compra = motor.evaluar(
        PropuestaOperacion(symbol=SIMBOLO, side=Lado.COMPRA, precio=PRECIO,
                           base_quantity_modelo=0.001),
        capital_disponible=1000.0, estado=estado)
    assert compra.aprobado is False
    assert compra.limite_violado == "RECONCILIACION_REQUERIDA"


def test_9b_la_venta_que_reduce_riesgo_sigue_permitida():
    from backend.risk import reloj as reloj_riesgo
    from backend.risk.estado import EstadoRiesgo, Posicion

    estado = EstadoRiesgo(dia=reloj_riesgo.dia_de_riesgo(),
                          posiciones={SIMBOLO: Posicion(cantidad=0.001,
                                                        coste_medio=PRECIO)},
                          ordenes_pendientes=2)
    venta = MotorRiesgo().evaluar(
        PropuestaOperacion(symbol=SIMBOLO, side=Lado.VENTA, precio=PRECIO,
                           base_quantity_modelo=0.01),
        capital_disponible=1000.0, estado=estado)

    assert venta.aprobado is True
    assert venta.approved_base_quantity == pytest.approx(0.001)


# ── 10 · client_order_id nunca se reutiliza ─────────────────────────────────
def test_10_el_client_order_id_nunca_se_reutiliza(fabrica, usuario, monkeypatch):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader = conector(cli, monkeypatch)
    vistos = set()
    for _ in range(5):
        res = ejecutar_y_registrar_compra(trader=trader, usuario_id=usuario,
                                          symbol=SIMBOLO, quote_amount=100.0,
                                          session_factory=fabrica)
        assert res.client_order_id not in vistos, "un cid no puede reutilizarse"
        vistos.add(res.client_order_id)

    with fabrica() as db:
        assert db.query(models.Orden).count() == 5
        cids = {o.client_order_id for o in db.query(models.Orden).all()}
        assert len(cids) == 5


# ── Evidencia explicita SI puede cerrar la orden ────────────────────────────
@pytest.mark.parametrize("status,esperado", [
    ("REJECTED", EstadoOrden.RECHAZADA),
    ("CANCELED", EstadoOrden.CANCELADA),
    ("EXPIRED", EstadoOrden.EXPIRADA),
])
def test_evidencia_explicita_del_broker_si_cierra(fabrica, usuario, monkeypatch,
                                                  status, esperado):
    cli = ClienteFalso(fallo_envio=TimeoutError("t"),
                       orden_en_broker={"status": status, "executedQty": "0",
                                        "cummulativeQuoteQty": "0", "orderId": 5})
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)
    reloj = Reloj()
    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=RAPIDA, ahora=reloj)

    assert estado_de(fabrica) == esperado.value
    assert es_terminal(esperado), "un rechazo explicito si es evidencia suficiente"


# ── Arquitectura multifuente ────────────────────────────────────────────────
def test_el_reconciliador_acepta_fuentes_alternativas(fabrica, usuario, monkeypatch):
    """get_order no es la unica fuente posible: el punto de extension existe."""
    from backend.reconciliacion import Evidencia

    class FuenteFalsa:
        nombre = "user_data_stream"
        def consultar(self, orden):
            return Evidencia(origen=self.nombre, estado_broker="FILLED",
                             ejecutado_base=0.001, ejecutado_quote=100.0,
                             broker_order_id="999",
                             fills=({"trade_id": "t1", "price": 100000.0,
                                     "qty": 0.001, "commission": 0.0,
                                     "commission_asset": "BTC"},))

    cli = ClienteFalso(fallo_envio=TimeoutError("t"), orden_en_broker=None)
    trader, _ = compra_con_timeout(fabrica, usuario, cli, monkeypatch)

    reconciliar_pendientes(trader, usuario_id=usuario, session_factory=fabrica,
                           politica=RAPIDA, fuentes=(FuenteFalsa(),), ahora=Reloj())

    assert estado_de(fabrica) == EstadoOrden.EJECUTADA.value
    assert cli.consultas == 0, "no se consulto REST: gano la fuente alternativa"
