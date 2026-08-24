"""Filtro pre-LLM de rentabilidad para compras nuevas BOT 2.0-05A.

Entrada esperada: salida del scanner, con posiciones abiertas primero y compras
nuevas ya ordenadas por score. Solo profundiza en los primeros 5 candidatos de
compra. Las posiciones abiertas pasan intactas para que el bot pueda vender.

Orden por candidato:
1) historia 1h gratuita -> edge empirico conservador;
2) si hay edge, profundidad publica -> slippage;
3) fee real ya reutilizada del GET /account + spread del snapshot 24h;
4) gate 05A;
5) solo APTA sigue al LLM/RiskEngine.

No ejecuta ordenes y no usa LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from backend.economia.edge_empirico import (
    FINALISTAS_MAXIMOS,
    estimar_edge,
    normalizar_klines,
)
from backend.economia.fuentes import estimar_slippage_roundtrip
from backend.economia.rentabilidad import evaluar_desde_componentes

MARGEN_NETO_MINIMO_BPS_05A = 5.0


@dataclass
class ResumenFiltroRentabilidad:
    preservados: int = 0
    candidatos: int = 0
    profundizados: int = 0
    aptos: int = 0
    rechazados_edge: int = 0
    rechazados_costes: int = 0
    rechazados_margen: int = 0
    motivos: Dict[str, int] = field(default_factory=dict)

    def anotar(self, motivo: str) -> None:
        self.motivos[motivo] = self.motivos.get(motivo, 0) + 1

    def linea(self) -> str:
        detalle = ",".join(f"{k}={v}" for k, v in sorted(self.motivos.items()))
        return (f"[RENTABILIDAD-05A] preservados={self.preservados} "
                f"candidatos={self.candidatos} profundizados={self.profundizados} "
                f"aptos={self.aptos} rechazados_edge={self.rechazados_edge} "
                f"rechazados_costes={self.rechazados_costes} "
                f"rechazados_margen={self.rechazados_margen}"
                + (f" motivos[{detalle}]" if detalle else ""))


def _ahora_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def filtrar_compras_rentables(
    activos,
    metricas_por_symbol,
    *,
    fee_taker_bps_por_lado,
    notional_por_symbol,
    binance,
    medidor=None,
    margen_neto_minimo_bps=MARGEN_NETO_MINIMO_BPS_05A,
    finalistas_maximos=FINALISTAS_MAXIMOS,
    ahora_ms: Optional[int] = None,
    resumen: Optional[ResumenFiltroRentabilidad] = None,
):
    """Devuelve `(activos_filtrados, evaluaciones_por_symbol)`.

    Si la fee es desconocida, no se gastan peticiones de velas/order book: las
    compras nuevas son no evaluables y se bloquean. Desconocido nunca es cero.
    """
    r = resumen if resumen is not None else ResumenFiltroRentabilidad()
    preservados = [a for a in (activos or ()) if a.get("_position_detected")]
    candidatos = [a for a in (activos or ()) if not a.get("_position_detected")]
    r.preservados = len(preservados)
    r.candidatos = len(candidatos)

    evaluaciones = {}
    if fee_taker_bps_por_lado is None:
        for a in candidatos[:max(0, int(finalistas_maximos))]:
            sym = a.get("symbol")
            if sym:
                evaluaciones[sym] = {"estado": "NO_EVALUABLE", "motivo": "FEE_DESCONOCIDA"}
                r.rechazados_costes += 1
                r.anotar("FEE_DESCONOCIDA")
        return preservados, evaluaciones

    ahora = _ahora_ms() if ahora_ms is None else int(ahora_ms)
    aptos = []
    op_klines = (medidor.operacion if medidor is not None else None)

    for a in candidatos[:max(0, int(finalistas_maximos))]:
        sym = a.get("symbol")
        if not sym:
            continue
        r.profundizados += 1
        notional = (notional_por_symbol or {}).get(sym)
        if notional is None or float(notional) <= 0:
            evaluaciones[sym] = {"estado": "NO_EVALUABLE", "motivo": "NOTIONAL_NO_DISPONIBLE"}
            r.rechazados_costes += 1
            r.anotar("NOTIONAL_NO_DISPONIBLE")
            continue

        medicion_klines = op_klines("binance", "edge_klines_05a") if op_klines else None
        filas = binance.get_recent_klines(sym, interval="1h", limit=1000,
                                          medicion=medicion_klines)
        edge = estimar_edge(normalizar_klines(filas, ahora_ms=ahora))
        if not edge.utilizable:
            evaluaciones[sym] = {
                "estado": "NO_EVALUABLE",
                "motivo": edge.estado,
                "edge": edge,
            }
            r.rechazados_edge += 1
            r.anotar(edge.estado)
            continue

        fila_m = (metricas_por_symbol or {}).get(sym) or {}
        bid = fila_m.get("bidPrice")
        ask = fila_m.get("askPrice")
        if bid is None or ask is None:
            evaluaciones[sym] = {"estado": "NO_EVALUABLE", "motivo": "BID_ASK_DESCONOCIDO", "edge": edge}
            r.rechazados_costes += 1
            r.anotar("BID_ASK_DESCONOCIDO")
            continue

        medicion_book = op_klines("binance", "order_book_05a") if op_klines else None
        libro = binance.get_order_book(sym, limit=100, medicion=medicion_book)
        slip = estimar_slippage_roundtrip(libro, quote_amount=notional)
        if not slip.estado == "DISPONIBLE":
            evaluaciones[sym] = {"estado": "NO_EVALUABLE", "motivo": "SLIPPAGE_NO_DISPONIBLE", "edge": edge}
            r.rechazados_costes += 1
            r.anotar("SLIPPAGE_NO_DISPONIBLE")
            continue

        ev = evaluar_desde_componentes(
            edge_bruto_bps=edge.edge_bruto_bps,
            margen_neto_minimo_bps=margen_neto_minimo_bps,
            notional_usd=notional,
            bid=bid,
            ask=ask,
            fee_taker_bps_por_lado=fee_taker_bps_por_lado,
            slippage_bps_por_lado=slip.slippage_bps_por_lado_promedio,
            exigir_costo_ia=False,
        )
        evaluaciones[sym] = {"estado": ev.estado, "rentabilidad": ev, "edge": edge}
        if ev.apta:
            copia = dict(a)
            copia["_edge_bruto_bps"] = float(edge.edge_bruto_bps)
            copia["_edge_neto_bps"] = float(ev.edge_neto_bps)
            aptos.append(copia)
            r.aptos += 1
        else:
            r.rechazados_margen += 1
            for motivo in ev.motivos:
                r.anotar(motivo)

    return preservados + aptos, evaluaciones
