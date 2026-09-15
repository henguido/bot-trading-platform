"""Shadow unificado BOT 2.0-05I: alpha + atribucion sobre UN MISMO snapshot.

Sustituye para observaciones nuevas la comparacion cruzada 05C/05D, que hacia
capturas independientes. Cada bucket de 4h:
1) madura observaciones anteriores;
2) toma UNA sola captura de mercado;
3) construye UN Top-20 del scanner;
4) guarda rank, score, features, precio y piso conocido de costes;
5) resume alpha ranks 1-5 vs 16-20 y atribucion score/features.

PAPER solamente. Sin LLM, BD ni ordenes. No cambia pesos ni scanner.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from backend import scanner
from backend.config import settings
from backend.connectors.crypto.binance_public_market import BinancePublicMarketData
from backend.utils.asset_collector import get_available_assets
from backend.economia.fee_verificada import fee_taker_manual_verificada

STATE = RAIZ_REPO / "artifacts" / "scanner-unified-shadow-05i-state.json"
SUMMARY = RAIZ_REPO / "artifacts" / "scanner-unified-shadow-05i-summary.json"
HORIZONTE_H = 4
TOP_N = 20
FEATURES = ("estrechez", "recorrido", "liquidez", "actividad", "momentum")
TOP_RANKS = set(range(1, 6))
CONTROL_RANKS = set(range(16, 21))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _bucket(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    h = (dt.hour // HORIZONTE_H) * HORIZONTE_H
    return dt.replace(hour=h, minute=0, second=0, microsecond=0).isoformat()


def _guardar(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _cargar() -> dict:
    if not STATE.exists():
        return {"phase": "05I", "mode": "SHADOW", "observations": []}
    data = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise RuntimeError("estado 05I invalido")
    return data


def _precio_horizonte(binance: BinancePublicMarketData, symbol: str, due_ms: int):
    for interval, max_offset in (("1m", 60_000), ("5m", 300_000), ("1h", 3_600_000)):
        filas = binance.get_recent_klines(symbol, interval=interval, limit=1000)
        for fila in filas or ():
            try:
                open_ms = int(fila[0]); close = float(fila[4]); close_ms = int(fila[6])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(close) or close <= 0:
                continue
            if open_ms <= due_ms <= close_ms and abs(close_ms - due_ms) <= max_offset:
                return close, close_ms, interval, abs(close_ms - due_ms) / 1000.0
    return None


def _madurar(state: dict, binance: BinancePublicMarketData, now: datetime) -> int:
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
        floor = obs.get("known_cost_floor_bps")
        obs.update({
            "settled": True,
            "settlement_status": "OK",
            "settled_at": _iso(now),
            "exit_price": px,
            "exit_candle_close_time": _iso(datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)),
            "settlement_resolution": resolution,
            "settlement_offset_seconds": offset_s,
            "realized_gross_bps": bruto,
            "realized_net_bps_vs_known_cost_floor": bruto - float(floor) if floor is not None else None,
        })
        matured += 1
    return matured


def _rank_promedio(xs):
    pares = sorted(enumerate(xs), key=lambda p: p[1])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(pares):
        j = i
        while j + 1 < len(pares) and pares[j + 1][1] == pares[i][1]:
            j += 1
        r = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[pares[k][0]] = r
        i = j + 1
    return ranks


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    dx = [x - mx for x in xs]; dy = [y - my for y in ys]
    den = math.sqrt(sum(x*x for x in dx) * sum(y*y for y in dy))
    if den == 0:
        return None
    return sum(a*b for a, b in zip(dx, dy)) / den


def spearman(xs, ys):
    if len(xs) != len(ys):
        raise ValueError("longitudes distintas")
    if len(xs) < 3:
        return None
    return _pearson(_rank_promedio(list(xs)), _rank_promedio(list(ys)))


def _stats(xs):
    vals = sorted(float(x) for x in xs if x is not None and math.isfinite(float(x)))
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "positive_rate": None}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
        "positive_rate": sum(1 for x in vals if x > 0) / len(vals),
    }


def construir_resumen(state: dict) -> dict:
    settled = [o for o in state.get("observations", []) if o.get("settled") and o.get("settlement_status") == "OK"]
    top = [o for o in settled if int(o["rank"]) in TOP_RANKS]
    control = [o for o in settled if int(o["rank"]) in CONTROL_RANKS]

    buckets = []
    bucket_ids = sorted({o.get("run_bucket") for o in settled if o.get("run_bucket")})
    for b in bucket_ids:
        group = [o for o in settled if o.get("run_bucket") == b]
        if len(group) < TOP_N:
            continue
        tg = [float(o["realized_gross_bps"]) for o in group if int(o["rank"]) in TOP_RANKS]
        cg = [float(o["realized_gross_bps"]) for o in group if int(o["rank"]) in CONTROL_RANKS]
        returns = [float(o["realized_gross_bps"]) for o in group]
        scores = [float(o["score"]) for o in group]
        feat_corr = {
            f: spearman([float(o["features"][f]) for o in group], returns)
            for f in FEATURES
        }
        buckets.append({
            "run_bucket": b,
            "observations": len(group),
            "top_1_5_gross_mean_bps": sum(tg) / len(tg),
            "control_16_20_gross_mean_bps": sum(cg) / len(cg),
            "alpha_top_minus_control_bps": sum(tg) / len(tg) - sum(cg) / len(cg),
            "spearman_score_vs_future_return": spearman(scores, returns),
            "spearman_feature_vs_future_return": feat_corr,
        })

    quintiles = {}
    if settled:
        orden = sorted(settled, key=lambda o: float(o["score"]), reverse=True)
        q = max(1, math.ceil(len(orden) / 5))
        for i in range(5):
            grupo = orden[i*q:(i+1)*q]
            vals = [float(o["realized_gross_bps"]) for o in grupo]
            quintiles[str(i + 1)] = {"n": len(vals), "mean_gross_bps": sum(vals) / len(vals) if vals else None}

    bucket_feature = {
        f: _stats([b["spearman_feature_vs_future_return"].get(f) for b in buckets])
        for f in FEATURES
    }

    return {
        "phase": "05I",
        "mode": "SHADOW",
        "generated_at": _iso(datetime.now(timezone.utc)),
        "orders_executed": False,
        "llm_called": False,
        "scanner_modified": False,
        "single_snapshot_per_bucket": True,
        "market_data_source": "https://data-api.binance.vision",
        "weights_frozen": dict(scanner.PESOS),
        "horizon_h": HORIZONTE_H,
        "total_observations": len(state.get("observations", [])),
        "matured_observations": len(settled),
        "complete_buckets": len(buckets),
        "top_gross": _stats([o.get("realized_gross_bps") for o in top]),
        "control_gross": _stats([o.get("realized_gross_bps") for o in control]),
        "top_net_vs_known_cost_floor": _stats([o.get("realized_net_bps_vs_known_cost_floor") for o in top]),
        "control_net_vs_known_cost_floor": _stats([o.get("realized_net_bps_vs_known_cost_floor") for o in control]),
        "bucket_alpha_top_minus_control_bps": _stats([b["alpha_top_minus_control_bps"] for b in buckets]),
        "bucket_score_spearman": _stats([b["spearman_score_vs_future_return"] for b in buckets]),
        "bucket_feature_spearman": bucket_feature,
        "score_quintiles": quintiles,
        "buckets": buckets,
        "interpretation": "Alpha y atribucion provienen del mismo Top-20 capturado una sola vez por bucket; no cambia pesos ni autoriza trading.",
    }


def _fee_taker_si_disponible(now=None):
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        _activos, _balances, _symbols_info, costes = get_available_assets(
            incluir_costes_cuenta=True
        )
        fee = costes.get("fee_taker_bps_por_lado")
        if fee is not None:
            return fee

    manual = fee_taker_manual_verificada(now)
    return manual["fee_taker_bps_por_lado"] if manual else None


def _observar(state: dict, binance: BinancePublicMarketData, now: datetime) -> int:
    bucket = _bucket(now)
    if any(o.get("run_bucket") == bucket for o in state["observations"]):
        return 0

    symbols_info = binance.get_exchange_symbols_info()
    snapshot = binance.get_price_snapshot()
    metricas_raw = binance.get_market_metrics()
    if not symbols_info or not snapshot or not metricas_raw:
        return 0

    fee = _fee_taker_si_disponible(now)
    activos = [
        fila for fila in symbols_info.values()
        if fila.get("quoteAsset") == "USDT"
        and fila.get("status") == "TRADING"
        and fila.get("isSpotTradingAllowed")
    ]

    metricas = []
    for a in activos:
        sym = a.get("symbol")
        if sym not in snapshot:
            continue
        m = scanner.leer_metricas(sym, metricas_raw.get(sym))
        if scanner.evaluar_filtros(m) == scanner.CANDIDATO:
            metricas.append(m)

    candidatos = scanner.puntuar(metricas)[:TOP_N]
    if len(candidatos) < TOP_N:
        return 0

    added = 0
    for rank, c in enumerate(candidatos, start=1):
        entry = float(snapshot.get(c.symbol, c.metricas.precio))
        spread = float(c.metricas.spread_bps)
        floor = 2.0 * float(fee) + spread if fee is not None else None
        state["observations"].append({
            "id": f"{bucket}|{rank}|{c.symbol}",
            "run_bucket": bucket,
            "observed_at": _iso(now),
            "due_at": _iso(now + timedelta(hours=HORIZONTE_H)),
            "symbol": c.symbol,
            "rank": rank,
            "entry_price": entry,
            "score": float(c.score),
            "features": {k: float(c.features[k]) for k in FEATURES},
            "entry_spread_bps": spread,
            "fee_taker_bps_por_lado": fee,
            "known_cost_floor_bps": floor,
            "settled": False,
            "settlement_status": "PENDING",
        })
        added += 1

    state["last_run_at"] = _iso(now)
    state["last_run_bucket"] = bucket
    return added


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05I solo puede ejecutarse en PAPER; LIVE bloqueado")
    now = datetime.now(timezone.utc)
    state = _cargar()
    binance = BinancePublicMarketData()
    matured = _madurar(state, binance, now)
    added = _observar(state, binance, now)
    summary = construir_resumen(state)
    _guardar(STATE, state)
    _guardar(SUMMARY, summary)
    print(f"[SHADOW-05I] nuevas={added} maduras_ahora={matured} total={summary['total_observations']} maduras={summary['matured_observations']} buckets={summary['complete_buckets']}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"state={STATE.relative_to(RAIZ_REPO)}")
    print(f"summary={SUMMARY.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
