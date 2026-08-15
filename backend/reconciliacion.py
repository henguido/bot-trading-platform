"""
Reconciliador conservador de ordenes  (P0-14 + P0-17).

REGLA CENTRAL: la ausencia de evidencia NO es evidencia de no ejecucion.

Antes, un unico `get_order` que respondia "no encontrada" bastaba para marcar la
orden como NO_EJECUTADA. En una operacion asincrona esa respuesta puede
significar simplemente que el broker todavia no ha propagado la orden. Marcarla
como inexistente y seguir operando podria duplicar una posicion real.

Ahora:
    timeout POST            -> ESTADO_DESCONOCIDO
    consulta negativa       -> SIGUE ESTADO_DESCONOCIDO (se cuenta el intento)
    intentos agotados       -> RECONCILIACION_MANUAL_REQUERIDA (no terminal)
    evidencia explicita     -> estado terminal

Nunca se reenvia el POST. La recuperacion es siempre por client_order_id.

Los estados no terminales bloquean nueva exposicion en el MotorRiesgo. Las
ventas siguen permitidas: reducir riesgo bajo incertidumbre es exactamente lo
que hay que poder hacer.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Sequence

from backend.app.database import SessionLocal
from backend.app.services import ordenes_repo
from backend.app.services.ordenes import (
    ESTADO_BROKER_A_ORDEN,
    EstadoOrden,
    extraer_fills,
)


# ─────────────────────────────────────────────────────────────────────────────
# Politica de backoff
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PoliticaBackoff:
    """
    Reintentos acotados, sin polling agresivo.

    `dormir` se inyecta para poder probar sin esperar de verdad.
    """
    intentos_maximos: int = 5
    espera_inicial_s: float = 2.0
    factor: float = 2.0
    espera_maxima_s: float = 60.0

    def espera_para(self, intento: int) -> float:
        """Intento 1 -> espera_inicial; luego crece por `factor`, con techo."""
        if intento <= 1:
            return 0.0
        bruta = self.espera_inicial_s * (self.factor ** (intento - 2))
        return min(bruta, self.espera_maxima_s)


# ─────────────────────────────────────────────────────────────────────────────
# Fuentes de evidencia
#
# El reconciliador NO asume que get_order sera para siempre la unica fuente.
# Cada fuente responde: "que sabes de ESTA orden?" y devuelve None si no sabe
# nada. Se consultan en orden y la primera con evidencia gana.
#
# Fuentes previstas para fases siguientes (punto de integracion ya definido):
#   - FuenteUserDataStream: eventos executionReport del User Data Stream, que
#     llegan aunque se pierda la respuesta REST.
#   - FuenteMisTrades: get_my_trades por rango temporal, util cuando el
#     broker_order_id no se llego a conocer.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Evidencia:
    """Lo que una fuente pudo averiguar sobre una orden."""
    origen: str
    estado_broker: str
    ejecutado_base: float = 0.0
    ejecutado_quote: float = 0.0
    broker_order_id: Optional[str] = None
    fills: tuple = ()


class FuenteGetOrder:
    """Consulta REST por NUESTRO client_order_id."""

    nombre = "get_order"

    def __init__(self, broker):
        self._broker = broker

    def consultar(self, orden) -> Optional[Evidencia]:
        respuesta = self._broker.consultar_orden(orden.symbol, orden.client_order_id)
        if respuesta is None:
            return None                     # el broker no sabe nada TODAVIA
        try:
            base = float(respuesta.get("executedQty", 0) or 0)
            quote = float(respuesta.get("cummulativeQuoteQty", 0) or 0)
        except (TypeError, ValueError):
            return None                     # respuesta ilegible: no es evidencia
        oid = respuesta.get("orderId")
        fills = list(extraer_fills(respuesta))
        if not fills and base > 0 and oid is not None:
            try:
                fills = _fills_desde_trades(
                    self._broker.consultar_fills(orden.symbol, str(oid)))
            except Exception:
                fills = []
        return Evidencia(
            origen=self.nombre,
            estado_broker=str(respuesta.get("status", "")).upper(),
            ejecutado_base=base, ejecutado_quote=quote,
            broker_order_id=str(oid) if oid is not None else None,
            fills=tuple(fills),
        )


def _fills_desde_trades(trades):
    salida = []
    for t in trades or []:
        try:
            salida.append({
                "trade_id": str(t.get("id")) if t.get("id") is not None else None,
                "price": float(t.get("price", 0) or 0),
                "qty": float(t.get("qty", 0) or 0),
                "commission": float(t.get("commission", 0) or 0),
                "commission_asset": t.get("commissionAsset"),
            })
        except (TypeError, ValueError):
            continue
    return salida


def fuentes_por_defecto(broker) -> Sequence:
    """Hoy solo REST. El punto de extension queda abierto a proposito."""
    return (FuenteGetOrder(broker),)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResumenReconciliacion:
    revisadas: int = 0
    resueltas: int = 0
    sin_resolver: int = 0
    manuales: int = 0
    fills_nuevos: int = 0
    consultas: int = 0

    @property
    def hay_incertidumbre(self) -> bool:
        return self.sin_resolver > 0 or self.manuales > 0


def _aplicar_evidencia(db, orden, ev: Evidencia) -> bool:
    """Traduce evidencia en estado. Devuelve True si quedo terminal."""
    if ev.broker_order_id:
        orden.broker_order_id = ev.broker_order_id
    orden.executed_base_quantity = ev.ejecutado_base
    orden.executed_quote_amount = ev.ejecutado_quote

    nuevos = ordenes_repo.procesar_fills(db, orden, ev.fills)

    if ev.ejecutado_base > 0:
        # PARCIAL no es terminal: aun puede llenarse mas.
        orden.estado = (EstadoOrden.PARCIAL.value
                        if ev.estado_broker in ("NEW", "PARTIALLY_FILLED")
                        else EstadoOrden.EJECUTADA.value)
    elif ev.estado_broker in ESTADO_BROKER_A_ORDEN:
        # Rechazo, cancelacion o expiracion EXPLICITOS del broker.
        orden.estado = ESTADO_BROKER_A_ORDEN[ev.estado_broker].value
    elif ev.estado_broker in ("FILLED", "NEW", "PARTIALLY_FILLED", ""):
        # El broker la conoce pero no da un desenlace cerrado con 0 ejecutado.
        orden.estado = EstadoOrden.ESTADO_DESCONOCIDO.value
    else:
        # Estado cerrado declarado por el broker con executedQty == 0. Esta es
        # la UNICA via por la que se alcanza NO_EJECUTADA.
        orden.estado = EstadoOrden.NO_EJECUTADA.value

    orden.error = None if orden.estado == EstadoOrden.EJECUTADA.value else orden.error
    orden.actualizada_en = datetime.utcnow()
    db.commit()
    print(f"[RECONCILIACION] {orden.client_order_id}: evidencia de {ev.origen} "
          f"({ev.estado_broker or 'sin status'}) -> {orden.estado} "
          f"({nuevos} fills nuevos)")
    return orden.estado not in [e.value for e in ESTADOS_ABIERTOS]


ESTADOS_ABIERTOS = (EstadoOrden.PARCIAL, EstadoOrden.ESTADO_DESCONOCIDO,
                    EstadoOrden.CREADA, EstadoOrden.ENVIANDO,
                    EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA)


def _marcar_manual(db, orden) -> bool:
    """Agotados los intentos automaticos. NO es NO_EJECUTADA."""
    orden.estado = EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA.value
    orden.error = (f"reconciliacion automatica agotada tras "
                   f"{orden.intentos_reconciliacion} intentos sin evidencia. "
                   f"Requiere revision manual en el broker. NO se asume que la "
                   f"orden no exista.")
    orden.actualizada_en = datetime.utcnow()
    db.commit()
    print(f"[RECONCILIACION] {orden.client_order_id}: "
          f"RECONCILIACION_MANUAL_REQUERIDA. Nueva exposicion sigue bloqueada.")
    return False


def reconciliar_orden(db, orden, broker, *, politica: PoliticaBackoff = None,
                      fuentes=None, ahora: Callable[[], datetime] = None,
                      resumen: ResumenReconciliacion = None) -> bool:
    """
    Realiza COMO MUCHO UNA consulta por llamada.

    El backoff no se implementa durmiendo dentro de la funcion -eso seria el
    polling agresivo que queremos evitar-, sino decidiendo si ha pasado
    suficiente tiempo desde `ultimo_intento_en`. Asi el reconciliador se puede
    invocar tan a menudo como se quiera sin machacar al broker, y la espera
    sobrevive a un reinicio del proceso.

    Devuelve True solo si la orden quedo en estado terminal. Una consulta
    negativa NUNCA produce NO_EJECUTADA.
    """
    politica = politica or PoliticaBackoff()
    fuentes = fuentes if fuentes is not None else fuentes_por_defecto(broker)
    momento = (ahora or datetime.utcnow)()
    intentos = orden.intentos_reconciliacion or 0

    if intentos >= politica.intentos_maximos:
        if orden.estado != EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA.value:
            return _marcar_manual(db, orden)
        return False

    # ¿Toca ya reintentar, o seguimos dentro de la ventana de espera?
    if orden.ultimo_intento_en is not None:
        espera = politica.espera_para(intentos + 1)
        transcurrido = (momento - orden.ultimo_intento_en).total_seconds()
        if transcurrido < espera:
            print(f"[RECONCILIACION] {orden.client_order_id}: en backoff "
                  f"({transcurrido:.1f}s de {espera:.1f}s). Sin consultar.")
            return False

    orden.intentos_reconciliacion = intentos + 1
    orden.ultimo_intento_en = momento
    if resumen is not None:
        resumen.consultas += 1

    evidencia = None
    for fuente in fuentes:
        try:
            evidencia = fuente.consultar(orden)
        except Exception as e:
            print(f"[RECONCILIACION] {orden.client_order_id}: fuente "
                  f"{fuente.nombre} no disponible ({type(e).__name__})")
            evidencia = None
        if evidencia is not None:
            break

    if evidencia is not None:
        return _aplicar_evidencia(db, orden, evidencia)

    # Sin evidencia: la orden SIGUE siendo desconocida. No se concluye nada.
    orden.estado = EstadoOrden.ESTADO_DESCONOCIDO.value
    db.commit()
    print(f"[RECONCILIACION] {orden.client_order_id}: sin evidencia "
          f"(intento {orden.intentos_reconciliacion}/{politica.intentos_maximos}). "
          f"Sigue ESTADO_DESCONOCIDO.")

    if orden.intentos_reconciliacion >= politica.intentos_maximos:
        return _marcar_manual(db, orden)
    return False


def reconciliar_pendientes(broker, *, usuario_id=None, session_factory=SessionLocal,
                           politica: PoliticaBackoff = None, fuentes=None,
                           ahora: Callable[[], datetime] = None
                           ) -> ResumenReconciliacion:
    """
    Recorre las ordenes no terminales y trata de resolverlas.

    Idempotente: los fills se guardan por (broker, symbol, trade_id) UNIQUE, asi
    que ejecutarla cien veces produce el mismo ledger que ejecutarla una.
    """
    resumen = ResumenReconciliacion()
    with session_factory() as db:
        pendientes = ordenes_repo.ordenes_no_terminales(db, usuario_id)
        resumen.revisadas = len(pendientes)
        for orden in pendientes:
            antes = len(orden.fills or [])
            terminal = reconciliar_orden(db, orden, broker, politica=politica,
                                         fuentes=fuentes, ahora=ahora,
                                         resumen=resumen)
            if terminal:
                resumen.resueltas += 1
            elif orden.estado == EstadoOrden.RECONCILIACION_MANUAL_REQUERIDA.value:
                resumen.manuales += 1
            else:
                resumen.sin_resolver += 1
            db.refresh(orden)
            resumen.fills_nuevos += max(0, len(orden.fills or []) - antes)

    if resumen.revisadas:
        print(f"[RECONCILIACION] revisadas={resumen.revisadas} "
              f"resueltas={resumen.resueltas} sin_resolver={resumen.sin_resolver} "
              f"manuales={resumen.manuales}")
    return resumen
