"""
Separacion estructural PAPER / LIVE  (P0-15, PAPER v1).

Cada modo tiene una fuente de verdad distinta y el bucle habla unicamente con
esta interfaz:

    CarteraPaper   journal persistente `paper_operaciones`. Reconstruye capital,
                   posiciones y P&L neto; usa profundidad publica solo al
                   simular un fill. Nunca recibe saldos del broker ni envia
                   ordenes reales.

    CarteraLive    estado en la base de datos + saldos del exchange. Persiste
                   solo tras confirmacion del broker.

No se mezclan tablas: PAPER nunca escribe `transacciones`, `ordenes` ni `fills`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from backend.app.database import SessionLocal
from backend.app.services.ordenes import (
    EstadoOrden,
    Lado,
    ResultadoOrden,
    error_pre_envio,
)
from backend.app.services.real_trading import (
    ejecutar_y_registrar_compra,
    ejecutar_y_registrar_venta,
)
from backend.config import settings
from backend.economia.ejecucion_paper import calcular_fill_compra, calcular_fill_venta
from backend.finanzas import precio_medio_de
from backend.risk import elegibilidad, reloj
from backend.risk.estado import EstadoRiesgo, Posicion, calcular_estado_riesgo
from backend.simulation.paper_ledger import (
    estado_desde_db,
    obtener_o_crear_ledger,
    registrar_fill,
    ultima_venta_desde_db,
)

_BPS = Decimal("10000")


@dataclass(frozen=True)
class ContextoPosicionLLM:
    """Vista financiera de una posicion desde la fuente del modo ACTIVO."""

    cantidad: float
    precio_medio: Optional[float]
    ultimo_movimiento: Any = None
    ultimo_precio_venta: Optional[float] = None


class CarteraPaper:
    """Cartera PAPER persistente y economicamente conservadora.

    La fuente de verdad es el journal de la BD. El constructor no admite
    saldos del broker ni trader. Las dependencias externas opcionales son
    proveedores publicos de profundidad y reglas del simbolo, usados solo
    despues de que MotorRiesgo haya aprobado una operacion.

    Si `symbol_info_provider` se configura, los filtros LOT_SIZE/NOTIONAL se
    vuelven obligatorios (fail-closed). Omitir el proveedor conserva el contrato
    de pruebas/consumidores legacy que ejercitan la cartera de forma aislada.
    """

    modo = "PAPER"
    usa_broker = False

    def __init__(
        self,
        *,
        usuario_id,
        session_factory=SessionLocal,
        initial_capital_usd=None,
        fee_taker_bps_por_lado=None,
        order_book_provider=None,
        symbol_info_provider=None,
    ):
        if usuario_id is None:
            raise ValueError("CarteraPaper exige usuario_id")
        self.usuario_id = usuario_id
        self._session_factory = session_factory
        self._initial_capital_usd = float(
            settings.INITIAL_CAPITAL_USD
            if initial_capital_usd is None else initial_capital_usd
        )
        self._fee_taker_bps_por_lado = fee_taker_bps_por_lado
        self._order_book_provider = order_book_provider
        self._symbol_info_provider = symbol_info_provider

    def _estado(self, *, dia=None):
        """Reconstruye desde el journal; crea el ledger una sola vez si falta."""
        with self._session_factory() as db:
            ledger = obtener_o_crear_ledger(
                db,
                usuario_id=self.usuario_id,
                initial_capital_usd=self._initial_capital_usd,
            )
            estado = estado_desde_db(db, ledger, dia=dia)
            db.commit()
            return estado

    def capital_disponible(self) -> float:
        return float(self._estado().capital_usd)

    def cantidad_disponible(self, symbol) -> float:
        posicion = self._estado().posiciones.get(str(symbol).strip().upper())
        return float(posicion.cantidad) if posicion else 0.0

    def contexto_posicion_llm(self, symbol) -> ContextoPosicionLLM:
        symbol = str(symbol).strip().upper()
        with self._session_factory() as db:
            ledger = obtener_o_crear_ledger(
                db,
                usuario_id=self.usuario_id,
                initial_capital_usd=self._initial_capital_usd,
            )
            estado = estado_desde_db(db, ledger)
            posicion = estado.posiciones.get(symbol)
            ultimo_precio_venta = ultima_venta_desde_db(db, ledger, symbol)
            db.commit()

        return ContextoPosicionLLM(
            cantidad=float(posicion.cantidad) if posicion else 0.0,
            precio_medio=(float(posicion.coste_medio_neto) if posicion else None),
            ultimo_movimiento=None,
            ultimo_precio_venta=ultimo_precio_venta,
        )

    def portafolio_para_llm(self):
        estado = self._estado()
        salida = []
        if estado.capital_usd > 0:
            salida.append({"moneda": "USDT", "cantidad": round(estado.capital_usd, 6)})
        for symbol, posicion in sorted(estado.posiciones.items()):
            if posicion.cantidad <= 0:
                continue
            moneda = symbol[:-4] if symbol.endswith("USDT") else symbol
            salida.append({"moneda": moneda, "cantidad": round(posicion.cantidad, 6)})
        return salida

    def estado_riesgo(self, dia=None):
        dia = dia or reloj.dia_de_riesgo()
        estado = self._estado(dia=dia)
        return EstadoRiesgo(
            dia=dia,
            posiciones={
                symbol: Posicion(
                    cantidad=posicion.cantidad,
                    coste_medio=posicion.coste_medio_neto,
                )
                for symbol, posicion in estado.posiciones.items()
            },
            pnl_realizado_dia=estado.realized_pnl_dia_usd,
            operaciones_dia=estado.operaciones_dia,
            ordenes_pendientes=0,
        )

    def limpiar_posiciones_sin_respaldo(self, saldos_broker=None) -> int:
        return 0

    @staticmethod
    def _decimal_positivo(valor, nombre):
        try:
            d = Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"{nombre} no es numerico") from None
        if not d.is_finite() or d <= 0:
            raise ValueError(f"{nombre} debe ser finito y positivo")
        return d

    def _fee_bps(self):
        return self._decimal_positivo(
            self._fee_taker_bps_por_lado,
            "fee_taker_bps_por_lado",
        )

    def _obtener_book(self, symbol):
        if not callable(self._order_book_provider):
            raise ValueError("PAPER no tiene proveedor de profundidad")
        book = self._order_book_provider(symbol)
        if not isinstance(book, dict):
            raise ValueError("profundidad PAPER no disponible")
        return book

    def _filtros_ejecucion(self, symbol):
        """Devuelve kwargs de ejecución Binance o vacío en modo legacy aislado."""
        if self._symbol_info_provider is None:
            return {}
        if not callable(self._symbol_info_provider):
            raise ValueError("PAPER tiene proveedor de filtros invalido")
        info = self._symbol_info_provider(symbol)
        filtros = elegibilidad.leer_filtros(info)
        if filtros is None:
            raise ValueError(f"PAPER no tiene LOT_SIZE/NOTIONAL validos para {symbol}")
        return {
            "step_size": filtros.step_size,
            "min_qty": filtros.min_qty,
            "max_qty": filtros.max_qty,
            "min_notional": filtros.min_notional,
        }

    def ejecutar(self, veredicto, precio, *, trader=None, economics=None) -> ResultadoOrden:
        symbol = veredicto.symbol
        lado = veredicto.side
        try:
            fee_bps = self._fee_bps()
            book = self._obtener_book(symbol)
            filtros = self._filtros_ejecucion(symbol)

            if lado is Lado.COMPRA:
                aprobado = self._decimal_positivo(
                    veredicto.approved_quote_amount,
                    "approved_quote_amount",
                )
                factor_fee = Decimal("1") + fee_bps / _BPS
                presupuesto_bruto = aprobado / factor_fee
                fill = calcular_fill_compra(
                    order_book=book,
                    quote_amount=presupuesto_bruto,
                    fee_taker_bps_por_lado=fee_bps,
                    **filtros,
                )
                requested_quote = float(aprobado)
                requested_base = None
            else:
                base = self._decimal_positivo(
                    veredicto.approved_base_quantity,
                    "approved_base_quantity",
                )
                fill = calcular_fill_venta(
                    order_book=book,
                    base_quantity=base,
                    fee_taker_bps_por_lado=fee_bps,
                    **filtros,
                )
                requested_quote = None
                requested_base = float(base)
        except Exception as exc:
            return error_pre_envio(
                symbol,
                lado,
                f"PAPER no pudo modelar ejecucion: {type(exc).__name__}: {exc}",
                base_quantity=(None if lado is Lado.COMPRA else
                               getattr(veredicto, "approved_base_quantity", None)),
                quote_amount=(getattr(veredicto, "approved_quote_amount", None)
                              if lado is Lado.COMPRA else None),
            )

        if not fill.completo:
            return error_pre_envio(
                symbol,
                lado,
                f"PAPER sin fill completo: {fill.motivo or fill.estado}",
                base_quantity=requested_base,
                quote_amount=requested_quote,
            )

        if lado is Lado.COMPRA:
            if fill.quote_neto is None or fill.quote_neto > aprobado + Decimal("1e-12"):
                return error_pre_envio(
                    symbol,
                    lado,
                    "PAPER excederia el capital aprobado al incluir la fee",
                    quote_amount=requested_quote,
                )

        try:
            with self._session_factory() as db:
                ledger = obtener_o_crear_ledger(
                    db,
                    usuario_id=self.usuario_id,
                    initial_capital_usd=self._initial_capital_usd,
                )
                economics = economics if isinstance(economics, dict) else {}
                registrar_fill(
                    db,
                    ledger=ledger,
                    symbol=symbol,
                    reference_price=precio,
                    fill=fill,
                    strategy=economics.get("strategy"),
                    expected_edge_bps=economics.get("expected_edge_bps"),
                    expected_cost_bps=economics.get("expected_cost_bps"),
                    expected_net_bps=economics.get("expected_net_bps"),
                )
                db.commit()
        except Exception as exc:
            return error_pre_envio(
                symbol,
                lado,
                f"PAPER no pudo persistir fill: {type(exc).__name__}: {exc}",
                base_quantity=requested_base,
                quote_amount=requested_quote,
            )

        return ResultadoOrden(
            symbol=symbol,
            side=lado,
            estado=EstadoOrden.EJECUTADA,
            requested_base_quantity=requested_base,
            requested_quote_amount=requested_quote,
            executed_base_quantity=float(fill.base_ejecutada),
            executed_quote_amount=float(fill.quote_bruto),
            average_fill_price=float(fill.precio_vwap),
            order_id=None,
        )


class CarteraLive:
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
        return ContextoPosicionLLM(
            cantidad=self.cantidad_disponible(symbol),
            precio_medio=precio_medio_de(self._estado_persistente, symbol),
            ultimo_movimiento=self._ultimos_movimientos.get(symbol),
            ultimo_precio_venta=self._ultimos_precios_venta.get(symbol),
        )

    def portafolio_para_llm(self):
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
        return 0

    def ejecutar(self, veredicto, precio, *, trader, economics=None) -> ResultadoOrden:
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
    metodo = getattr(cartera, "portafolio_para_llm", None)
    if callable(metodo):
        return metodo()
    capital = float(cartera.capital_disponible())
    return ([{"moneda": "USDT", "cantidad": round(capital, 6)}]
            if capital > 0 else [])


def construir_cartera(
    *,
    modo_real,
    simulador=None,
    usuario_id=None,
    saldos_broker=None,
    usdt_broker=0.0,
    session_factory=None,
    estado_persistente=None,
    ultimos_movimientos=None,
    ultimos_precios_venta=None,
    paper_initial_capital_usd=None,
    paper_fee_taker_bps_por_lado=None,
    paper_order_book_provider=None,
    paper_symbol_info_provider=None,
):
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
    return CarteraPaper(
        usuario_id=usuario_id,
        session_factory=session_factory or SessionLocal,
        initial_capital_usd=(settings.INITIAL_CAPITAL_USD
                             if paper_initial_capital_usd is None
                             else paper_initial_capital_usd),
        fee_taker_bps_por_lado=paper_fee_taker_bps_por_lado,
        order_book_provider=paper_order_book_provider,
        symbol_info_provider=paper_symbol_info_provider,
    )