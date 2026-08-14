"""
Separacion estructural PAPER / LIVE  (P0-15).

Antes, el bucle de trading manipulaba a la vez el Simulator, los saldos reales
de Binance y la base de datos. En PAPER eso provocaba que el bloque de limpieza
viese `saldo_real == 0` para toda posicion simulada y la borrase en cada ciclo,
ademas de escribir en la BD. PAPER era inutilizable y contaminaba el ledger.

La correccion no es repartir `if not MODO_REAL` por el codigo. Cada modo tiene
su propia clase, y el bucle habla UNICAMENTE con la interfaz:

    CarteraPaper   estado en el Simulator (memoria). NUNCA recibe saldos del
                   broker: no existe ningun parametro por el que pudieran
                   entrar. Nunca escribe en la base de datos.

    CarteraLive    estado en la base de datos + saldos del exchange. Persiste
                   solo tras confirmacion del broker.

Que PAPER ignore los saldos reales no es una comprobacion en tiempo de
ejecucion: es que su constructor no los admite.
"""
from __future__ import annotations

from backend.app.services.ordenes import EstadoOrden, Lado, ResultadoOrden
from backend.app.services.real_trading import (
    ejecutar_y_registrar_compra,
    ejecutar_y_registrar_venta,
)
from backend.risk.estado import calcular_estado_riesgo, calcular_estado_riesgo_paper


class CarteraPaper:
    """
    Cartera simulada. Su unica fuente de verdad es el Simulator en memoria.

    Deliberadamente NO recibe `saldos_broker` ni `usuario_id`: no puede leer
    saldos reales ni escribir transacciones LIVE aunque alguien lo intente.
    """

    modo = "PAPER"
    usa_broker = False

    def __init__(self, simulador):
        self._sim = simulador

    def capital_disponible(self) -> float:
        return float(self._sim.capital_usd)

    def cantidad_disponible(self, symbol) -> float:
        posicion = self._sim.positions.get(symbol)
        return float(posicion.quantity) if posicion else 0.0

    def estado_riesgo(self, dia=None):
        return calcular_estado_riesgo_paper(self._sim, dia=dia)

    def limpiar_posiciones_sin_respaldo(self, saldos_broker=None) -> int:
        """
        No-op POR DEFINICION.

        Una posicion PAPER no tiene ni debe tener respaldo en el exchange. Este
        era exactamente el bug P0-15: comparar posiciones simuladas contra
        saldos reales las borraba en cada ciclo. El parametro se acepta y se
        ignora para mantener una interfaz unica.
        """
        return 0

    def ejecutar(self, veredicto, precio, *, trader=None) -> ResultadoOrden:
        """Aplica la operacion al libro en memoria. Jamas toca la BD."""
        accion = "COMPRAR" if veredicto.side is Lado.COMPRA else "VENDER"
        self._sim.simulate_trade(veredicto.symbol, accion, precio,
                                 veredicto.approved_base_quantity)
        return ResultadoOrden(
            symbol=veredicto.symbol, side=veredicto.side,
            estado=EstadoOrden.EJECUTADA,
            executed_base_quantity=veredicto.approved_base_quantity,
            executed_quote_amount=veredicto.approved_base_quantity * precio,
            average_fill_price=precio,
            order_id=None,
        )


class CarteraLive:
    """
    Cartera real. Estado en la base de datos; saldos y ejecucion en el exchange.

    Solo se instancia cuando MODO_REAL esta activo. Persiste unicamente tras la
    confirmacion del broker (contrato de P0-1/P0-2).
    """

    modo = "LIVE"
    usa_broker = True

    def __init__(self, *, usuario_id, saldos_broker, usdt_broker, session_factory=None):
        self.usuario_id = usuario_id
        self._saldos = dict(saldos_broker or {})
        self._usdt = float(usdt_broker or 0.0)
        self._session_factory = session_factory

    def capital_disponible(self) -> float:
        return self._usdt

    def cantidad_disponible(self, symbol) -> float:
        return float(self._saldos.get(symbol.replace("USDT", ""), 0.0))

    def estado_riesgo(self, dia=None):
        kwargs = {"dia": dia}
        if self._session_factory is not None:
            kwargs["session_factory"] = self._session_factory
        return calcular_estado_riesgo(self.usuario_id, **kwargs)

    def limpiar_posiciones_sin_respaldo(self, saldos_broker=None) -> int:
        """
        Reservado para la reconciliacion real (P0-14), aun no implementada.

        El bloque antiguo reseteaba `Portfolio.balance_inicial` a partir de los
        saldos del exchange, lo que no es reconciliacion sino perdida de datos:
        borraba el historial local sin consultar las ordenes del broker. Se
        deja como no-op explicito hasta tener el reconciliador.
        """
        return 0

    def ejecutar(self, veredicto, precio, *, trader) -> ResultadoOrden:
        extra = ({"session_factory": self._session_factory}
                 if self._session_factory is not None else {})
        if veredicto.side is Lado.COMPRA:
            return ejecutar_y_registrar_compra(
                trader=trader, usuario_id=self.usuario_id, symbol=veredicto.symbol,
                quote_amount=veredicto.approved_quote_amount,
                precio_referencia=precio, **extra)
        return ejecutar_y_registrar_venta(
            trader=trader, usuario_id=self.usuario_id, symbol=veredicto.symbol,
            base_quantity=veredicto.approved_base_quantity,
            precio_referencia=precio, **extra)


def construir_cartera(*, modo_real, simulador, usuario_id=None,
                      saldos_broker=None, usdt_broker=0.0, session_factory=None):
    """
    Unico punto donde se decide el modo. A partir de aqui el bucle no vuelve a
    preguntar si estamos en PAPER o en LIVE.
    """
    if modo_real:
        return CarteraLive(usuario_id=usuario_id, saldos_broker=saldos_broker,
                           usdt_broker=usdt_broker, session_factory=session_factory)
    return CarteraPaper(simulador)
