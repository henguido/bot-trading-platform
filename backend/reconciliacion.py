"""
Reconciliador de ordenes  (P0-14).

Resuelve las ordenes cuya situacion no conocemos preguntando al broker por
NUESTRO client_order_id. Es la unica recuperacion admisible tras un timeout:
reenviar la orden podria duplicar exposicion.

POLITICA ANTE DIVERGENCIA
  - El broker es la autoridad sobre lo que ocurrio.
  - Si el broker NO conoce el client_order_id, la orden nunca llego a crearse
    y pasa a NO_EJECUTADA. Es seguro: preguntamos por una identidad que solo
    nosotros pudimos asignar.
  - Si no podemos determinarlo (error de red al consultar), la orden SIGUE en
    ESTADO_DESCONOCIDO. Nunca se resuelve por omision ni por tiempo.
  - Mientras exista una orden no terminal se BLOQUEA cualquier operacion que
    aumente exposicion. Las ventas siguen permitidas: reducir riesgo bajo
    incertidumbre es exactamente lo que se debe poder hacer.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.database import SessionLocal
from backend.app.services import ordenes_repo
from backend.app.services.ordenes import (
    ESTADO_BROKER_A_ORDEN,
    EstadoOrden,
    extraer_fills,
)


@dataclass
class ResumenReconciliacion:
    revisadas: int = 0
    resueltas: int = 0
    sin_resolver: int = 0
    fills_nuevos: int = 0

    @property
    def hay_incertidumbre(self) -> bool:
        return self.sin_resolver > 0


def _fills_desde_trades(trades):
    """Normaliza get_my_trades al mismo formato que los fills de una orden."""
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


def reconciliar_orden(db, orden, broker) -> bool:
    """
    Resuelve una orden concreta. Devuelve True si quedo en estado terminal.

    Idempotente: los fills se guardan por (broker, symbol, trade_id) UNIQUE, asi
    que ejecutarla cien veces produce el mismo ledger que ejecutarla una.
    """
    try:
        respuesta = broker.consultar_orden(orden.symbol, orden.client_order_id)
    except Exception as e:
        print(f"[RECONCILIACION] {orden.client_order_id}: no se pudo consultar "
              f"({type(e).__name__}: {e}). Sigue en ESTADO_DESCONOCIDO.")
        orden.estado = EstadoOrden.ESTADO_DESCONOCIDO.value
        db.commit()
        return False

    if respuesta is None:
        # El broker no conoce nuestra identidad -> la orden nunca existio.
        orden.estado = EstadoOrden.NO_EJECUTADA.value
        orden.error = "el broker no conoce este client_order_id: la orden nunca se creo"
        db.commit()
        print(f"[RECONCILIACION] {orden.client_order_id}: inexistente en el broker "
              f"-> NO_EJECUTADA")
        return True

    estado_broker = str(respuesta.get("status", "")).upper()
    orden.broker_order_id = (str(respuesta.get("orderId"))
                             if respuesta.get("orderId") is not None
                             else orden.broker_order_id)
    try:
        ejecutado_base = float(respuesta.get("executedQty", 0) or 0)
        ejecutado_quote = float(respuesta.get("cummulativeQuoteQty", 0) or 0)
    except (TypeError, ValueError):
        print(f"[RECONCILIACION] {orden.client_order_id}: respuesta ilegible. "
              f"Sigue en ESTADO_DESCONOCIDO.")
        db.commit()
        return False

    orden.executed_base_quantity = ejecutado_base
    orden.executed_quote_amount = ejecutado_quote

    # Fills: primero los que venga en la respuesta, si no se consultan aparte.
    fills = list(extraer_fills(respuesta))
    if not fills and ejecutado_base > 0 and orden.broker_order_id:
        try:
            fills = _fills_desde_trades(
                broker.consultar_fills(orden.symbol, orden.broker_order_id))
        except Exception as e:
            print(f"[RECONCILIACION] {orden.client_order_id}: fills no disponibles "
                  f"({type(e).__name__}). La comision quedara sin registrar.")

    nuevos = ordenes_repo.procesar_fills(db, orden, fills)

    if ejecutado_base <= 0 and estado_broker in ESTADO_BROKER_A_ORDEN:
        orden.estado = ESTADO_BROKER_A_ORDEN[estado_broker].value
    elif ejecutado_base <= 0:
        orden.estado = EstadoOrden.NO_EJECUTADA.value
    elif estado_broker in ("NEW", "PARTIALLY_FILLED"):
        orden.estado = EstadoOrden.PARCIAL.value
    else:
        orden.estado = EstadoOrden.EJECUTADA.value

    db.commit()
    print(f"[RECONCILIACION] {orden.client_order_id}: {estado_broker} -> "
          f"{orden.estado} ({nuevos} fills nuevos)")
    return orden.estado not in [e.value for e in
                                (EstadoOrden.PARCIAL, EstadoOrden.ESTADO_DESCONOCIDO,
                                 EstadoOrden.CREADA, EstadoOrden.ENVIANDO)]


def reconciliar_pendientes(broker, *, usuario_id=None,
                           session_factory=SessionLocal) -> ResumenReconciliacion:
    """
    Recorre todas las ordenes no terminales y trata de resolverlas.

    Se invoca al arrancar y antes de abrir nueva exposicion.
    """
    resumen = ResumenReconciliacion()
    with session_factory() as db:
        pendientes = ordenes_repo.ordenes_no_terminales(db, usuario_id)
        resumen.revisadas = len(pendientes)
        for orden in pendientes:
            antes = len(orden.fills or [])
            if reconciliar_orden(db, orden, broker):
                resumen.resueltas += 1
            else:
                resumen.sin_resolver += 1
            db.refresh(orden)
            resumen.fills_nuevos += max(0, len(orden.fills or []) - antes)
    if resumen.revisadas:
        print(f"[RECONCILIACION] revisadas={resumen.revisadas} "
              f"resueltas={resumen.resueltas} sin_resolver={resumen.sin_resolver}")
    return resumen
