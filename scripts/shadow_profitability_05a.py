"""Shadow longitudinal BOT 2.0-05A.

Cada ejecucion hace dos cosas, siempre en PAPER y sin ordenes/LLM:
1) madura observaciones antiguas cuyo horizonte de 4 h ya paso;
2) toma una nueva foto scanner -> Top 5 -> edge -> costes -> gate 05A.

El estado queda SOLO local en artifacts/profitability-shadow-05a-state.json.
No se usa para ajustar parametros automaticamente. Su proposito es medir OOS
si el edge estimado y el gate de rentabilidad predicen resultados netos utiles.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

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

ESTADO_PATH = RAIZ_REPO / "artifacts" / "profitability-shadow-05a-state.json"
RESUMEN_PATH = RAIZ_REPO / "artifacts" / "profitability-shadow-05a-summary.json"
HORIZONTE_H = 4
FINALISTAS_MAX = 5


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(valor: str) -> datetime:
    return datetime.fromisoformat(valor).astimezone(timezone.utc)


def _bucket_4h(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    h = (dt.hour // HORIZONTE_H) * HORIZONTE_H
    return dt.replace(hour=h, minute=0, second=0, microsecond=0).isoformat()


def _cargar_estado() -> dict:
    if not ESTADO_PATH.exists():
        return {
            "phase": "05A",
            "mode": "SHADOW",
            "created_at": _iso(datetime.now(timezone.utc)),
            "observations": [],
        }
    try:
        data = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Estado shadow ilegible: {ESTADO_PATH}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise RuntimeError("Estado shadow invalido: falta observations[]")
    return data


def _guardar_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    temporal.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporal.replace(path)


def _serializar_evaluacion(info: dict) -> dict:
    out = {"estado": info.get("estado"), "motivo": info.get("motivo")}
    edge = info.get("edge")
    if edge is not None:
        out["edge"] = {
            "estado": edge.estado,
            "edge_bruto_bps": edge.edge_bruto_bps,
            "muestras": edge.muestras,
            "retorno_mediano_bps": edge.retorno_mediano_bps,
            "retorno_p25_bps": edge.retorno_p25_bps,
            # 05F: telemetria solamente. 05A sigue decidiendo con p25.
            "retorno_medio_bps": edge.retorno_medio_bps,
            "tasa_positiva": edge.tasa_positiva,
            "momentum_6h_bps": edge.momentum_6h_bps,
            "momentum_24h_bps": edge.momentum_24h_bps,
            "horizonte_h": edge.horizonte_h,
        }
    ev = info.get("rentabilidad")
    if ev is not None:
        out["rentabilidad"] = ev.como_dict()
    return out


def _precio_horizonte(binance: BinanceConnector, symbol: str, due_ms: int):
    """Busca precio observable alrededor del horizonte sin interpolar.

    Prioriza 1m. Si la observacion es vieja y esa ventana ya no cabe en las
    ultimas 1000 velas, degrada explicitamente a 5m y luego 1h. Devuelve la
    resolucion usada para que el analisis no confunda precision desconocida.
    """
    for interval, max_offset_ms in (("1m", 60_000), ("5m", 300_000), ("1h", 3_600_000)):
        filas = binance.get_recent_klines(symbol, interval=interval, limit=1000)
        mejor = None
        for fila in filas or ():
            try:
                open_ms = int(fila[0])
                close = float(fila[4])
                close_ms = int(fila[6])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(close) or close <= 0:
                continue
            # Primera vela que contiene el instante due; si due coincide con el
            # borde, preferimos la vela que ya comenzo en due.
            if open_ms <= due_ms <= close_ms:
                offset = abs(close_ms - due_ms)
                if offset <= max_offset_ms:
                    mejor = (close, close_ms, interval, offset / 1000.0)
                    break
        if mejor is not None:
            return mejor
    return None


def _madurar(estado: dict, binance: BinanceConnector, ahora: datetime) -> int:
    ahora_ms = int(ahora.timestamp() * 1000)
    maduras = 0
    for obs in estado["observations"]:
        if obs.get("settled"):
            continue
        due = _parse_iso(obs["due_at"])
        if int(due.timestamp() * 1000) > ahora_ms:
            continue
        salida = _precio_horizonte(binance, obs["symbol"], int(due.timestamp() * 1000))
        if salida is None:
            obs["settlement_status"] = "PRECIO_HORIZONTE_NO_DISPONIBLE"
            continue
        precio_salida, close_ms, resolucion, offset_s = salida
        precio_entrada = float(obs["entry_price"])
        bruto_bps = (precio_salida / precio_entrada - 1.0) * 10_000.0
        coste = obs.get("known_cost_total_bps")
        neto_bps = bruto_bps - float(coste) if coste is not None else None
        edge = obs.get("predicted_edge_bruto_bps")
        obs.update({
            "settled": True,
            "settled_at": _iso(ahora),
            "exit_price": precio_salida,
            "exit_candle_close_time": _iso(datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)),
            "settlement_resolution": resolucion,
            "settlement_offset_seconds": offset_s,
            "realized_gross_bps": bruto_bps,
            "realized_net_bps_if_cost_known": neto_bps,
            "prediction_error_bps": (bruto_bps - float(edge)) if edge is not None else None,
            "settlement_status": "OK",
        })
        maduras += 1
    return maduras


def _resumen(estado: dict) -> dict:
    obs = estado["observations"]
    maduras = [o for o in obs if o.get("settled")]
    aprobadas = [o for o in obs if o.get("would_trade_05a")]
    aprobadas_maduras = [o for o in maduras if o.get("would_trade_05a")]
    rechazadas_maduras = [o for o in maduras if not o.get("would_trade_05a")]

    def media(xs):
        vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
        return (sum(vals) / len(vals)) if vals else None

    netos_aprobados = [o.get("realized_net_bps_if_cost_known") for o in aprobadas_maduras]
    netos_validos = [float(x) for x in netos_aprobados if x is not None]
    return {
        "phase": "05A",
        "mode": "SHADOW",
        "generated_at": _iso(datetime.now(timezone.utc)),
        "parameter_changes_from_probe": False,
        "orders_executed": False,
        "llm_called": False,
        "total_observations": len(obs),
        "matured_observations": len(maduras),
        "pending_observations": len(obs) - len(maduras),
        "approved_observations": len(aprobadas),
        "approved_matured": len(aprobadas_maduras),
        "approved_realized_net_mean_bps": media(netos_validos),
        "approved_realized_net_positive_rate": (
            sum(1 for x in netos_validos if x > 0) / len(netos_validos)
            if netos_validos else None
        ),
        "rejected_matured": len(rechazadas_maduras),
        "rejected_realized_gross_mean_bps": media(
            [o.get("realized_gross_bps") for o in rechazadas_maduras]
        ),
        "signal_states": {
            k: sum(1 for o in obs if o.get("edge_state") == k)
            for k in sorted({o.get("edge_state") for o in obs if o.get("edge_state")})
        },
        "decision_states": {
            k: sum(1 for o in obs if o.get("decision_state") == k)
            for k in sorted({o.get("decision_state") for o in obs if o.get("decision_state")})
        },
    }


def _nueva_observacion(estado: dict, binance: BinanceConnector, ahora: datetime) -> int:
    bucket = _bucket_4h(ahora)
    if any(o.get("run_bucket") == bucket for o in estado["observations"]):
        return 0

    activos, _balances, _symbols_info, costes_cuenta = get_available_assets(
        incluir_costes_cuenta=True
    )
    fee = costes_cuenta.get("fee_taker_bps_por_lado")
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
    notionals = {
        a["symbol"]: motor.limite_compra(
            capital_disponible=capital, estado=estado_riesgo, symbol=a["symbol"]
        ).quote_permitido
        for a in top20 if not a.get("_position_detected")
    }

    resumen_05a = ResumenFiltroRentabilidad()
    _filtrados, evaluaciones = filtrar_compras_rentables(
        top20,
        metricas,
        fee_taker_bps_por_lado=fee,
        notional_por_symbol=notionals,
        binance=binance,
        resumen=resumen_05a,
        ahora_ms=int(ahora.timestamp() * 1000),
    )

    agregadas = 0
    for rank, activo in enumerate(top20[:FINALISTAS_MAX], start=1):
        sym = activo.get("symbol")
        if not sym or sym not in evaluaciones or sym not in snapshot:
            continue
        serial = _serializar_evaluacion(evaluaciones[sym])
        edge = serial.get("edge") or {}
        rent = serial.get("rentabilidad") or {}
        coste_total = rent.get("coste_total_bps")
        obs = {
            "id": f"{bucket}|{rank}|{sym}",
            "run_bucket": bucket,
            "observed_at": _iso(ahora),
            "due_at": _iso(ahora + timedelta(hours=HORIZONTE_H)),
            "symbol": sym,
            "scanner_rank": rank,
            "entry_price": float(snapshot[sym]),
            "notional_usd": notionals.get(sym),
            "fee_taker_bps_por_lado": fee,
            "fee_source": costes_cuenta.get("fuente_fee"),
            "edge_state": edge.get("estado"),
            "predicted_edge_bruto_bps": edge.get("edge_bruto_bps"),
            "edge_samples": edge.get("muestras"),
            "momentum_6h_bps": edge.get("momentum_6h_bps"),
            "momentum_24h_bps": edge.get("momentum_24h_bps"),
            "decision_state": serial.get("estado"),
            "decision_reason": serial.get("motivo"),
            "would_trade_05a": bool(rent.get("apta", False)),
            "predicted_edge_net_bps": rent.get("edge_neto_bps"),
            "known_cost_total_bps": coste_total,
            "evaluation": serial,
            "settled": False,
            "settlement_status": "PENDING",
        }
        estado["observations"].append(obs)
        agregadas += 1

    estado["last_scanner_summary"] = resumen_scanner.linea(requests=0)
    estado["last_profitability_summary"] = resumen_05a.linea()
    estado["last_run_at"] = _iso(ahora)
    estado["last_run_bucket"] = bucket
    return agregadas


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05A shadow solo puede ejecutarse en PAPER; LIVE bloqueado")

    ahora = datetime.now(timezone.utc)
    estado = _cargar_estado()
    binance = BinanceConnector()

    maduras = _madurar(estado, binance, ahora)
    nuevas = _nueva_observacion(estado, binance, ahora)
    resumen = _resumen(estado)

    _guardar_json(ESTADO_PATH, estado)
    _guardar_json(RESUMEN_PATH, resumen)

    print(f"[SHADOW-05A] nuevas={nuevas} maduras_ahora={maduras} "
          f"total={resumen['total_observations']} maduras={resumen['matured_observations']} "
          f"aprobadas={resumen['approved_observations']}")
    print(json.dumps(resumen, indent=2, sort_keys=True))
    print(f"state={ESTADO_PATH.relative_to(RAIZ_REPO)}")
    print(f"summary={RESUMEN_PATH.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
