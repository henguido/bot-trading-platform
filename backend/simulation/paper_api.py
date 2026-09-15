"""Vistas de lectura del ledger PAPER para la API.

No crea ledgers, no escribe filas y no consulta balances privados del broker.
El estado financiero se reconstruye exclusivamente desde paper_operaciones.
"""
from __future__ import annotations

from typing import Callable, Optional

import pytz

from backend.app import models
from backend.economia.estadisticas_paper import resumen_por_estrategia
from backend.finanzas import campos, pnl_no_realizado
from backend.simulation.estado_operativo import construir_estado_operativo
from backend.simulation.paper_ledger import operaciones_desde_db, reconstruir_paper

_TZ_CR = pytz.timezone("America/Costa_Rica")
_METODO_PNL_ABIERTO = "MTM_INCLUYE_COSTE_ENTRADA_NO_COSTE_SALIDA"
_METODO_PNL_REALIZADO = "NETO_DE_FEES_DE_FILLS_REALIZADOS"


def _ledger_usuario(db, usuario_id: int):
    return (
        db.query(models.PaperLedger)
        .filter(models.PaperLedger.usuario_id == usuario_id)
        .first()
    )


def _timestamp_cr(valor) -> Optional[str]:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = pytz.utc.localize(valor)
    return valor.astimezone(_TZ_CR).strftime("%Y-%m-%d %H:%M:%S")


def historial_paper(db, *, usuario_id: int):
    """Devuelve fills PAPER ejecutados del usuario, nunca decisiones GPT."""
    ledger = _ledger_usuario(db, usuario_id)
    if ledger is None:
        return []

    operaciones = (
        db.query(models.PaperOperacion)
        .filter(models.PaperOperacion.ledger_id == ledger.id)
        .order_by(models.PaperOperacion.id.desc())
        .all()
    )
    salida = []
    for op in operaciones:
        action = "COMPRAR" if op.side == "BUY" else "VENDER"
        salida.append({
            "symbol": op.symbol,
            "action": action,
            "quantity": float(op.base_quantity),
            "price": float(op.fill_price),
            "timestamp": _timestamp_cr(op.creada_en),
            "context": {
                "strategy": op.strategy,
                "expected_edge_bps": op.expected_edge_bps,
                "expected_cost_bps": op.expected_cost_bps,
                "expected_net_bps": op.expected_net_bps,
            },
            "decision_gpt": None,
            "risk_score": None,
            "paper_operation_id": op.id,
            "side": op.side,
            "reference_price": float(op.reference_price),
            "fill_price": float(op.fill_price),
            "base_quantity": float(op.base_quantity),
            "quote_gross": float(op.quote_gross),
            "fee_usd": float(op.fee_usd),
            "quote_net": float(op.quote_net),
            "slippage_bps": float(op.slippage_bps),
            "fee_taker_bps": float(op.fee_taker_bps),
            "strategy": op.strategy,
            "expected_edge_bps": op.expected_edge_bps,
            "expected_cost_bps": op.expected_cost_bps,
            "expected_net_bps": op.expected_net_bps,
        })
    return salida


def resumen_paper(
    db,
    *,
    usuario_id: int,
    initial_capital_usd: float,
    obtener_precio: Callable[[str], Optional[float]],
):
    """Marca a mercado el ledger PAPER y atribuye resultados por estrategia.

    El coste medio de una posición incluye la fee de entrada porque así se
    reconstruye el ledger. El P&L realizado ya incluye fees de entrada/salida.
    El P&L no realizado todavía no descuenta una hipotética fee/slippage de
    salida, por lo que la API lo etiqueta como MTM pre-coste de salida.

    La atribución por estrategia reutiliza las mismas filas del journal que ya
    se leen para reconstruir la cartera; no añade red ni otra consulta al broker.
    """
    ledger = _ledger_usuario(db, usuario_id)
    if ledger is None:
        operaciones = ()
        estado = reconstruir_paper(initial_capital_usd, operaciones)
    else:
        operaciones = operaciones_desde_db(db, ledger)
        estado = reconstruir_paper(ledger.initial_capital_usd, operaciones)

    economia_estrategias = resumen_por_estrategia(operaciones)

    resumen = []
    capital = float(estado.capital_usd)
    fila_cash = {
        "symbol": "USDT",
        "cantidad": round(capital, 6),
        "precio_actual": 1.0,
        "valor_actual": round(capital, 2),
        "pnl_metodologia": "CAJA",
    }
    fila_cash.update(campos("average_price", 1.0, redondeo=6))
    fila_cash.update(campos("pnl", 0.0, redondeo=2))
    resumen.append(fila_cash)

    valor_total = capital
    valor_total_conocido = True
    pnl_no_realizado_total = 0.0
    pnl_no_realizado_conocido = True

    for symbol, posicion in sorted(estado.posiciones.items()):
        cantidad = float(posicion.cantidad)
        medio = float(posicion.coste_medio_neto)
        try:
            precio_actual = obtener_precio(symbol)
            precio_actual = None if precio_actual is None else float(precio_actual)
            if precio_actual is not None and precio_actual <= 0:
                precio_actual = None
        except Exception:
            precio_actual = None

        if precio_actual is None:
            valor_actual = None
            pnl = None
            valor_total_conocido = False
            pnl_no_realizado_conocido = False
            motivo = f"precio público no disponible para {symbol}"
        else:
            valor_actual = cantidad * precio_actual
            pnl = pnl_no_realizado(precio_actual, medio, cantidad)
            valor_total += valor_actual
            pnl_no_realizado_total += pnl
            motivo = None

        fila = {
            "symbol": symbol,
            "cantidad": round(cantidad, 6),
            "precio_actual": (
                None if precio_actual is None else round(precio_actual, 4)
            ),
            "valor_actual": (
                None if valor_actual is None else round(valor_actual, 2)
            ),
            "pnl_metodologia": _METODO_PNL_ABIERTO,
        }
        fila.update(campos("average_price", medio, redondeo=6))
        fila.update(campos("pnl", pnl, redondeo=2, motivo=motivo))
        resumen.append(fila)

    pnl_realizado = float(estado.realized_pnl_usd)
    pnl_total = (
        pnl_realizado + pnl_no_realizado_total
        if pnl_no_realizado_conocido else None
    )
    posiciones_abiertas = len(estado.posiciones)
    estado_operativo = construir_estado_operativo(
        estado=estado,
        valoracion_completa=valor_total_conocido,
        estrategias_paper=economia_estrategias,
    )

    salida = {
        "modo": "PAPER",
        "resumen": resumen,
        "valor_total_usd": (
            round(valor_total, 2) if valor_total_conocido else None
        ),
        "valor_total_usd_status": (
            "DISPONIBLE" if valor_total_conocido else "NO_DISPONIBLE"
        ),
        "valor_total_usd_metodologia": "CAJA_MAS_MTM_PRE_COSTE_SALIDA",
        "capital_disponible_usd": round(capital, 6),
        "initial_capital_usd": float(estado.initial_capital_usd),
        "pnl_realizado_usd": round(pnl_realizado, 6),
        "pnl_realizado_metodologia": _METODO_PNL_REALIZADO,
        "pnl_no_realizado_usd": (
            round(pnl_no_realizado_total, 6)
            if pnl_no_realizado_conocido else None
        ),
        "pnl_no_realizado_metodologia": _METODO_PNL_ABIERTO,
        "pnl_total_metodologia": "REALIZADO_NETO_MAS_MTM_PRE_COSTE_SALIDA",
        "pnl_total_es_neto_liquidacion": posiciones_abiertas == 0,
        "fees_total_usd": round(float(estado.fees_total_usd), 6),
        "operaciones": int(estado.operaciones),
        "posiciones_abiertas": posiciones_abiertas,
        "estrategias_paper": economia_estrategias,
        "estado_operativo": estado_operativo,
    }
    salida.update(campos(
        "pnl_total",
        pnl_total,
        redondeo=2,
        motivo=(None if pnl_no_realizado_conocido
                else "al menos una posición carece de precio público"),
    ))
    return salida
