from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app import models
from backend.app.database import get_db
from backend.app.auth import get_current_user

router = APIRouter()


@router.get("/api/transacciones-reales", tags=["Transacciones"])
def obtener_transacciones_reales(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Devuelve solo las transacciones LIVE pertenecientes al usuario autenticado.

    La autenticacion por si sola no es aislamiento: la consulta debe filtrar por
    el propietario del portafolio. Cuando no existen filas devuelve una lista
    vacia, manteniendo un contrato JSON estable para el frontend.
    """
    transacciones = (
        db.query(models.Transaction)
        .join(models.Asset, models.Transaction.activo_id == models.Asset.id)
        .join(models.Portfolio, models.Transaction.portafolio_id == models.Portfolio.id)
        .filter(models.Portfolio.usuario_id == current_user.id)
        .order_by(models.Transaction.fecha_operacion.desc())
        .all()
    )

    resultado = []
    for tx in transacciones:
        resultado.append({
            "id": tx.id,
            "usuario_id": tx.portafolio.usuario_id,
            "activo": tx.activo_id,
            "simbolo": tx.activo.simbolo,
            "tipo_operacion": tx.tipo_operacion,
            "cantidad": tx.cantidad,
            "precio": tx.precio,
            "fecha": tx.fecha_operacion.strftime("%Y-%m-%d %H:%M:%S")
        })
    return resultado
