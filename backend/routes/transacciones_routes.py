from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app import models
from backend.app.database import get_db

router = APIRouter()

@router.get("/api/transacciones-reales", tags=["Transacciones"])
def obtener_transacciones_reales(db: Session = Depends(get_db)):
    transacciones = (
        db.query(models.Transaction)
        .join(models.Asset, models.Transaction.activo_id == models.Asset.id)
        .join(models.Portfolio, models.Transaction.portafolio_id == models.Portfolio.id)
        .order_by(models.Transaction.fecha_operacion.desc())
        .all()
    )

    if not transacciones:
        return {"mensaje": "No hay transacciones disponibles"}

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
