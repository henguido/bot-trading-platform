from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict
from backend.app import models
from sqlalchemy import func
import json

def guardar_transaccion_real(db: Session, usuario_id: int, symbol: str, action: str, price: float, quantity: float):
    # 1. Buscar o crear activo
    activo = db.query(models.Asset).filter_by(simbolo=symbol).first()
    if not activo:
        activo = models.Asset(simbolo=symbol, nombre=symbol, tipo="crypto")
        db.add(activo)
        db.commit()
        db.refresh(activo)

    # 2. Buscar o crear portafolio del usuario para cripto
    portafolio = (
        db.query(models.Portfolio)
        .filter_by(usuario_id=usuario_id, tipo_activo="crypto")
        .first()
    )
    if not portafolio:
        portafolio = models.Portfolio(
            usuario_id=usuario_id,
            nombre="Portafolio Cripto",
            tipo_activo="crypto",
            balance_inicial=0.0
        )
        db.add(portafolio)
        db.commit()
        db.refresh(portafolio)

    # 3. Guardar transacción
    transaccion = models.Transaction(
        portafolio_id=portafolio.id,
        activo_id=activo.id,
        tipo_operacion="Compra" if action == "COMPRAR" else "Venta",
        cantidad=quantity,
        precio=price,
        fecha_operacion=datetime.utcnow()
    )
    db.add(transaccion)
    db.commit()
    db.refresh(transaccion)
    return transaccion

def cargar_estado_portafolio(db: Session, usuario_id: int) -> Dict[str, Dict[str, float]]:
    posiciones = {}

    portafolio = (
        db.query(models.Portfolio)
        .filter_by(usuario_id=usuario_id, tipo_activo="crypto")
        .first()
    )
    if not portafolio:
        return posiciones

    transacciones = (
        db.query(models.Transaction)
        .filter_by(portafolio_id=portafolio.id)
        .order_by(models.Transaction.fecha_operacion.asc())
        .all()
    )

    for tx in transacciones:
        symbol = db.query(models.Asset).get(tx.activo_id).simbolo
        if symbol not in posiciones:
            posiciones[symbol] = {"cantidad": 0.0, "precio_promedio": 0.0}

        pos = posiciones[symbol]

        if tx.tipo_operacion == "Compra":
            total_valor = pos["cantidad"] * pos["precio_promedio"]
            total_valor += tx.cantidad * tx.precio
            pos["cantidad"] += tx.cantidad
            pos["precio_promedio"] = total_valor / pos["cantidad"] if pos["cantidad"] else 0.0

        elif tx.tipo_operacion == "Venta":
            pos["cantidad"] -= tx.cantidad
            if pos["cantidad"] <= 0:
                pos["cantidad"] = 0.0
                pos["precio_promedio"] = 0.0

    return posiciones

def guardar_auditoria_decision(
    db: Session,
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    sentimiento: str,
    noticias: str,
    risk_score: float,
    decision_gpt: dict
):
    auditoria = models.DecisionAudit(
        symbol=symbol,
        action=action,
        quantity=quantity,
        price=price,
        sentimiento=sentimiento,
        noticias=noticias,
        risk_score=risk_score,
        decision_gpt=json.dumps(decision_gpt),
        timestamp=datetime.utcnow()
    )
    db.add(auditoria)
    db.commit()

def obtener_ultimo_precio_venta(db: Session, usuario_id: int) -> Dict[str, float]:
    resultado = {}

    portafolio = (
        db.query(models.Portfolio)
        .filter_by(usuario_id=usuario_id, tipo_activo="crypto")
        .first()
    )
    if not portafolio:
        return resultado

    transacciones = (
        db.query(models.Transaction)
        .filter_by(portafolio_id=portafolio.id, tipo_operacion="Venta")
        .order_by(models.Transaction.fecha_operacion.desc())
        .all()
    )

    for tx in transacciones:
        symbol = db.query(models.Asset).get(tx.activo_id).simbolo
        if symbol not in resultado:
            resultado[symbol] = tx.precio

    return resultado

def obtener_ultimo_movimiento(db: Session, usuario_id: int) -> Dict[str, str]:
    resultados = {}

    portafolio = (
        db.query(models.Portfolio)
        .filter_by(usuario_id=usuario_id, tipo_activo="crypto")
        .first()
    )
    if not portafolio:
        return resultados

    subq = (
        db.query(
            models.Transaction.activo_id,
            func.max(models.Transaction.fecha_operacion).label("ultima_fecha")
        )
        .filter(models.Transaction.portafolio_id == portafolio.id)
        .group_by(models.Transaction.activo_id)
        .subquery()
    )

    transacciones = db.query(subq.c.activo_id, subq.c.ultima_fecha).all()

    for activo_id, fecha in transacciones:
        simbolo = db.query(models.Asset).get(activo_id).simbolo
        resultados[simbolo] = fecha.strftime("%Y-%m-%d %H:%M:%S")

    return resultados
