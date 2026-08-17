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

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.ordenes import EstadoOrden, Lado, ResultadoOrden
from backend.app.services.real_trading import (
    ejecutar_y_registrar_compra,
    ejecutar_y_registrar_venta,
)
from backend.finanzas import precio_medio_de
from backend.risk.estado import calcular_estado_riesgo, calcular_estado_riesgo_paper


@dataclass(frozen=True)
class ContextoPosicionLLM:
    """Vista financiera de una posicion desde la fuente del modo ACTIVO."""

    cantidad: float
    precio_medio: Optional[float]
    ultimo_movimiento: Any = None
    ultimo_precio_venta: Optional[float] = None


def _ultimo_precio_venta_paper(simulador, symbol):
    """Ultimo precio de venta del libro PAPER, o None si no existe."""
    for entrada in reversed(getattr(simulador, "history", ()) or ()):
        if not isinstance(entrada, dict):
            continue
        if entrada.get("symbol") != symbol or entrada.get("action") != "VENTA":
            continue
        try:
            precio = float(entrada.get("price"))
        except (TypeError, ValueError):
            return None
        return precio if precio > 0 else None
    return None


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

    def contexto_posicion_llm(self, symbol) -> ContextoPosicionLLM:
        """
        Contexto para IA exclusivamente desde el libro PAPER.

        Ningun dato de coste, movimiento o saldo se consulta en la BD ni en el
        broker. Asi GPT, RiskEngine y ejecucion observan el mismo modo.
        """
        posicion = self._sim.positions.get(symbol)
        cantidad = float(posicion.quantity) if posicion else 0.0
        medio = None
        movimiento = None
        if posicion is not None:
            movimiento = getattr(posicion, "last_movement", None)
            try:
                candidato = float(getattr(posicion, "average_price", 0.0) or 0.0)
            except (TypeError, ValueError):
                candidato = 0.0
            if cantidad > 0 and candidato > 0:
                medio = candidato
        return ContextoPosicionLLM(
            cantidad=cantidad,
            precio_medio=medio,
            ultimo_movimiento=movimiento,
            ultimo_precio_venta=_ultimo_precio_venta_paper(self._sim, symbol),
        )

    def portafolio_para_llm(self):
        """Snapshot del portafolio PAPER; nunca contiene balances del broker."""
        salida = []
        capital = self.capital_disponible()
        if capital > 0:
            salida.append({"moneda": "USDT", "cantidad": round(capital, 6)})
        for symbol, posicion in sorted(self._sim.positions.items()):
            try:
                cantidad = float(posicion.quantity)
            except (TypeError, ValueError):
                continue
            if cantidad <= 0:
                continue
            moneda = symbol[:-4] if symbol.endswith("USDT") else symbol
            salida.append({"moneda": moneda, "cantidad": round(cantidad, 6)})
        return salida

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

    def __init__(self, *, usuario_id, saldos_broker, usdt_broker, session_factory=None,
                 estado_persistente=None, ultimos_movimientos=None,
                 ultimos_precios_venta=None):
        self.usuario_id = usuario_id
        self._saldos = dict(saldos_broker or {})
        self._usdt = float(usdt_broker or 0.0)
        self._session_factory = session_factory
        self._estado_persistente = dict(estado_persistente or {})
        self._ultimos_movimientos = dict(ultimos_movimientos or {})
        self._ultimos_precios_venta = dict(ultimos_precios_venta or {})

    def capital_disponible(self) -> float:
        return self._usdt

    def cantidad_disponible(self, symbol) -> float:
        return float(self._saldos.get(symbol.replace("USDT", ""), 0.0))

    def contexto_posicion_llm(self, symbol) -> ContextoPosicionLLM:
        """Contexto LIVE: saldo broker + coste/historial persistente."""
        return ContextoPosicionLLM(
            cantidad=self.cantidad_disponible(symbol),
            precio_medio=precio_medio_de(self._estado_persistente, symbol),
            ultimo_movimiento=self._ultimos_movimientos.get(symbol),
            ultimo_precio_venta=self._ultimos_precios_venta.get(symbol),
        )

    def portafolio_para_llm(self):
        """Snapshot LIVE exclusivamente desde los saldos del broker."""
        salida = []
        for moneda, cantidad_bruta in sorted(self._saldos.items()):
            try:
                cantidad = float(cantidad_bruta)
            except (TypeError, ValueError):
                continue
            if cantidad > 0:
                salida.append({"moneda": moneda, "cantidad": round(cantidad, 6)})
        return salida

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


def contexto_posicion_para_llm(cartera, symbol) -> ContextoPosicionLLM:
    """
    Adaptador para el bucle y sus dobles de prueba.

    Las carteras reales implementan `contexto_posicion_llm`. Un doble antiguo
    que solo exponga `cantidad_disponible` degrada de forma segura a cantidad +
    metadatos desconocidos; nunca consulta otra fuente por su cuenta.
    """
    metodo = getattr(cartera, "contexto_posicion_llm", None)
    if callable(metodo):
        return metodo(symbol)
    return ContextoPosicionLLM(
        cantidad=float(cartera.cantidad_disponible(symbol)),
        precio_medio=None,
        ultimo_movimiento=None,
        ultimo_precio_venta=None,
    )


def portafolio_para_llm(cartera):
    """Snapshot financiero del modo activo, con fallback seguro para dobles."""
    metodo = getattr(cartera, "portafolio_para_llm", None)
    if callable(metodo):
        return metodo()
    capital = float(cartera.capital_disponible())
    return ([{"moneda": "USDT", "cantidad": round(capital, 6)}]
            if capital > 0 else [])


def construir_cartera(*, modo_real, simulador, usuario_id=None,
                      saldos_broker=None, usdt_broker=0.0, session_factory=None,
                      estado_persistente=None, ultimos_movimientos=None,
                      ultimos_precios_venta=None):
    """
    Unico punto donde se decide el modo. A partir de aqui el bucle no vuelve a
    preguntar si estamos en PAPER o en LIVE.
    """
    if modo_real:
        return CarteraLive(
            usuario_id=usuario_id,
            saldos_broker=saldos_broker,
            usdt_broker=usdt_broker,
            session_factory=session_factory,
            estado_persistente=estado_persistente,
            ultimos_movimientos=ultimos_movimientos,
            ultimos_precios_venta=ultimos_precios_venta,
        )
    return CarteraPaper(simulador)
