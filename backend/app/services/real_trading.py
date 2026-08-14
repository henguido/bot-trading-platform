from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, NamedTuple, Optional
from backend.app import models
from backend.app.database import SessionLocal
from backend.app.services import ordenes_repo
from backend.app.services.ordenes import nuevo_client_order_id
from sqlalchemy import func
import json


class ContextoUsuario(NamedTuple):
    """
    Estado financiero persistente del usuario activo, leido de la BASE DE DATOS.

    La base de datos es la UNICA fuente de verdad del estado persistente. El
    Simulator es un libro en memoria para modo PAPER y no debe usarse para
    reconstruir el coste base: existen varias instancias de Simulator en el
    proyecto y ninguna esta sincronizada con las demas.

    `usuario_id is None` representa el estado NORMAL de "todavia no hay
    usuarios registrados". No es una condicion de error.
    """
    usuario_id: Optional[int]
    estado: Dict[str, Dict[str, float]]
    ultimos_movimientos: Dict[str, str]
    ultimos_precios_venta: Dict[str, float]


def cargar_contexto_usuario(session_factory=SessionLocal) -> ContextoUsuario:
    """
    Devuelve el contexto financiero fresco del usuario activo.

    Usa una sesion CORTA: se abre aqui, se lee todo y se cierra al salir del
    with. No se mantiene ninguna sesion viva entre iteraciones del bot.

    `session_factory` se inyecta para poder probar contra SQLite en memoria.
    """
    with session_factory() as db:
        usuario = (
            db.query(models.User)
            .order_by(models.User.id.asc())
            .first()
        )
        if usuario is None:
            # Estado normal, no excepcional: aun no hay nadie registrado.
            return ContextoUsuario(
                usuario_id=None,
                estado={},
                ultimos_movimientos={},
                ultimos_precios_venta={},
            )

        return ContextoUsuario(
            usuario_id=usuario.id,
            estado=cargar_estado_portafolio(db, usuario.id),
            ultimos_movimientos=obtener_ultimo_movimiento(db, usuario.id),
            ultimos_precios_venta=obtener_ultimo_precio_venta(db, usuario.id),
        )

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

def ejecutar_y_registrar_compra(*, trader, usuario_id, symbol, quote_amount,
                                precio_referencia=None, session_factory=SessionLocal,
                                decision_audit_id=None):
    """
    COMPRA en LIVE. Persiste UNICAMENTE si el broker confirma la ejecucion.

        senal -> intento de orden -> respuesta -> validacion del fill
              -> persistencia

    `quote_amount` es el importe del activo COTIZADO (USDT en BTCUSDT).
    Devuelve el ResultadoOrden del conector, tanto si se persistio como si no.
    """
    return _ejecutar_con_identidad(
        trader=trader, usuario_id=usuario_id, symbol=symbol, side="BUY",
        session_factory=session_factory, quote_amount=quote_amount,
        decision_audit_id=decision_audit_id,
        enviar=lambda cid: trader.comprar(symbol, quote_amount=quote_amount,
                                          client_order_id=cid),
    )


def ejecutar_y_registrar_venta(*, trader, usuario_id, symbol, base_quantity,
                               precio_referencia=None, session_factory=SessionLocal,
                               decision_audit_id=None):
    """
    VENTA en LIVE. Persiste UNICAMENTE si el broker confirma la ejecucion.

    `base_quantity` es cantidad del activo BASE (BTC en BTCUSDT). Nunca se le
    pasa precio * cantidad: eso seria un importe en USDT (bug P0-1).
    """
    return _ejecutar_con_identidad(
        trader=trader, usuario_id=usuario_id, symbol=symbol, side="SELL",
        session_factory=session_factory, base_quantity=base_quantity,
        decision_audit_id=decision_audit_id,
        enviar=lambda cid: trader.vender(symbol, base_quantity=base_quantity,
                                         client_order_id=cid),
    )


def _ejecutar_con_identidad(*, trader, usuario_id, symbol, side, session_factory,
                            enviar, base_quantity=None, quote_amount=None,
                            decision_audit_id=None):
    """
    Ciclo de vida completo de una orden con identidad (P0-10 / P0-11).

        client_order_id -> intencion persistida -> ENVIANDO -> POST
        -> resultado -> fills idempotentes -> transaccion

    La intencion se guarda ANTES del envio: si perdemos la respuesta, la orden
    queda registrada como ESTADO_DESCONOCIDO y el reconciliador puede
    preguntarle al broker por ese client_order_id. Sin ese registro previo, una
    orden ejecutada cuya respuesta se pierde seria invisible para siempre.
    """
    cid = nuevo_client_order_id()

    with session_factory() as db:
        orden = ordenes_repo.crear_intencion(
            db, client_order_id=cid, usuario_id=usuario_id, symbol=symbol, side=side,
            requested_base_quantity=base_quantity, requested_quote_amount=quote_amount,
            decision_audit_id=decision_audit_id)
        ordenes_repo.marcar_enviando(db, orden)

    ejecucion = enviar(cid)

    with session_factory() as db:
        orden = db.query(models.Orden).filter_by(client_order_id=cid).first()
        if orden is not None:
            ordenes_repo.aplicar_resultado(db, orden, ejecucion)
            # Los fills se procesan siempre que existan, incluso en ejecuciones
            # parciales. Son idempotentes por restriccion de BD.
            if ejecucion.fills:
                ordenes_repo.procesar_fills(db, orden, ejecucion.fills)
            elif ejecucion.success:
                # El broker confirmo cantidad pero no detallo fills: se registra
                # un fill sintetico identificado por el propio order_id, para no
                # perder el apunte contable ni romper la idempotencia.
                ordenes_repo.procesar_fills(db, orden, [{
                    "trade_id": f"orden:{ejecucion.order_id or cid}",
                    "price": ejecucion.average_fill_price or 0.0,
                    "qty": ejecucion.executed_base_quantity,
                    "commission": None, "commission_asset": None,
                }])
    return ejecucion


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
