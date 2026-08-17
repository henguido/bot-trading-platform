"""
Eligibility Gate deterministico  (Fase BOT 2.0-03A).

QUE RESUELVE
    En el ciclo PAPER real de 02B, GPT analizo 484 activos (14.521 tokens de
    entrada) y propuso comprar ETCUSDT. El MotorRiesgo autorizo 0,400000 USDT
    y Binance exige un minimo de 5,000000: RECHAZADA_RIESGO / min_notional.

    El motor actuo bien. El desperdicio estaba ANTES: se pago el analisis de IA
    de un candidato que era demostrablemente inejecutable sin preguntar nada.

QUE HACE
    Antes de construir el universo que va al LLM, demuestra -sin red, sin IA y
    sin aleatoriedad- si existe alguna cantidad ejecutable para una COMPRA
    nueva respetando SIMULTANEAMENTE los filtros del exchange y el limite de
    riesgo vigente. Si no existe, el activo no se envia.

QUE NO HACE
    No decide, no dimensiona y no autoriza nada. Solo puede QUITAR candidatos.
    El MotorRiesgo sigue siendo la unica autoridad y vuelve a evaluar de cero
    cada decision. Un gate permisivo de mas es inocuo; por eso, ante cualquier
    duda -filtros ausentes, valores ilegibles- se declara INELEGIBLE para
    compra nueva (fail-closed), que es la direccion segura.

UNA SOLA ARITMETICA DE RIESGO
    El importe maximo autorizado NO se recalcula aqui: se pide a
    `MotorRiesgo.limite_compra()`. No existe una formula de riesgo en el gate y
    otra en el motor.

VENTAS
    Este modulo evalua UNICAMENTE compras nuevas. Una posicion abierta jamas se
    filtra por elegibilidad de compra: el bot nunca puede quedarse sin poder
    vender por culpa de un filtro pensado para comprar. Esa preservacion la
    aplica el llamador (ver `ResumenElegibilidad.preservar`).

DECIMAL, NO FLOAT
    Toda la aritmetica de cantidades y notionales usa `Decimal` construido
    desde `str`. Con float, 4.999999999999999 pasaria por 5,0 y produciriamos
    una orden que el exchange rechaza. Los redondeos replican los de la
    ejecucion y SIEMPRE son a la baja: nunca se eleva el tamano para alcanzar
    un minimo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# CODIGOS DE MOTIVO
#
# Estables y comparables: la logica se apoya en el CODIGO, nunca en un texto.
# Se derivan de lo que el codigo real comprueba hoy, no de una lista teorica.
# ─────────────────────────────────────────────────────────────────────────────
ELEGIBLE = "ELEGIBLE"
NO_TRADING = "NO_TRADING"                      # status != TRADING
NO_SPOT = "NO_SPOT"                            # isSpotTradingAllowed False
SIN_PRECIO = "SIN_PRECIO"                      # ausente, <=0, NaN o infinito
FILTROS_INVALIDOS = "FILTROS_INVALIDOS"        # faltan LOT_SIZE/NOTIONAL o ilegibles
CAPITAL_RIESGO_INSUFICIENTE = "CAPITAL_RIESGO_INSUFICIENTE"   # autorizado <= 0
LOT_SIZE_INCOMPATIBLE = "LOT_SIZE_INCOMPATIBLE"              # no cabe ni un stepSize
MIN_QTY_INALCANZABLE = "MIN_QTY_INALCANZABLE"                # minQty excede el riesgo
MIN_NOTIONAL_INALCANZABLE = "MIN_NOTIONAL_INALCANZABLE"      # minNotional > autorizado
MAX_QTY_INCOMPATIBLE = "MAX_QTY_INCOMPATIBLE"                # maxQty impide el minimo

MOTIVOS = (ELEGIBLE, NO_TRADING, NO_SPOT, SIN_PRECIO, FILTROS_INVALIDOS,
           CAPITAL_RIESGO_INSUFICIENTE, LOT_SIZE_INCOMPATIBLE,
           MIN_QTY_INALCANZABLE, MIN_NOTIONAL_INALCANZABLE, MAX_QTY_INCOMPATIBLE)

# La ejecucion real cuantiza la cantidad a 6 decimales
# (`real_trading_connector._round_to_step` hace `round(q - q % step, 6)`).
# El gate replica ese truncamiento pero SIEMPRE a la baja: `round` de Python
# podria subir, y subir significaria superar el importe autorizado.
DECIMALES_EJECUCION = Decimal("0.000001")

CERO = Decimal(0)


def _a_decimal(valor) -> Optional[Decimal]:
    """
    Decimal exacto desde texto. None si el valor no es un numero utilizable.

    Se pasa por `str` a proposito: `Decimal(0.1)` arrastra el error binario,
    `Decimal("0.1")` no.
    """
    if valor is None or isinstance(valor, bool):
        return None
    try:
        if isinstance(valor, float) and not math.isfinite(valor):
            return None
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def _piso_a_paso(cantidad: Decimal, paso: Decimal) -> Decimal:
    """Mayor multiplo de `paso` que no supera `cantidad`."""
    if paso <= CERO:
        return cantidad
    return (cantidad / paso).to_integral_value(rounding=ROUND_FLOOR) * paso


def _techo_a_paso(cantidad: Decimal, paso: Decimal) -> Decimal:
    """Menor multiplo de `paso` que alcanza `cantidad`."""
    if paso <= CERO:
        return cantidad
    return (cantidad / paso).to_integral_value(rounding=ROUND_CEILING) * paso


def _como_ejecutaria(cantidad: Decimal, paso: Decimal) -> Decimal:
    """
    Cantidad tal y como la dejaria la ejecucion: piso al paso y truncada a los
    6 decimales que aplica el conector. Nunca hacia arriba.
    """
    return _piso_a_paso(cantidad, paso).quantize(DECIMALES_EJECUCION,
                                                 rounding=ROUND_FLOOR)


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS DEL EXCHANGE
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FiltrosSimbolo:
    """LOT_SIZE + NOTIONAL de un simbolo, ya en Decimal."""
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal
    min_notional: Decimal


def leer_filtros(symbol_info) -> Optional[FiltrosSimbolo]:
    """
    Extrae LOT_SIZE y NOTIONAL de una entrada de `exchange_info["symbols"]`.

    Devuelve None si falta alguno o si algun valor no es legible. Esa ausencia
    NO se rellena con valores por defecto: para una compra nueva, no saber cual
    es el minimo del exchange significa no poder demostrar que la orden seria
    valida, y entonces no se envia el activo al LLM (fail-closed).
    """
    if not isinstance(symbol_info, dict):
        return None
    filtros = symbol_info.get("filters")
    if not isinstance(filtros, (list, tuple)):
        return None

    lote = notional = None
    for f in filtros:
        if not isinstance(f, dict):
            continue
        tipo = f.get("filterType")
        if tipo == "LOT_SIZE":
            lote = f
        elif tipo in ("NOTIONAL", "MIN_NOTIONAL"):
            # Binance migro MIN_NOTIONAL a NOTIONAL; se aceptan ambos, igual
            # que hace `get_min_notional` en el bucle.
            if notional is None:
                notional = f

    if lote is None or notional is None:
        return None

    min_qty = _a_decimal(lote.get("minQty"))
    max_qty = _a_decimal(lote.get("maxQty"))
    step = _a_decimal(lote.get("stepSize"))
    min_notional = _a_decimal(notional.get("minNotional"))

    if None in (min_qty, max_qty, step, min_notional):
        return None
    if min_qty < CERO or max_qty <= CERO or step <= CERO or min_notional < CERO:
        return None
    if max_qty < min_qty:
        return None
    return FiltrosSimbolo(min_qty=min_qty, max_qty=max_qty, step_size=step,
                          min_notional=min_notional)


# ─────────────────────────────────────────────────────────────────────────────
# VEREDICTO
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Veredicto:
    """
    Por que un activo entra o no en el universo de compra.

    Los campos numericos quedan a None cuando no se llegaron a calcular: no se
    rellenan con ceros, que serian una respuesta inventada.
    """
    symbol: str
    elegible: bool
    motivo: str
    max_notional_autorizado: Optional[float] = None
    min_notional: Optional[float] = None
    cantidad_minima_valida: Optional[float] = None
    notional_minimo_valido: Optional[float] = None

    def __str__(self) -> str:
        if self.elegible:
            return (f"ELEGIBLE {self.symbol}: qty_min={self.cantidad_minima_valida} "
                    f"notional_min={self.notional_minimo_valido} "
                    f"autorizado={self.max_notional_autorizado}")
        return f"INELEGIBLE {self.symbol}: {self.motivo}"


def evaluar_compra(symbol, *, symbol_info, precio,
                   max_notional_autorizado) -> Veredicto:
    """
    ¿Existe alguna cantidad ejecutable para COMPRAR `symbol` ahora mismo?

    Elegible si y solo si existe `q > 0` tal que, con las reglas de redondeo de
    la ejecucion:

        q es multiplo de stepSize
        q >= minQty
        q <= maxQty
        q * precio >= minNotional
        q * precio <= max_notional_autorizado

    Se busca la cantidad valida MAS PEQUENA que alcanza `minNotional` y se
    comprueba que su importe cabe en lo autorizado. Nunca se eleva el tamano
    para llegar al minimo del exchange: eso violaria nuestros propios limites,
    que es exactamente lo que el MotorRiesgo se niega a hacer.
    """
    # 1. Estado del simbolo en el exchange.
    info = symbol_info if isinstance(symbol_info, dict) else {}
    if info.get("status") != "TRADING":
        return Veredicto(symbol, False, NO_TRADING)
    if not info.get("isSpotTradingAllowed"):
        return Veredicto(symbol, False, NO_SPOT)

    # 2. Precio utilizable. Ausente no es cero (invariante del proyecto).
    p = _a_decimal(precio)
    if p is None or p <= CERO:
        return Veredicto(symbol, False, SIN_PRECIO)

    # 3. Filtros. Sin ellos no se puede demostrar nada: fail-closed.
    filtros = leer_filtros(info)
    if filtros is None:
        return Veredicto(symbol, False, FILTROS_INVALIDOS)

    # 4. Importe autorizado por el RIESGO. No se recalcula aqui.
    autorizado = _a_decimal(max_notional_autorizado)
    if autorizado is None or autorizado <= CERO:
        return Veredicto(symbol, False, CAPITAL_RIESGO_INSUFICIENTE,
                         min_notional=float(filtros.min_notional))

    campos = dict(max_notional_autorizado=float(autorizado),
                  min_notional=float(filtros.min_notional))

    # 5. Cantidad valida MAS PEQUENA: la que alcanza minNotional y minQty.
    #    Se calcula SIEMPRE, incluso cuando ya se sabe que no cabra: es el dato
    #    que explica cuanto haria falta, y dejarlo a None pierde el diagnostico.
    q_min_notional = _techo_a_paso(filtros.min_notional / p, filtros.step_size)
    q_min_lote = _techo_a_paso(filtros.min_qty, filtros.step_size)
    q_min = max(q_min_notional, q_min_lote, filtros.step_size)
    campos["cantidad_minima_valida"] = float(q_min)
    campos["notional_minimo_valido"] = float(q_min * p)

    # 6. Techos por lote y por riesgo, cuantizados como lo haria la ejecucion.
    q_max_lote = _piso_a_paso(filtros.max_qty, filtros.step_size)
    if q_min > q_max_lote:
        return Veredicto(symbol, False, MAX_QTY_INCOMPATIBLE, **campos)

    q_max = min(_como_ejecutaria(autorizado / p, filtros.step_size), q_max_lote)

    if q_min > q_max:
        # ── PRECEDENCIA POR CAUSA PRIMARIA ──────────────────────────────────
        # El orden importa: un simbolo puede incumplir varias cosas a la vez y
        # el motivo debe nombrar la que realmente manda.
        #
        # Auditado contra los filtros reales de Binance: con 0,40 USDT
        # autorizados los 484 pares fallan porque el minimo del exchange (1 o
        # 5 USDT) no cabe en el riesgo. Una version anterior devolvia
        # LOT_SIZE_INCOMPATIBLE para 40 de ellos -los de precio mas alto-
        # porque comprobaba el techo del lote antes que el minimo del exchange.
        # La elegibilidad era la misma; el diagnostico, enganoso.
        if filtros.min_notional > autorizado:
            # 1. El minimo del exchange no cabe en lo autorizado. Ninguna
            #    granularidad puede arreglar eso.
            motivo = MIN_NOTIONAL_INALCANZABLE
        elif q_min_lote * p > autorizado:
            # 2. minQty por si sola ya se pasa del riesgo.
            motivo = MIN_QTY_INALCANZABLE
        else:
            # 3. Ambos minimos cabrian por separado, pero ningun multiplo de
            #    stepSize satisface los dos sin superar lo autorizado.
            motivo = LOT_SIZE_INCOMPATIBLE
        return Veredicto(symbol, False, motivo, **campos)

    return Veredicto(symbol, True, ELEGIBLE, **campos)


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN POR CICLO
#
# Telemetria MINIMA y deliberadamente sin persistencia: contadores en memoria y
# una linea legible por ciclo. No hace falta migracion (ver informe de 03A).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResumenElegibilidad:
    """
    Contadores del gate en un ciclo. No influye en ninguna decision.

    `universo` lo fija el llamador; el resto se acumula. Ningun metodo lanza:
    contar no puede alterar el trading.
    """
    universo: int = 0
    elegibles_compra: int = 0
    preservados_venta: int = 0
    descartados: int = 0
    por_motivo: Dict[str, int] = field(default_factory=dict)

    def anotar(self, veredicto: Veredicto) -> None:
        try:
            motivo = getattr(veredicto, "motivo", None) or "DESCONOCIDO"
            self.por_motivo[motivo] = self.por_motivo.get(motivo, 0) + 1
            if getattr(veredicto, "elegible", False):
                self.elegibles_compra += 1
            else:
                self.descartados += 1
        except Exception:
            pass

    def preservar(self, symbol=None) -> None:
        """Una posicion abierta entra SIEMPRE, para poder analizar su salida."""
        try:
            self.preservados_venta += 1
            self.por_motivo["POSICION_ABIERTA"] = \
                self.por_motivo.get("POSICION_ABIERTA", 0) + 1
        except Exception:
            pass

    @property
    def enviados(self) -> int:
        return self.elegibles_compra + self.preservados_venta

    def linea(self, duracion_ms=None) -> str:
        """Resumen de una linea, con el desglose por motivo ordenado."""
        try:
            desglose = " ".join(
                f"{m}={n}" for m, n in sorted(self.por_motivo.items(),
                                              key=lambda kv: (-kv[1], kv[0])))
            tiempo = f" | {duracion_ms} ms" if duracion_ms is not None else ""
            return (f"[GATE] universo={self.universo} "
                    f"elegibles_compra={self.elegibles_compra} "
                    f"preservados_venta={self.preservados_venta} "
                    f"descartados={self.descartados} "
                    f"-> a_GPT={self.enviados}"
                    f"{' | ' + desglose if desglose else ''}{tiempo}")
        except Exception:
            return "[GATE] resumen no disponible"
