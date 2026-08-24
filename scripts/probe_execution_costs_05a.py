"""Probe PAPER 05A: cuantifica si merece la pena perseguir ejecucion maker.

No ejecuta ordenes, no llama LLM y no modifica parametros. Reutiliza las fees
maker/taker del mismo GET /account, toma Top-5 del scanner y compara:
- coste round-trip taker observado;
- piso teorico maker fee-only;
- ahorro maximo teorico si maker evitara toda microfriccion taker.

El escenario maker NO es ejecutable: no modela fill ni adverse selection.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from backend import scanner
from backend.config import settings
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.costes import spread_bps_desde_bid_ask
from backend.economia.ejecucion_05a import comparar_ejecucion
from backend.economia.fuentes import estimar_slippage_roundtrip
from backend.risk.estado import EstadoRiesgo
from backend.risk.motor import MotorRiesgo
from backend.utils.asset_collector import get_available_assets

ARTIFACTO = RAIZ_REPO / "artifacts" / "execution-costs-probe-05a.json"
FINALISTAS = 5


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05A execution probe solo puede ejecutarse en PAPER; LIVE bloqueado")

    activos, _balances, _symbols_info, costes = get_available_assets(
        incluir_costes_cuenta=True
    )
    fee_taker = costes.get("fee_taker_bps_por_lado")
    fee_maker = costes.get("fee_maker_bps_por_lado")

    binance = BinanceConnector()
    snapshot = binance.get_price_snapshot()
    metricas = binance.get_market_metrics()

    entrada = []
    for a in activos:
        if a.get("type") != "crypto":
            continue
        sym = a.get("symbol")
        precio = snapshot.get(sym)
        if precio is None or not math.isfinite(float(precio)) or float(precio) <= 0:
            continue
        entrada.append({
            "symbol": sym,
            "price": float(precio),
            "position_quantity": 0.0,
            "average_price": None,
            "last_movement": None,
            "last_sell_price": None,
            "_balance_detected": False,
            "_position_detected": False,
        })

    resumen_scanner = scanner.ResumenScanner()
    top20 = scanner.aplicar(
        entrada, metricas, top_n=scanner.TOP_N_POR_DEFECTO, resumen=resumen_scanner
    )

    motor = MotorRiesgo()
    estado = EstadoRiesgo(dia=date.today())
    capital = float(settings.INITIAL_CAPITAL_USD)

    filas = []
    for rank, activo in enumerate(top20[:FINALISTAS], start=1):
        sym = activo.get("symbol")
        if not sym:
            continue
        notional = motor.limite_compra(
            capital_disponible=capital, estado=estado, symbol=sym
        ).quote_permitido
        m = metricas.get(sym) or {}
        bid = m.get("bidPrice")
        ask = m.get("askPrice")
        try:
            spread = spread_bps_desde_bid_ask(bid, ask)
        except ValueError:
            spread = None

        libro = binance.get_order_book(sym, limit=100)
        slip = estimar_slippage_roundtrip(libro, quote_amount=notional)
        slip_bps = (float(slip.slippage_bps_por_lado_promedio)
                    if slip.estado == "DISPONIBLE" and
                    slip.slippage_bps_por_lado_promedio is not None else None)

        comp = comparar_ejecucion(
            fee_taker_bps_por_lado=fee_taker,
            fee_maker_bps_por_lado=fee_maker,
            spread_bps=float(spread) if spread is not None else None,
            slippage_bps_por_lado=slip_bps,
        )
        fila = {"rank": rank, "symbol": sym, "notional_usd": notional}
        fila.update(comp.como_dict())
        filas.append(fila)

    disponibles = [f for f in filas if f["estado"] == "DISPONIBLE"]
    ahorro_fee = [f["ahorro_fee_roundtrip_bps"] for f in disponibles]
    ahorro_max = [f["ahorro_maximo_teorico_bps"] for f in disponibles]
    payload = {
        "phase": "05A",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "maker_fill_modelled": False,
        "maker_cost_is_executable_estimate": False,
        "capital_reference_usd": capital,
        "fee_taker_bps_por_lado": fee_taker,
        "fee_maker_bps_por_lado": fee_maker,
        "fee_taker_source": costes.get("fuente_fee"),
        "fee_maker_source": costes.get("fuente_fee_maker"),
        "scanner_selected": [a.get("symbol") for a in top20],
        "finalists": filas,
        "summary": {
            "evaluated": len(filas),
            "available": len(disponibles),
            "fee_saving_roundtrip_mean_bps": (
                sum(ahorro_fee) / len(ahorro_fee) if ahorro_fee else None
            ),
            "max_theoretical_saving_mean_bps": (
                sum(ahorro_max) / len(ahorro_max) if ahorro_max else None
            ),
        },
        "interpretation": (
            "maker fee-only es un piso teorico optimista. No incorpora tasa de fill, "
            "cola, adverse selection ni coste de oportunidad; no puede alimentar el gate 05A."
        ),
    }

    ARTIFACTO.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTO.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(resumen_scanner.linea(requests=0))
    print(json.dumps(payload["summary"], indent=2))
    print(f"maker_bps={fee_maker} taker_bps={fee_taker}")
    print(f"artifact={ARTIFACTO.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
