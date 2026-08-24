"""Probe PAPER 05B: compara 05A congelado contra challenger por regimen.

No ejecuta ordenes ni llama LLM. Reutiliza Top-5, una sola descarga de velas por
activo y la fee taker real. 05A se calcula solo como referencia; 05B evalua
continuacion y pullback dentro de tendencia 24h con el mismo p25 conservador.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from backend import scanner
from backend.config import settings
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.edge_empirico import estimar_edge, normalizar_klines
from backend.economia.edge_regimen_05b import estimar_edge_regimen
from backend.economia.fuentes import estimar_slippage_roundtrip
from backend.economia.rentabilidad import evaluar_desde_componentes
from backend.risk.estado import EstadoRiesgo
from backend.risk.motor import MotorRiesgo
from backend.utils.asset_collector import get_available_assets

ARTIFACTO = RAIZ_REPO / "artifacts" / "edge-regime-probe-05b.json"
FINALISTAS = 5
MARGEN_NETO_MINIMO_BPS = 5.0


def _edge_dict(e):
    return {
        "estado": e.estado,
        "regimen": getattr(e, "regimen", None),
        "edge_bruto_bps": e.edge_bruto_bps,
        "muestras": e.muestras,
        "retorno_mediano_bps": e.retorno_mediano_bps,
        "retorno_p25_bps": e.retorno_p25_bps,
        "tasa_positiva": e.tasa_positiva,
        "momentum_6h_bps": e.momentum_6h_bps,
        "momentum_24h_bps": e.momentum_24h_bps,
    }


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05B probe solo puede ejecutarse en PAPER; LIVE bloqueado")

    ahora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    activos, _balances, _symbols_info, costes = get_available_assets(
        incluir_costes_cuenta=True
    )
    fee = costes.get("fee_taker_bps_por_lado")

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
    estado_riesgo = EstadoRiesgo(dia=date.today())
    capital = float(settings.INITIAL_CAPITAL_USD)
    filas = []

    for rank, activo in enumerate(top20[:FINALISTAS], start=1):
        sym = activo.get("symbol")
        if not sym:
            continue
        notional = motor.limite_compra(
            capital_disponible=capital, estado=estado_riesgo, symbol=sym
        ).quote_permitido
        klines = binance.get_recent_klines(sym, interval="1h", limit=1000)
        velas = normalizar_klines(klines, ahora_ms=ahora_ms)
        edge_a = estimar_edge(velas)
        edge_b = estimar_edge_regimen(velas)

        fila = {
            "rank": rank,
            "symbol": sym,
            "notional_usd": notional,
            "edge_05a": _edge_dict(edge_a),
            "edge_05b": _edge_dict(edge_b),
            "rentabilidad_05b": None,
        }

        if edge_b.utilizable and fee is not None:
            m = metricas.get(sym) or {}
            bid, ask = m.get("bidPrice"), m.get("askPrice")
            libro = binance.get_order_book(sym, limit=100)
            slip = estimar_slippage_roundtrip(libro, quote_amount=notional)
            if bid is not None and ask is not None and slip.estado == "DISPONIBLE":
                ev = evaluar_desde_componentes(
                    edge_bruto_bps=edge_b.edge_bruto_bps,
                    margen_neto_minimo_bps=MARGEN_NETO_MINIMO_BPS,
                    notional_usd=notional,
                    bid=bid,
                    ask=ask,
                    fee_taker_bps_por_lado=fee,
                    slippage_bps_por_lado=slip.slippage_bps_por_lado_promedio,
                    exigir_costo_ia=False,
                )
                fila["rentabilidad_05b"] = ev.como_dict()
        filas.append(fila)

    aptos_b = [
        f for f in filas
        if isinstance(f.get("rentabilidad_05b"), dict)
        and f["rentabilidad_05b"].get("apta")
    ]
    payload = {
        "phase": "05B",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "modifies_05a": False,
        "fee_taker_bps_por_lado": fee,
        "fee_source": costes.get("fuente_fee"),
        "capital_reference_usd": capital,
        "margin_net_min_bps": MARGEN_NETO_MINIMO_BPS,
        "scanner_selected": [a.get("symbol") for a in top20],
        "finalists": filas,
        "summary": {
            "evaluated": len(filas),
            "05a_usable_edges": sum(1 for f in filas if f["edge_05a"]["edge_bruto_bps"] is not None),
            "05b_usable_edges": sum(1 for f in filas if f["edge_05b"]["edge_bruto_bps"] is not None),
            "05b_pullback_regimes": sum(1 for f in filas if f["edge_05b"]["regimen"] == "PULLBACK_TENDENCIA"),
            "05b_continuation_regimes": sum(1 for f in filas if f["edge_05b"]["regimen"] == "CONTINUACION"),
            "05b_profitability_approved": len(aptos_b),
        },
        "interpretation": (
            "05B es challenger predefinido; no reemplaza 05A ni modifica su shadow. "
            "Una mayor cobertura solo es util si el p25 historico supera costes reales."
        ),
    }

    ARTIFACTO.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTO.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(resumen_scanner.linea(requests=0))
    print(json.dumps(payload["summary"], indent=2))
    for f in filas:
        b = f["edge_05b"]
        r = f.get("rentabilidad_05b") or {}
        print(f"{f['rank']} {f['symbol']} regimen={b['regimen']} edge05b={b['edge_bruto_bps']} "
              f"muestras={b['muestras']} net={r.get('edge_neto_bps')} apta={r.get('apta')}")
    print(f"artifact={ARTIFACTO.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
