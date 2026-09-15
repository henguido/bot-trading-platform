"""Shadow longitudinal 05C: mide si el ranking del scanner aporta alpha.

Compara, en el MISMO snapshot y con horizonte fijo de 4h:
- TOP: ranks 1..5 del scanner;
- CONTROL: ranks 16..20 del mismo scanner.

No cambia el scanner, no llama LLM y no ejecuta ordenes. El objetivo es aislar
si ordenar candidatos por el score actual mejora el retorno futuro respecto a
candidatos que pasaron los mismos filtros pero quedaron al final del Top-20.

El estado y resumen son solo locales en artifacts/. LIVE queda bloqueado.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from backend import scanner
from backend.config import settings
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.costes import spread_bps_desde_bid_ask
from backend.utils.asset_collector import get_available_assets

STATE = RAIZ_REPO / "artifacts" / "scanner-alpha-shadow-05c-state.json"
SUMMARY = RAIZ_REPO / "artifacts" / "scanner-alpha-shadow-05c-summary.json"
HORIZONTE_H = 4
TOP_RANKS = set(range(1, 6))
CONTROL_RANKS = set(range(16, 21))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(v: str) -> datetime:
    return datetime.fromisoformat(v).astimezone(timezone.utc)


def _bucket(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    h = (dt.hour // HORIZONTE_H) * HORIZONTE_H
    return dt.replace(hour=h, minute=0, second=0, microsecond=0).isoformat()


def _load() -> dict:
    if not STATE.exists():
        return {"phase": "05C", "mode": "SHADOW", "observations": []}
    data = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise RuntimeError("estado 05C invalido")
    return data


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _precio_horizonte(binance: BinanceConnector, symbol: str, due_ms: int):
    for interval, max_offset in (("1m", 60_000), ("5m", 300_000), ("1h", 3_600_000)):
        filas = binance.get_recent_klines(symbol, interval=interval, limit=1000)
        for fila in filas or ():
            try:
                open_ms = int(fila[0])
                close = float(fila[4])
                close_ms = int(fila[6])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(close) or close <= 0:
                continue
            if open_ms <= due_ms <= close_ms and abs(close_ms - due_ms) <= max_offset:
                return close, close_ms, interval, abs(close_ms - due_ms) / 1000.0
    return None


def _madurar(state: dict, binance: BinanceConnector, now: datetime) -> int:
    matured = 0
    for obs in state["observations"]:
        if obs.get("settled"):
            continue
        due = _parse(obs["due_at"])
        if due > now:
            continue
        salida = _precio_horizonte(binance, obs["symbol"], int(due.timestamp() * 1000))
        if salida is None:
            obs["settlement_status"] = "PRECIO_HORIZONTE_NO_DISPONIBLE"
            continue
        px, close_ms, resolution, offset_s = salida
        bruto = (px / float(obs["entry_price"]) - 1.0) * 10_000.0
        floor_cost = obs.get("known_cost_floor_bps")
        obs.update({
            "settled": True,
            "settlement_status": "OK",
            "settled_at": _iso(now),
            "exit_price": px,
            "exit_candle_close_time": _iso(datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)),
            "settlement_resolution": resolution,
            "settlement_offset_seconds": offset_s,
            "realized_gross_bps": bruto,
            "realized_net_bps_vs_known_cost_floor": (
                bruto - float(floor_cost) if floor_cost is not None else None
            ),
        })
        matured += 1
    return matured


def _stats(xs):
    vals = sorted(float(x) for x in xs if x is not None and math.isfinite(float(x)))
    if not vals:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None}
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    return {
        "n": n,
        "mean": sum(vals) / n,
        "median": med,
        "positive_rate": sum(1 for x in vals if x > 0) / n,
    }


def _summary(state: dict) -> dict:
    settled = [o for o in state["observations"] if o.get("settled")]
    top = [o for o in settled if o.get("group") == "TOP"]
    control = [o for o in settled if o.get("group") == "CONTROL"]

    top_g = _stats([o.get("realized_gross_bps") for o in top])
    ctl_g = _stats([o.get("realized_gross_bps") for o in control])
    top_n = _stats([o.get("realized_net_bps_vs_known_cost_floor") for o in top])
    ctl_n = _stats([o.get("realized_net_bps_vs_known_cost_floor") for o in control])

    # Alpha por bucket: diferencia entre la media TOP y CONTROL en el mismo run.
    deltas = []
    buckets = sorted({o.get("run_bucket") for o in settled if o.get("run_bucket")})
    for b in buckets:
        t = [float(o["realized_gross_bps"]) for o in top if o.get("run_bucket") == b]
        c = [float(o["realized_gross_bps"]) for o in control if o.get("run_bucket") == b]
        if t and c:
            deltas.append(sum(t) / len(t) - sum(c) / len(c))

    alpha = _stats(deltas)
    return {
        "phase": "05C",
        "mode": "SHADOW",
        "generated_at": _iso(datetime.now(timezone.utc)),
        "orders_executed": False,
        "llm_called": False,
        "scanner_modified": False,
        "horizon_h": HORIZONTE_H,
        "comparison": "scanner ranks 1-5 vs ranks 16-20",
        "total_observations": len(state["observations"]),
        "matured_observations": len(settled),
        "top_gross": top_g,
        "control_gross": ctl_g,
        "top_net_vs_known_cost_floor": top_n,
        "control_net_vs_known_cost_floor": ctl_n,
        "bucket_alpha_top_minus_control_bps": alpha,
        "interpretation": (
            "El coste neto es un piso conocido: fee taker round-trip + spread de entrada; "
            "omite slippage futuro. La prueba primaria de 05C es alpha bruto TOP-CONTROL."
        ),
    }


def _new_snapshot(state: dict, binance: BinanceConnector, now: datetime) -> int:
    bucket = _bucket(now)
    if any(o.get("run_bucket") == bucket for o in state["observations"]):
        return 0

    activos, _balances, _symbols_info, costes = get_available_assets(incluir_costes_cuenta=True)
    fee = costes.get("fee_taker_bps_por_lado")
    snapshot = binance.get_price_snapshot()
    metricas = binance.get_market_metrics()

    entrada = []
    for a in activos:
        if a.get("type") != "crypto":
            continue
        sym = a.get("symbol")
        px = snapshot.get(sym)
        if px is None:
            continue
        try:
            px = float(px)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(px) or px <= 0:
            continue
        entrada.append({
            "symbol": sym,
            "price": px,
            "position_quantity": 0.0,
            "average_price": None,
            "last_movement": None,
            "last_sell_price": None,
            "_balance_detected": False,
            "_position_detected": False,
        })

    resumen_scanner = scanner.ResumenScanner()
    top20 = scanner.aplicar(entrada, metricas, top_n=20, resumen=resumen_scanner)
    added = 0
    for rank, activo in enumerate(top20, start=1):
        if rank not in TOP_RANKS and rank not in CONTROL_RANKS:
            continue
        sym = activo.get("symbol")
        if not sym or sym not in snapshot:
            continue
        m = metricas.get(sym) or {}
        spread = None
        try:
            s = spread_bps_desde_bid_ask(m.get("bidPrice"), m.get("askPrice"))
            spread = float(s) if s is not None else None
        except ValueError:
            pass
        cost_floor = None
        if fee is not None and spread is not None:
            cost_floor = 2.0 * float(fee) + spread
        state["observations"].append({
            "id": f"{bucket}|{rank}|{sym}",
            "run_bucket": bucket,
            "observed_at": _iso(now),
            "due_at": _iso(now + timedelta(hours=HORIZONTE_H)),
            "group": "TOP" if rank in TOP_RANKS else "CONTROL",
            "scanner_rank": rank,
            "symbol": sym,
            "entry_price": float(snapshot[sym]),
            "fee_taker_bps_por_lado": fee,
            "entry_spread_bps": spread,
            "known_cost_floor_bps": cost_floor,
            "settled": False,
            "settlement_status": "PENDING",
        })
        added += 1

    state["last_run_at"] = _iso(now)
    state["last_run_bucket"] = bucket
    state["last_scanner_summary"] = resumen_scanner.linea(requests=0)
    return added


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05C shadow solo puede ejecutarse en PAPER; LIVE bloqueado")

    now = datetime.now(timezone.utc)
    state = _load()
    binance = BinanceConnector()
    matured = _madurar(state, binance, now)
    added = _new_snapshot(state, binance, now)
    summary = _summary(state)

    _save(STATE, state)
    _save(SUMMARY, summary)
    print(f"[SHADOW-05C] nuevas={added} maduras_ahora={matured} "
          f"total={summary['total_observations']} maduras={summary['matured_observations']}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"state={STATE.relative_to(RAIZ_REPO)}")
    print(f"summary={SUMMARY.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
