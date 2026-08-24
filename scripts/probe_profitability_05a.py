"""Probe de observacion BOT 2.0-05A: scanner -> edge -> costes -> rentabilidad.

No llama LLM, no escribe BD y no ejecuta operaciones. Usa endpoints existentes
de Binance y guarda un artefacto JSON sin credenciales.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend import scanner
from backend.config import settings
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.filtro_rentabilidad_05a import (
    ResumenFiltroRentabilidad,
    filtrar_compras_rentables,
)
from backend.risk.estado import EstadoRiesgo
from backend.risk.motor import MotorRiesgo
from backend.utils.asset_collector import get_available_assets

ARTIFACTO = Path("artifacts/profitability-probe-05a.json")


def _serializar_evaluacion(info):
    out = {"estado": info.get("estado"), "motivo": info.get("motivo")}
    edge = info.get("edge")
    if edge is not None:
        out["edge"] = {
            "estado": edge.estado,
            "edge_bruto_bps": edge.edge_bruto_bps,
            "muestras": edge.muestras,
            "retorno_mediano_bps": edge.retorno_mediano_bps,
            "retorno_p25_bps": edge.retorno_p25_bps,
            "tasa_positiva": edge.tasa_positiva,
            "momentum_6h_bps": edge.momentum_6h_bps,
            "momentum_24h_bps": edge.momentum_24h_bps,
            "horizonte_h": edge.horizonte_h,
        }
    rentabilidad = info.get("rentabilidad")
    if rentabilidad is not None:
        out["rentabilidad"] = rentabilidad.como_dict()
    return out


def main():
    activos, _balances, symbols_info, costes_cuenta = get_available_assets(
        incluir_costes_cuenta=True)
    fee = costes_cuenta.get("fee_taker_bps_por_lado")

    binance = BinanceConnector()
    snapshot = binance.get_price_snapshot()
    metricas = binance.get_market_metrics()

    entrada = []
    for a in activos:
        if a.get("type") != "crypto":
            continue
        sym = a.get("symbol")
        precio = snapshot.get(sym)
        if precio is None:
            continue
        entrada.append({
            "symbol": sym,
            "price": precio,
            "position_quantity": 0.0,
            "average_price": None,
            "last_movement": None,
            "last_sell_price": None,
            "_balance_detected": False,
            "_position_detected": False,
        })

    resumen_scanner = scanner.ResumenScanner()
    top20 = scanner.aplicar(
        entrada, metricas, top_n=scanner.TOP_N_POR_DEFECTO,
        resumen=resumen_scanner)

    # Probe independiente: estado PAPER vacio con el capital inicial configurado.
    # No pretende reconstruir el libro de un proceso actualmente en ejecucion.
    motor = MotorRiesgo()
    estado = EstadoRiesgo(dia=date.today())
    capital = float(settings.INITIAL_CAPITAL_USD)
    notionals = {
        a["symbol"]: motor.limite_compra(
            capital_disponible=capital, estado=estado, symbol=a["symbol"]
        ).quote_permitido
        for a in top20 if not a.get("_position_detected")
    }

    resumen_05a = ResumenFiltroRentabilidad()
    filtrados, evaluaciones = filtrar_compras_rentables(
        top20,
        metricas,
        fee_taker_bps_por_lado=fee,
        notional_por_symbol=notionals,
        binance=binance,
        resumen=resumen_05a,
    )

    aptos = [a for a in filtrados if not a.get("_position_detected")]
    payload = {
        "phase": "05A",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "trading_mode_expected": "PAPER",
        "capital_reference_usd": capital,
        "fee_taker_bps_por_lado": fee,
        "fee_source": costes_cuenta.get("fuente_fee"),
        "universe_crypto": len(entrada),
        "scanner_selected": [a.get("symbol") for a in top20],
        "profitability_finalists_max": 5,
        "profitability_approved": [
            {
                "symbol": a.get("symbol"),
                "edge_bruto_bps": a.get("_edge_bruto_bps"),
                "edge_neto_bps": a.get("_edge_neto_bps"),
                "notional_usd": notionals.get(a.get("symbol")),
            }
            for a in aptos
        ],
        "evaluations": {
            sym: _serializar_evaluacion(info)
            for sym, info in evaluaciones.items()
        },
        "scanner_summary": resumen_scanner.linea(requests=0),
        "profitability_summary": resumen_05a.linea(),
        "method": {
            "interval": "1h",
            "history_limit": 1000,
            "momentum_short_h": 6,
            "momentum_long_h": 24,
            "forward_horizon_h": 4,
            "min_samples": 30,
            "gross_edge": "historical bullish-state forward-return p25",
            "net_margin_min_bps": 5.0,
            "costs": "observed spread + account taker fee round-trip + order-book slippage round-trip",
        },
    }

    ARTIFACTO.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTO.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(resumen_scanner.linea(requests=0))
    print(resumen_05a.linea())
    print(json.dumps(payload["profitability_approved"], indent=2))
    print(f"artifact={ARTIFACTO}")


if __name__ == "__main__":
    main()
