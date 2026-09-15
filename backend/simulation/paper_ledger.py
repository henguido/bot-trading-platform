"""Fuente de verdad persistente para PAPER v1.

El journal de `paper_operaciones` es append-only. Capital, posiciones, coste
medio, fees y P&L realizado se reconstruyen deterministamente desde esas filas.
No comparte tablas con LIVE y no hace ninguna llamada de red.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Dict, Iterable, Optional

from backend.app import models
from backend.economia.ejecucion_paper import FillPaper
from backend.risk import reloj


@dataclass(frozen=True)
class PosicionPaper:
    cantidad: float = 0.0
    coste_medio_neto: float = 0.0

    @property
    def coste_abierto_usd(self) -> float:
        return self.cantidad * self.coste_medio_neto


@dataclass(frozen=True)
class EstadoPaper:
    initial_capital_usd: float
    capital_usd: float
    posiciones: Dict[str, PosicionPaper] = field(default_factory=dict)
    realized_pnl_usd: float = 0.0
    fees_total_usd: float = 0.0
    operaciones: int = 0
    # Solo se calcula cuando `reconstruir_paper(..., dia=...)` recibe un dia de
    # riesgo. Es NETO: incluye la fee de entrada distribuida en el coste medio
    # y la fee de salida ya descontada de quote_net.
    realized_pnl_dia_usd: float = 0.0
    operaciones_dia: int = 0

    @property
    def exposicion_coste_usd(self) -> float:
        return sum(p.coste_abierto_usd for p in self.posiciones.values())


def _float(v, *, nombre: str) -> float:
    if v is None or isinstance(v, bool):
        raise ValueError(f"{nombre} es obligatorio")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not math.isfinite(x):
        raise ValueError(f"{nombre} debe ser finito")
    return x


def _campo(op, nombre, defecto=None):
    if isinstance(op, dict):
        return op.get(nombre, defecto)
    return getattr(op, nombre, defecto)


def _momento_utc_naive(op):
    """Normaliza `creada_en` a datetime UTC naive, como el resto del ledger."""
    momento = _campo(op, "creada_en")
    if momento is None:
        return None
    if isinstance(momento, str):
        try:
            momento = datetime.fromisoformat(momento.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(momento, datetime):
        return None
    if momento.tzinfo is not None:
        momento = momento.astimezone(timezone.utc).replace(tzinfo=None)
    return momento


def reconstruir_paper(initial_capital_usd, operaciones: Iterable, *, dia=None) -> EstadoPaper:
    """Reconstruye el libro completo y falla ante un journal imposible.

    En BUY el coste medio usa `quote_net`, que incluye la fee de entrada.
    En SELL el P&L usa `quote_net`, que ya descuenta la fee de salida. Por eso
    el P&L resultante es neto de las fees registradas en ambos lados.

    Si `dia` se aporta, `realized_pnl_dia_usd` y `operaciones_dia` se calculan
    usando la ventana UTC de `RISK_TIMEZONE`; el coste medio se sigue
    reconstruyendo desde TODO el historial para no perder la base de posiciones
    abiertas antes de ese dia.
    """
    inicial = _float(initial_capital_usd, nombre="initial_capital_usd")
    if inicial <= 0:
        raise ValueError("initial_capital_usd debe ser positivo")

    ventana = reloj.ventana_utc(dia) if dia is not None else None
    capital = inicial
    posiciones: Dict[str, dict] = {}
    pnl = 0.0
    pnl_dia = 0.0
    fees = 0.0
    n = 0
    n_dia = 0

    for op in operaciones or ():
        symbol = str(_campo(op, "symbol") or "").strip().upper()
        side = str(_campo(op, "side") or "").strip().upper()
        qty = _float(_campo(op, "base_quantity"), nombre="base_quantity")
        quote_net = _float(_campo(op, "quote_net"), nombre="quote_net")
        fee = _float(_campo(op, "fee_usd"), nombre="fee_usd")

        if not symbol or side not in ("BUY", "SELL"):
            raise ValueError("operacion PAPER invalida")
        if qty <= 0 or quote_net <= 0 or fee < 0:
            raise ValueError("magnitudes PAPER invalidas")

        momento = _momento_utc_naive(op)
        en_dia = False
        if ventana is not None and momento is not None:
            inicio, fin = ventana
            en_dia = inicio <= momento < fin

        pos = posiciones.setdefault(symbol, {"cantidad": 0.0, "coste": 0.0})

        if side == "BUY":
            if quote_net > capital + 1e-9:
                raise ValueError("journal PAPER compra mas capital del disponible")
            coste_anterior = pos["cantidad"] * pos["coste"]
            nuevo_total = pos["cantidad"] + qty
            pos["coste"] = (coste_anterior + quote_net) / nuevo_total
            pos["cantidad"] = nuevo_total
            capital -= quote_net
        else:
            if qty > pos["cantidad"] + 1e-12:
                raise ValueError("journal PAPER vende mas posicion de la disponible")
            coste_vendido = qty * pos["coste"]
            pnl_operacion = quote_net - coste_vendido
            pnl += pnl_operacion
            if en_dia:
                pnl_dia += pnl_operacion
            capital += quote_net
            pos["cantidad"] -= qty
            if pos["cantidad"] <= 1e-12:
                pos["cantidad"] = 0.0
                pos["coste"] = 0.0

        fees += fee
        n += 1
        if en_dia:
            n_dia += 1

    return EstadoPaper(
        initial_capital_usd=inicial,
        capital_usd=capital,
        posiciones={
            s: PosicionPaper(cantidad=p["cantidad"], coste_medio_neto=p["coste"])
            for s, p in posiciones.items() if p["cantidad"] > 1e-12
        },
        realized_pnl_usd=pnl,
        fees_total_usd=fees,
        operaciones=n,
        realized_pnl_dia_usd=pnl_dia,
        operaciones_dia=n_dia,
    )


def obtener_o_crear_ledger(db, *, usuario_id: int, initial_capital_usd: float):
    """Devuelve el ledger estable del usuario; el capital inicial no se resetea."""
    if usuario_id is None:
        raise ValueError("usuario_id es obligatorio para PAPER persistente")
    ledger = db.query(models.PaperLedger).filter_by(usuario_id=usuario_id).first()
    if ledger is not None:
        return ledger

    inicial = _float(initial_capital_usd, nombre="initial_capital_usd")
    if inicial <= 0:
        raise ValueError("initial_capital_usd debe ser positivo")
    ledger = models.PaperLedger(
        usuario_id=usuario_id,
        initial_capital_usd=inicial,
        creado_en=datetime.utcnow(),
    )
    db.add(ledger)
    db.flush()
    return ledger


def operaciones_desde_db(db, ledger):
    return (
        db.query(models.PaperOperacion)
        .filter_by(ledger_id=ledger.id)
        .order_by(models.PaperOperacion.id.asc())
        .all()
    )


def estado_desde_db(db, ledger, *, dia=None) -> EstadoPaper:
    return reconstruir_paper(
        ledger.initial_capital_usd,
        operaciones_desde_db(db, ledger),
        dia=dia,
    )


def ultima_venta_desde_db(db, ledger, symbol: str) -> Optional[float]:
    row = (
        db.query(models.PaperOperacion)
        .filter_by(ledger_id=ledger.id, symbol=str(symbol).strip().upper(), side="SELL")
        .order_by(models.PaperOperacion.id.desc())
        .first()
    )
    return float(row.fill_price) if row is not None else None


def registrar_fill(
    db,
    *,
    ledger,
    symbol: str,
    reference_price,
    fill: FillPaper,
    strategy: Optional[str] = None,
    expected_edge_bps=None,
    expected_cost_bps=None,
    expected_net_bps=None,
):
    """Añade UN fill PAPER completo al journal; no hace commit por su cuenta.

    Valida contra el estado reconstruido ANTES del INSERT. Asi una llamada
    defectuosa no puede persistir una compra sin capital ni una venta mayor que
    la posicion disponible y dejar el journal imposible de reconstruir.
    """
    if not isinstance(fill, FillPaper) or not fill.completo:
        raise ValueError("fill PAPER incompleto no se puede persistir")
    if fill.base_ejecutada is None or fill.precio_vwap is None:
        raise ValueError("fill PAPER carece de cantidad o VWAP")
    if fill.quote_bruto is None or fill.quote_neto is None or fill.fee_usd is None:
        raise ValueError("fill PAPER carece de contabilidad")
    if fill.slippage_bps is None or fill.fee_taker_bps_por_lado is None:
        raise ValueError("fill PAPER carece de friccion")

    symbol_norm = str(symbol).strip().upper()
    if not symbol_norm:
        raise ValueError("symbol PAPER vacio")

    estado = estado_desde_db(db, ledger)
    qty = float(fill.base_ejecutada)
    quote_net = float(fill.quote_neto)
    if fill.lado == "BUY":
        if quote_net > estado.capital_usd + 1e-9:
            raise ValueError("fill PAPER consume mas capital del disponible")
    elif fill.lado == "SELL":
        disponible = estado.posiciones.get(symbol_norm)
        if disponible is None or qty > disponible.cantidad + 1e-12:
            raise ValueError("fill PAPER vende mas posicion de la disponible")
    else:
        raise ValueError("lado PAPER invalido")

    row = models.PaperOperacion(
        ledger_id=ledger.id,
        symbol=symbol_norm,
        side=fill.lado,
        reference_price=_float(reference_price, nombre="reference_price"),
        fill_price=float(fill.precio_vwap),
        base_quantity=qty,
        quote_gross=float(fill.quote_bruto),
        fee_usd=float(fill.fee_usd),
        quote_net=quote_net,
        slippage_bps=float(fill.slippage_bps),
        fee_taker_bps=float(fill.fee_taker_bps_por_lado),
        strategy=strategy,
        expected_edge_bps=(None if expected_edge_bps is None else float(expected_edge_bps)),
        expected_cost_bps=(None if expected_cost_bps is None else float(expected_cost_bps)),
        expected_net_bps=(None if expected_net_bps is None else float(expected_net_bps)),
        creada_en=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row
