"""Shadow 05D: atribucion del score del scanner contra retorno futuro 4h.

No modifica pesos, no llama LLM y no ejecuta ordenes. Cada bucket de 4h:
1) madura observaciones previas con precio 4h despues;
2) reconstruye el universo elegible con el snapshot actual;
3) guarda los 20 candidatos seleccionados, score y cinco componentes;
4) resume correlacion de score/features con retorno bruto futuro.

Objetivo: saber que componentes del ranking aportan o destruyen alpha antes de
cambiar pesos. Los parametros del scanner quedan congelados durante la medicion.
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
from backend.utils.asset_collector import get_available_assets

ESTADO_PATH = RAIZ_REPO / "artifacts" / "scanner-attribution-shadow-05d-state.json"
RESUMEN_PATH = RAIZ_REPO / "artifacts" / "scanner-attribution-shadow-05d-summary.json"
HORIZONTE_H = 4
TOP_N = 20
FEATURES = ("estrechez", "recorrido", "liquidez", "actividad", "momentum")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _bucket_4h(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    h = (dt.hour // HORIZONTE_H) * HORIZONTE_H
    return dt.replace(hour=h, minute=0, second=0, microsecond=0).isoformat()


def _guardar(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _cargar() -> dict:
    if not ESTADO_PATH.exists():
        return {"phase": "05D", "mode": "SHADOW", "created_at": _iso(datetime.now(timezone.utc)), "observations": []}
    data = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise RuntimeError("estado 05D invalido")
    return data


def _precio_horizonte(binance: BinanceConnector, symbol: str, due_ms: int):
    for interval, max_offset_ms in (("1m", 60_000), ("5m", 300_000), ("1h", 3_600_000)):
        filas = binance.get_recent_klines(symbol, interval=interval, limit=1000)
        for fila in filas or ():
            try:
                open_ms = int(fila[0]); close = float(fila[4]); close_ms = int(fila[6])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(close) or close <= 0:
                continue
            if open_ms <= due_ms <= close_ms and abs(close_ms - due_ms) <= max_offset_ms:
                return close, close_ms, interval
    return None


def _madurar(estado: dict, binance: BinanceConnector, ahora: datetime) -> int:
    ahora_ms = int(ahora.timestamp() * 1000)
    n = 0
    for o in estado["observations"]:
        if o.get("settled"):
            continue
        due = _parse_iso(o["due_at"])
        due_ms = int(due.timestamp() * 1000)
        if due_ms > ahora_ms:
            continue
        salida = _precio_horizonte(binance, o["symbol"], due_ms)
        if salida is None:
            o["settlement_status"] = "PRECIO_HORIZONTE_NO_DISPONIBLE"
            continue
        px, close_ms, resolution = salida
        bruto = (px / float(o["entry_price"]) - 1.0) * 10_000.0
        o.update({
            "settled": True,
            "settlement_status": "OK",
            "settled_at": _iso(ahora),
            "exit_price": px,
            "exit_candle_close_time": _iso(datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)),
            "settlement_resolution": resolution,
            "realized_gross_bps": bruto,
        })
        n += 1
    return n


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


def _resumen(estado: dict) -> dict:
    maduras = [o for o in estado["observations"] if o.get("settled") and o.get("settlement_status") == "OK"]
    retornos = [float(o["realized_gross_bps"]) for o in maduras]

    def corr(campo):
        xs = [float(o[campo]) for o in maduras]
        return spearman(xs, retornos) if maduras else None

    feat_corr = {}
    for f in FEATURES:
        xs = [float(o["features"][f]) for o in maduras]
        feat_corr[f] = spearman(xs, retornos) if maduras else None

    por_quintil = {}
    if maduras:
        orden = sorted(maduras, key=lambda o: float(o["score"]), reverse=True)
        q = max(1, math.ceil(len(orden) / 5))
        for i in range(5):
            grupo = orden[i*q:(i+1)*q]
            vals = [float(o["realized_gross_bps"]) for o in grupo]
            por_quintil[str(i + 1)] = {
                "n": len(vals),
                "mean_gross_bps": (sum(vals) / len(vals)) if vals else None,
            }

    return {
        "phase": "05D",
        "mode": "SHADOW",
        "generated_at": _iso(datetime.now(timezone.utc)),
        "orders_executed": False,
        "llm_called": False,
        "scanner_modified": False,
        "weights_frozen": dict(scanner.PESOS),
        "horizon_h": HORIZONTE_H,
        "total_observations": len(estado["observations"]),
        "matured_observations": len(maduras),
        "spearman_score_vs_future_return": corr("score"),
        "spearman_feature_vs_future_return": feat_corr,
        "score_quintiles": por_quintil,
        "interpretation": "Correlaciones descriptivas OOS. No cambian pesos automaticamente ni autorizan trading.",
    }


def _observar(estado: dict, binance: BinanceConnector, ahora: datetime) -> int:
    bucket = _bucket_4h(ahora)
    if any(o.get("run_bucket") == bucket for o in estado["observations"]):
        return 0

    activos, _balances, _symbols_info = get_available_assets()
    snapshot = binance.get_price_snapshot()
    metricas_raw = binance.get_market_metrics()

    metricas = []
    for a in activos:
        if a.get("type") != "crypto":
            continue
        sym = a.get("symbol")
        if sym not in snapshot:
            continue
        m = scanner.leer_metricas(sym, metricas_raw.get(sym))
        if scanner.evaluar_filtros(m) == scanner.CANDIDATO:
            metricas.append(m)

    candidatos = scanner.puntuar(metricas)[:TOP_N]
    agregadas = 0
    for rank, c in enumerate(candidatos, start=1):
        entry = float(snapshot.get(c.symbol, c.metricas.precio))
        estado["observations"].append({
            "id": f"{bucket}|{rank}|{c.symbol}",
            "run_bucket": bucket,
            "observed_at": _iso(ahora),
            "due_at": _iso(ahora + timedelta(hours=HORIZONTE_H)),
            "symbol": c.symbol,
            "rank": rank,
            "entry_price": entry,
            "score": float(c.score),
            "features": {k: float(c.features[k]) for k in FEATURES},
            "raw_metrics": {
                "spread_bps": float(c.metricas.spread_bps),
                "quote_volume": float(c.metricas.quote_volume),
                "trades": float(c.metricas.trades),
                "rango": float(c.metricas.rango),
                "cambio_pct": float(c.metricas.cambio_pct),
            },
            "settled": False,
            "settlement_status": "PENDING",
        })
        agregadas += 1
    estado["last_run_at"] = _iso(ahora)
    estado["last_run_bucket"] = bucket
    return agregadas


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05D solo puede ejecutarse en PAPER; LIVE bloqueado")
    ahora = datetime.now(timezone.utc)
    estado = _cargar()
    binance = BinanceConnector()
    maduras = _madurar(estado, binance, ahora)
    nuevas = _observar(estado, binance, ahora)
    resumen = _resumen(estado)
    _guardar(ESTADO_PATH, estado)
    _guardar(RESUMEN_PATH, resumen)
    print(f"[SHADOW-05D] nuevas={nuevas} maduras_ahora={maduras} total={resumen['total_observations']} maduras={resumen['matured_observations']}")
    print(json.dumps(resumen, indent=2, sort_keys=True))
    print(f"summary={RESUMEN_PATH.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
