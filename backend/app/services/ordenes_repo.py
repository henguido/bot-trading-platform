"""
Persistencia idempotente del ciclo de vida de una orden (P0-11).

La idempotencia se apoya en RESTRICCIONES DE BASE DE DATOS, no en comprobaciones
Python que dos procesos podrian atravesar a la vez:

    ordenes.client_order_id            UNIQUE
    fills(broker, symbol, trade_id)    UNIQUE
    transacciones.fill_id              UNIQUE (NULL en las legacy)

Procesar el mismo fill cien veces deja exactamente una fila y un apunte.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.app.services.ordenes import ESTADOS_NO_TERMINALES, EstadoOrden


def crear_intencion(db, *, client_order_id, usuario_id, symbol, side,
                    requested_base_quantity=None, requested_quote_amount=None,
                    decision_audit_id=None, broker="binance"):
    """
    Registra la INTENCION de operar antes de cualquier POST.

    Si el client_order_id ya existe, no crea una segunda: devuelve la existente.
    Esa es la barrera contra duplicar una orden economica por reintentar.
    """
    existente = (db.query(models.Orden)
                 .filter_by(client_order_id=client_order_id).first())
    if existente is not None:
        return existente

    orden = models.Orden(
        client_order_id=client_order_id, broker=broker, usuario_id=usuario_id,
        symbol=symbol, side=side,
        requested_base_quantity=requested_base_quantity,
        requested_quote_amount=requested_quote_amount,
        decision_audit_id=decision_audit_id,
        estado=EstadoOrden.CREADA.value,
    )
    db.add(orden)
    try:
        db.commit()
    except IntegrityError:
        # Otro proceso la creo entre el SELECT y el INSERT. La UNIQUE de la BD
        # es la que garantiza que solo exista una.
        db.rollback()
        return (db.query(models.Orden)
                .filter_by(client_order_id=client_order_id).first())
    db.refresh(orden)
    return orden


def marcar_enviando(db, orden):
    orden.estado = EstadoOrden.ENVIANDO.value
    orden.actualizada_en = datetime.utcnow()
    db.commit()
    return orden


def aplicar_resultado(db, orden, resultado):
    """Vuelca un ResultadoOrden sobre la fila de la orden."""
    orden.estado = EstadoOrden(resultado.estado).value
    orden.broker_order_id = resultado.order_id or orden.broker_order_id
    orden.executed_base_quantity = resultado.executed_base_quantity or 0.0
    orden.executed_quote_amount = resultado.executed_quote_amount or 0.0
    orden.error = resultado.error
    orden.actualizada_en = datetime.utcnow()
    db.commit()
    return orden


def registrar_fill(db, orden, fill):
    """
    Guarda un fill si no existia. Devuelve (Fill, creado: bool).

    La unicidad la impone la BD: dos procesos concurrentes no pueden insertar
    el mismo (broker, symbol, trade_id).
    """
    trade_id = fill.get("trade_id")
    if trade_id is None:
        return None, False

    existente = (db.query(models.Fill)
                 .filter_by(broker=orden.broker, symbol=orden.symbol,
                            trade_id=str(trade_id)).first())
    if existente is not None:
        return existente, False

    nuevo = models.Fill(
        orden_id=orden.id, broker=orden.broker, symbol=orden.symbol,
        trade_id=str(trade_id),
        price=float(fill.get("price") or 0.0),
        qty=float(fill.get("qty") or 0.0),
        commission=fill.get("commission"),
        commission_asset=fill.get("commission_asset"),
    )
    db.add(nuevo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (db.query(models.Fill)
                .filter_by(broker=orden.broker, symbol=orden.symbol,
                           trade_id=str(trade_id)).first()), False
    db.refresh(nuevo)
    return nuevo, True


def registrar_transaccion_de_fill(db, orden, fill_row):
    """
    Crea el apunte contable de un fill, una sola vez.

    transacciones.fill_id es UNIQUE: aunque se llame cien veces, solo hay un
    apunte por fill.
    """
    ya = db.query(models.Transaction).filter_by(fill_id=fill_row.id).first()
    if ya is not None:
        return ya, False

    activo = db.query(models.Asset).filter_by(simbolo=orden.symbol).first()
    if activo is None:
        activo = models.Asset(simbolo=orden.symbol, nombre=orden.symbol, tipo="crypto")
        db.add(activo); db.commit(); db.refresh(activo)

    portafolio = (db.query(models.Portfolio)
                  .filter_by(usuario_id=orden.usuario_id, tipo_activo="crypto").first())
    if portafolio is None:
        portafolio = models.Portfolio(usuario_id=orden.usuario_id,
                                      nombre="Portafolio Cripto",
                                      tipo_activo="crypto", balance_inicial=0.0)
        db.add(portafolio); db.commit(); db.refresh(portafolio)

    tx = models.Transaction(
        portafolio_id=portafolio.id, activo_id=activo.id,
        tipo_operacion="Compra" if orden.side == "BUY" else "Venta",
        cantidad=fill_row.qty, precio=fill_row.price,
        fecha_operacion=datetime.utcnow(), fill_id=fill_row.id,
    )
    db.add(tx)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(models.Transaction).filter_by(fill_id=fill_row.id).first(), False
    db.refresh(tx)
    return tx, True


def procesar_fills(db, orden, fills) -> int:
    """Guarda fills y sus apuntes. Idempotente. Devuelve cuantos son nuevos."""
    nuevos = 0
    for fill in fills or ():
        fila, creado = registrar_fill(db, orden, fill)
        if fila is None:
            continue
        if creado:
            nuevos += 1
        registrar_transaccion_de_fill(db, orden, fila)
    return nuevos


def ordenes_no_terminales(db, usuario_id=None):
    """Ordenes cuya situacion todavia no conocemos con certeza."""
    q = db.query(models.Orden).filter(
        models.Orden.estado.in_([e.value for e in ESTADOS_NO_TERMINALES]))
    if usuario_id is not None:
        q = q.filter(models.Orden.usuario_id == usuario_id)
    return q.order_by(models.Orden.id.asc()).all()


def hay_incertidumbre(db, usuario_id=None) -> bool:
    return bool(ordenes_no_terminales(db, usuario_id))
