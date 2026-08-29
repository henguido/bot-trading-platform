import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.auth import get_current_user
from backend.app.database import get_db
from backend.observabilidad.ciclos import ultimos_resumenes

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


@router.get("/api/decision-cycles", tags=["Observabilidad"])
def obtener_ciclos_decision(
    limite: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Embudo reciente del usuario: explica ejecuciones y NO TRADE por ciclo."""
    return ultimos_resumenes(db, usuario_id=current_user.id, limite=limite)


def _paper_rows(db: Session, usuario_id: int) -> list[dict]:
    ledger = (
        db.query(models.PaperLedger)
        .filter(models.PaperLedger.usuario_id == usuario_id)
        .one_or_none()
    )
    if ledger is None:
        return []

    operaciones = (
        db.query(models.PaperOperacion)
        .filter(models.PaperOperacion.ledger_id == ledger.id)
        .order_by(models.PaperOperacion.id.asc())
        .all()
    )
    return [
        {
            "id": op.id,
            "created_at": op.creada_en.isoformat() if op.creada_en else None,
            "symbol": op.symbol,
            "side": op.side,
            "reference_price": op.reference_price,
            "fill_price": op.fill_price,
            "base_quantity": op.base_quantity,
            "quote_gross": op.quote_gross,
            "fee_usd": op.fee_usd,
            "quote_net": op.quote_net,
            "slippage_bps": op.slippage_bps,
            "fee_taker_bps": op.fee_taker_bps,
            "strategy": op.strategy,
            "expected_edge_bps": op.expected_edge_bps,
            "expected_cost_bps": op.expected_cost_bps,
            "expected_net_bps": op.expected_net_bps,
        }
        for op in operaciones
    ]


def _csv_seguro(valor):
    """Evita formula injection al abrir texto no confiable en una hoja de calculo."""
    if not isinstance(valor, str):
        return valor
    if valor.startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


@router.get("/api/paper/journal/export", tags=["PAPER"])
def exportar_journal_paper(
    formato: Literal["json", "csv"] = Query("json"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Exporta fills PAPER del usuario autenticado sin consultar broker ni LIVE."""
    rows = _paper_rows(db, current_user.id)

    if formato == "json":
        return {
            "mode": "PAPER",
            "user_id": current_user.id,
            "count": len(rows),
            "operations": rows,
        }

    columnas = [
        "id", "created_at", "symbol", "side", "reference_price", "fill_price",
        "base_quantity", "quote_gross", "fee_usd", "quote_net", "slippage_bps",
        "fee_taker_bps", "strategy", "expected_edge_bps", "expected_cost_bps",
        "expected_net_bps",
    ]
    salida = io.StringIO(newline="")
    writer = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _csv_seguro(row.get(k)) for k in columnas})

    return Response(
        content=salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=paper-journal.csv",
            "X-Paper-Operation-Count": str(len(rows)),
        },
    )
