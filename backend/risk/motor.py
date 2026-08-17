"""
Motor deterministico de gestion de riesgo.

PRINCIPIO CENTRAL: EL LLM PROPONE, EL MOTOR DECIDE.

Para las COMPRAS el modelo NO tiene ninguna autoridad sobre el tamano. El
importe autorizado se calcula desde cero con capital, limites y exposicion; la
`quantity` que devuelve GPT se conserva unicamente como dato de auditoria y
esta marcada como NO AUTORITATIVA. Dos propuestas identicas salvo por esa
cantidad producen exactamente el mismo tamano autorizado.

Para las VENTAS la asimetria es deliberada y esta acotada: el modelo puede
proponer un cierre parcial, pero el motor lo limita a la posicion realmente
disponible. Una venta solo puede REDUCIR exposicion, nunca aumentarla ni abrir
un corto, asi que dejar que el modelo elija cerrar menos es seguro por
construccion.

Fuera de alcance en esta fase: stop loss, take profit, trailing, sizing por
distancia al stop, risk/reward, VaR, correlacion y optimizacion de cartera.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

from backend.app.services.ordenes import Lado, es_cantidad_valida
from backend.config import settings
from backend.risk.estado import EstadoRiesgo


@dataclass(frozen=True)
class PropuestaOperacion:
    """Lo que el modelo sugiere. Solo `symbol`, `side` y `precio` son fiables."""
    symbol: str
    side: Lado
    precio: float
    # NO AUTORITATIVO PARA EJECUCION. Se conserva para auditoria y, en ventas,
    # como tope superior de un cierre parcial.
    base_quantity_modelo: Optional[float] = None
    min_notional: float = 0.0


@dataclass(frozen=True)
class LimiteCompra:
    """
    Importe maximo que el motor autoriza para UNA compra, y que limite manda.

    Se extrajo de `_evaluar_compra` en la fase 03A para que el Eligibility Gate
    pueda preguntar "cuanto se autorizaria aqui" SIN duplicar la formula. Existe
    una sola aritmetica de sizing de compra en el proyecto y es esta.
    """
    quote_permitido: float
    limite: str
    reglas: Tuple[str, ...]


@dataclass(frozen=True)
class DecisionRiesgo:
    aprobado: bool
    symbol: str
    side: Lado
    motivo: Optional[str] = None
    limite_violado: Optional[str] = None

    requested_by_model: Optional[float] = None      # base, NO autoritativo
    approved_base_quantity: float = 0.0
    approved_quote_amount: float = 0.0

    capital_available: float = 0.0
    current_exposure: float = 0.0                   # total, a coste, USDT
    exposure_symbol: float = 0.0
    daily_realized_pnl: float = 0.0
    kill_switch_activo: bool = False

    reglas_aplicadas: Tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        if self.aprobado:
            return (f"APROBADA {self.side.value} {self.symbol}: "
                    f"{self.approved_base_quantity} base / "
                    f"{self.approved_quote_amount} quote")
        return (f"RECHAZADA {self.side.value} {self.symbol}: {self.motivo}"
                + (f" [limite={self.limite_violado}]" if self.limite_violado else ""))


class MotorRiesgo:
    """
    Punto de paso obligatorio entre la senal y la ejecucion.

    Es puro: no abre sesiones, no llama a brokers y no muta nada. Recibe el
    estado ya reconstruido y devuelve un veredicto.
    """

    def __init__(self, *, config=settings):
        self.monto_maximo_usdt = float(config.MONTO_MAXIMO_USDT)
        self.limite_asignacion = float(config.LIMITE_ASIGNACION_POR_OPERACION)
        self.max_perdida_diaria = float(config.MAX_DAILY_LOSS_USDT)
        self.max_exposicion_total = float(config.MAX_EXPOSICION_TOTAL_USDT)
        self.max_exposicion_activo = float(config.MAX_EXPOSICION_POR_ACTIVO_USDT)

    # ── Kill switch ──────────────────────────────────────────────────────────
    def kill_switch_activo(self, estado: EstadoRiesgo) -> bool:
        """
        Se activa cuando la PERDIDA REALIZADA del dia alcanza el limite.
        Se basa en P&L realizado, no en fluctuaciones no realizadas.
        """
        return estado.pnl_realizado_dia <= -self.max_perdida_diaria

    # ── Dimensionamiento de compra: UNICA fuente de verdad ───────────────────
    def limite_compra(self, *, capital_disponible: float, estado: EstadoRiesgo,
                      symbol: str) -> LimiteCompra:
        """
        Importe maximo autorizado para comprar `symbol`, y el limite que manda.

        Es la UNICA aritmetica de sizing de compra del proyecto. `_evaluar_compra`
        la usa para decidir y el Eligibility Gate (03A) la usa para descartar
        candidatos ANTES de gastar IA. Que sea la misma llamada -y no una copia-
        es lo que garantiza que el filtro previo y la decision final no puedan
        discrepar.

        Funcion PURA: no lee configuracion nueva, no consulta nada, no muta. La
        cantidad propuesta por el modelo no participa.

        No aplica los filtros del exchange: aqui solo vive el limite de RIESGO.
        `min_notional`, `LOT_SIZE` y compania se comprueban despues, contra este
        importe, y nunca elevandolo.
        """
        margen_total = self.max_exposicion_total - estado.exposicion_total
        margen_activo = self.max_exposicion_activo - estado.exposicion_de(symbol)

        candidatos = {
            "MONTO_MAXIMO_USDT": self.monto_maximo_usdt,
            "LIMITE_ASIGNACION_POR_OPERACION": capital_disponible * self.limite_asignacion,
            "capital_disponible": capital_disponible,
            "MAX_EXPOSICION_TOTAL_USDT": margen_total,
            "MAX_EXPOSICION_POR_ACTIVO_USDT": margen_activo,
        }
        limite = min(candidatos, key=candidatos.get)
        return LimiteCompra(quote_permitido=candidatos[limite], limite=limite,
                            reglas=tuple(candidatos.keys()))

    # ── Evaluacion ───────────────────────────────────────────────────────────
    def evaluar(self, propuesta: PropuestaOperacion, *, capital_disponible: float,
                estado: EstadoRiesgo) -> DecisionRiesgo:
        if propuesta.side is Lado.COMPRA:
            return self._evaluar_compra(propuesta, capital_disponible, estado)
        return self._evaluar_venta(propuesta, capital_disponible, estado)

    # ── COMPRA ───────────────────────────────────────────────────────────────
    def _evaluar_compra(self, p, capital_disponible, estado) -> DecisionRiesgo:
        reglas = []
        base = dict(
            symbol=p.symbol, side=p.side,
            requested_by_model=p.base_quantity_modelo,
            capital_available=capital_disponible,
            current_exposure=estado.exposicion_total,
            exposure_symbol=estado.exposicion_de(p.symbol),
            daily_realized_pnl=estado.pnl_realizado_dia,
            kill_switch_activo=self.kill_switch_activo(estado),
        )

        reglas.append("precio_valido")
        if not es_cantidad_valida(p.precio):
            return DecisionRiesgo(aprobado=False, motivo=f"precio invalido: {p.precio!r}",
                                  limite_violado="precio_valido",
                                  reglas_aplicadas=tuple(reglas), **base)

        # min() ignora los NaN en silencio (toda comparacion con NaN es falsa),
        # asi que un capital no finito colandose aqui aprobaria un importe
        # arbitrario. Se valida explicitamente antes de dimensionar.
        reglas.append("capital_finito")
        if not math.isfinite(capital_disponible):
            return DecisionRiesgo(aprobado=False,
                                  motivo=f"capital disponible no finito: {capital_disponible!r}",
                                  limite_violado="capital_finito",
                                  reglas_aplicadas=tuple(reglas), **base)

        # P0-14: bajo incertidumbre no se abre exposicion nueva. Podriamos tener
        # una posicion real que el ledger local todavia no conoce.
        reglas.append("sin_ordenes_pendientes")
        if estado.ordenes_pendientes > 0:
            return DecisionRiesgo(
                aprobado=False,
                motivo=(f"reconciliacion requerida: {estado.ordenes_pendientes} "
                        f"orden(es) sin resolver. No se abre nueva exposicion "
                        f"hasta conocer su estado."),
                limite_violado="RECONCILIACION_REQUERIDA",
                reglas_aplicadas=tuple(reglas), **base)

        reglas.append("kill_switch_diario")
        if base["kill_switch_activo"]:
            return DecisionRiesgo(
                aprobado=False,
                motivo=(f"kill switch diario activo: perdida realizada "
                        f"{estado.pnl_realizado_dia:.2f} USDT alcanza el limite de "
                        f"{self.max_perdida_diaria:.2f}. No se permite aumentar exposicion."),
                limite_violado="MAX_DAILY_LOSS_USDT",
                reglas_aplicadas=tuple(reglas), **base)

        # ── DIMENSIONAMIENTO DESDE CERO ─────────────────────────────────────
        # La cantidad propuesta por el modelo NO participa en este calculo.
        lim = self.limite_compra(capital_disponible=capital_disponible,
                                 estado=estado, symbol=p.symbol)
        reglas.extend(lim.reglas)
        limite_violado = lim.limite
        quote_permitido = lim.quote_permitido

        if not es_cantidad_valida(quote_permitido):
            return DecisionRiesgo(
                aprobado=False,
                motivo=f"importe autorizado no operable: {quote_permitido:.6f} USDT "
                       f"(limitado por {limite_violado})",
                limite_violado=limite_violado,
                reglas_aplicadas=tuple(reglas), **base)

        reglas.append("min_notional")
        if quote_permitido < p.min_notional:
            # No se eleva hasta el minimo: eso violaria nuestros propios limites.
            return DecisionRiesgo(
                aprobado=False,
                motivo=(f"el importe autorizado {quote_permitido:.6f} USDT es menor que el "
                        f"minimo del exchange {p.min_notional:.6f}. La operacion se rechaza; "
                        f"no se aumenta el tamano para alcanzarlo."),
                limite_violado="min_notional",
                reglas_aplicadas=tuple(reglas), **base)

        base_quantity = quote_permitido / p.precio
        if not es_cantidad_valida(base_quantity):
            return DecisionRiesgo(aprobado=False,
                                  motivo=f"cantidad base resultante invalida: {base_quantity!r}",
                                  limite_violado="cantidad_base",
                                  reglas_aplicadas=tuple(reglas), **base)

        return DecisionRiesgo(aprobado=True, approved_quote_amount=quote_permitido,
                              approved_base_quantity=base_quantity,
                              limite_violado=None, reglas_aplicadas=tuple(reglas), **base)

    # ── VENTA ────────────────────────────────────────────────────────────────
    def _evaluar_venta(self, p, capital_disponible, estado) -> DecisionRiesgo:
        reglas = ["posicion_disponible"]
        disponible = estado.cantidad_disponible(p.symbol)
        base = dict(
            symbol=p.symbol, side=p.side,
            requested_by_model=p.base_quantity_modelo,
            capital_available=capital_disponible,
            current_exposure=estado.exposicion_total,
            exposure_symbol=estado.exposicion_de(p.symbol),
            daily_realized_pnl=estado.pnl_realizado_dia,
            kill_switch_activo=self.kill_switch_activo(estado),
        )

        # El kill switch NO bloquea las ventas: impedir salir de una posicion
        # seria exactamente lo contrario de proteger el capital.
        if disponible <= 0:
            return DecisionRiesgo(aprobado=False,
                                  motivo=f"no hay posicion abierta en {p.symbol}",
                                  limite_violado="posicion_disponible",
                                  reglas_aplicadas=tuple(reglas), **base)

        solicitado = p.base_quantity_modelo
        if not es_cantidad_valida(solicitado):
            return DecisionRiesgo(aprobado=False,
                                  motivo=f"cantidad de venta invalida: {solicitado!r}",
                                  limite_violado="cantidad_base",
                                  reglas_aplicadas=tuple(reglas), **base)

        # Se acota a la posicion real: nunca se abre un corto por accidente.
        reglas.append("tope_posicion")
        aprobada = min(float(solicitado), disponible)
        if not es_cantidad_valida(aprobada):
            return DecisionRiesgo(aprobado=False,
                                  motivo="cantidad de venta resultante invalida",
                                  limite_violado="cantidad_base",
                                  reglas_aplicadas=tuple(reglas), **base)

        return DecisionRiesgo(aprobado=True, approved_base_quantity=aprobada,
                              approved_quote_amount=aprobada * p.precio if es_cantidad_valida(p.precio) else 0.0,
                              limite_violado=None, reglas_aplicadas=tuple(reglas), **base)
