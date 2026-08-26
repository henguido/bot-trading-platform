"""Shadow de ejecución prospectiva BOT 2.0-05K.

Convierte los rankings 05I/05J en dos portafolios virtuales independientes y
mide P&L en USDT con el mismo modelo de ejecución PAPER:

- solo usa un bucket 05I recién capturado; nunca hace backfill;
- BASE_05I toma ranks 1-5 del scanner congelado;
- CHALLENGER_05J rerankea el mismo Top-20 con los pesos OOS congelados;
- MotorRiesgo calcula el tamaño, no este script;
- entrada y salida usan profundidad pública real, VWAP, slippage y fee conocida;
- LOT_SIZE y NOTIONAL se toman del exchangeInfo público actual y son fail-closed;
- horizonte objetivo: el `due_at` ya congelado por 05I (~4 h);
- sin LLM, sin BD, sin órdenes y sin tocar pesos del scanner.

Este shadow responde una pregunta distinta de 05I: no "¿el Top-5 supera al
control?", sino "¿qué P&L habría producido una cartera PAPER de 500 USDT bajo
las restricciones reales del bot?".
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from backend.app.services.ordenes import Lado
from backend.config import settings
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.ejecucion_paper import calcular_fill_compra, calcular_fill_venta
from backend.risk import elegibilidad, reloj
from backend.risk.estado import EstadoRiesgo, Posicion
from backend.risk.motor import MotorRiesgo, PropuestaOperacion
from scripts.analyze_scanner_challenger_05j import CHALLENGER_WEIGHTS

SOURCE_05I = RAIZ_REPO / "artifacts" / "scanner-unified-shadow-05i-state.json"
STATE = RAIZ_REPO / "artifacts" / "strategy-execution-shadow-05k-state.json"
SUMMARY = RAIZ_REPO / "artifacts" / "strategy-execution-shadow-05k-summary.json"

PORTFOLIO_BASE = "BASE_05I"
PORTFOLIO_CHALLENGER = "CHALLENGER_05J"
PORTFOLIOS = (PORTFOLIO_BASE, PORTFOLIO_CHALLENGER)
TOP_N = 5
MAX_ENTRY_DELAY_SECONDS = 10 * 60
ORDER_BOOK_LIMIT = 100
_BPS = Decimal("10000")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _guardar(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _nuevo_portafolio(capital: float) -> dict:
    return {
        "initial_capital_usd": capital,
        "capital_usd": capital,
        "open_positions": [],
        "closed_trades": [],
        "skipped_entries": [],
    }


def nuevo_estado(capital: float | None = None) -> dict:
    inicial = float(settings.INITIAL_CAPITAL_USD if capital is None else capital)
    if not math.isfinite(inicial) or inicial <= 0:
        raise ValueError("capital inicial 05K invalido")
    return {
        "phase": "05K",
        "mode": "SHADOW_EXECUTION",
        "created_at": _iso(datetime.now(timezone.utc)),
        "initial_capital_usd": inicial,
        "processed_buckets": [],
        "ignored_stale_buckets": [],
        "orderbook_calls": 0,
        "exchange_info_calls": 0,
        "portfolios": {
            PORTFOLIO_BASE: _nuevo_portafolio(inicial),
            PORTFOLIO_CHALLENGER: _nuevo_portafolio(inicial),
        },
    }


def cargar_estado() -> dict:
    if not STATE.exists():
        return nuevo_estado()
    data = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("portfolios"), dict):
        raise RuntimeError("estado 05K invalido")
    for nombre in PORTFOLIOS:
        if nombre not in data["portfolios"]:
            raise RuntimeError(f"estado 05K carece de {nombre}")
    # Compatibilidad con estados 05K creados antes de modelar exchangeInfo.
    data.setdefault("exchange_info_calls", 0)
    return data


def cargar_05i() -> dict:
    if not SOURCE_05I.exists():
        raise SystemExit(f"No existe {SOURCE_05I}")
    data = json.loads(SOURCE_05I.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise RuntimeError("estado 05I invalido para 05K")
    return data


def _score_challenger(obs: dict) -> float:
    features = obs.get("features") or {}
    return sum(float(features[k]) * float(CHALLENGER_WEIGHTS[k])
               for k in CHALLENGER_WEIGHTS)


def _selecciones(group: list[dict]) -> dict[str, list[dict]]:
    if len(group) != 20:
        return {}
    base = sorted(group, key=lambda o: int(o["rank"]))[:TOP_N]
    challenger = sorted(
        group,
        key=lambda o: (-_score_challenger(o), str(o["symbol"])),
    )[:TOP_N]
    return {
        PORTFOLIO_BASE: base,
        PORTFOLIO_CHALLENGER: challenger,
    }


def _pnl_dia(portfolio: dict, now: datetime) -> tuple[float, int]:
    dia = reloj.dia_de_riesgo(now)
    inicio, fin = reloj.ventana_utc(dia)
    pnl = 0.0
    n = 0
    for trade in portfolio.get("closed_trades", []):
        cerrado = _parse(trade["closed_at"]).replace(tzinfo=None)
        if inicio <= cerrado < fin:
            pnl += float(trade["pnl_realizado_usd"])
            n += 1
    return pnl, n


def _estado_riesgo_virtual(portfolio: dict, now: datetime) -> EstadoRiesgo:
    agrupadas = defaultdict(lambda: {"cantidad": 0.0, "coste": 0.0})
    for pos in portfolio.get("open_positions", []):
        qty = float(pos["base_quantity"])
        coste = float(pos["entry_quote_net"])
        g = agrupadas[pos["symbol"]]
        g["cantidad"] += qty
        g["coste"] += coste
    posiciones = {
        symbol: Posicion(
            cantidad=v["cantidad"],
            coste_medio=v["coste"] / v["cantidad"],
        )
        for symbol, v in agrupadas.items() if v["cantidad"] > 0
    }
    pnl_dia, n_dia = _pnl_dia(portfolio, now)
    return EstadoRiesgo(
        dia=reloj.dia_de_riesgo(now),
        posiciones=posiciones,
        pnl_realizado_dia=pnl_dia,
        operaciones_dia=n_dia,
        ordenes_pendientes=0,
    )


def _book(binance, cache: dict, symbol: str, state: dict):
    if symbol not in cache:
        cache[symbol] = binance.get_order_book(symbol, limit=ORDER_BOOK_LIMIT)
        state["orderbook_calls"] = int(state.get("orderbook_calls", 0)) + 1
    return cache[symbol]


def _exchange_info(binance, cache: dict, state: dict) -> dict:
    """Carga exchangeInfo una sola vez y solo si una entrada/salida lo necesita."""
    if "symbols" not in cache:
        cache["symbols"] = binance.get_exchange_symbols_info()
        state["exchange_info_calls"] = int(state.get("exchange_info_calls", 0)) + 1
    data = cache["symbols"]
    return data if isinstance(data, dict) else {}


def _filtros(binance, cache: dict, state: dict, symbol: str):
    info = _exchange_info(binance, cache, state).get(symbol)
    return elegibilidad.leer_filtros(info)


def _kwargs_filtros(filtros) -> dict:
    return {
        "step_size": filtros.step_size,
        "min_qty": filtros.min_qty,
        "max_qty": filtros.max_qty,
        "min_notional": filtros.min_notional,
    }


def _cerrar_vencidas(state: dict, binance, now: datetime, cache_books: dict,
                     cache_exchange: dict) -> int:
    cerradas = 0
    for nombre in PORTFOLIOS:
        portfolio = state["portfolios"][nombre]
        siguen = []
        for pos in portfolio.get("open_positions", []):
            if _parse(pos["due_at"]) > now:
                siguen.append(pos)
                continue

            filtros = _filtros(binance, cache_exchange, state, pos["symbol"])
            if filtros is None:
                pos["last_exit_error"] = "FILTROS_EXCHANGE_NO_DISPONIBLES"
                siguen.append(pos)
                continue

            libro = _book(binance, cache_books, pos["symbol"], state)
            try:
                fill = calcular_fill_venta(
                    order_book=libro,
                    base_quantity=pos["base_quantity"],
                    fee_taker_bps_por_lado=pos["fee_taker_bps_por_lado"],
                    **_kwargs_filtros(filtros),
                )
            except Exception as exc:
                pos["last_exit_error"] = f"{type(exc).__name__}: {exc}"
                siguen.append(pos)
                continue
            if not fill.completo:
                pos["last_exit_error"] = fill.motivo or fill.estado
                siguen.append(pos)
                continue

            # La contabilidad 05K cierra lotes completos. Si un cambio de
            # LOT_SIZE actual obligara a vender menos que la posicion, no se
            # atribuye un P&L ficticio a todo el coste: se mantiene abierta.
            if abs(float(fill.base_ejecutada) - float(pos["base_quantity"])) > 1e-12:
                pos["last_exit_error"] = "LOT_SIZE_SALIDA_PARCIAL_NO_MODELADA"
                siguen.append(pos)
                continue

            salida_neta = float(fill.quote_neto)
            coste = float(pos["entry_quote_net"])
            pnl = salida_neta - coste
            portfolio["capital_usd"] = float(portfolio["capital_usd"]) + salida_neta
            portfolio["closed_trades"].append({
                **{k: v for k, v in pos.items() if k != "last_exit_error"},
                "closed_at": _iso(now),
                "exit_fill_price": float(fill.precio_vwap),
                "exit_quote_gross": float(fill.quote_bruto),
                "exit_quote_net": salida_neta,
                "exit_fee_usd": float(fill.fee_usd),
                "exit_slippage_bps": float(fill.slippage_bps),
                "pnl_realizado_usd": pnl,
                "retorno_realizado_neto_bps": pnl / coste * 10_000.0,
                "exit_step_size": float(filtros.step_size),
                "exit_min_qty": float(filtros.min_qty),
                "exit_max_qty": float(filtros.max_qty),
                "exit_min_notional": float(filtros.min_notional),
            })
            cerradas += 1
        portfolio["open_positions"] = siguen
    return cerradas


def _entrada_fresca(estado_05i: dict, state: dict, binance, now: datetime,
                    cache_books: dict, cache_exchange: dict,
                    motor: MotorRiesgo) -> int:
    bucket = estado_05i.get("last_run_bucket")
    if not bucket:
        return 0
    conocidos = set(state.get("processed_buckets", []))
    ignorados = {x.get("run_bucket") for x in state.get("ignored_stale_buckets", [])}
    if bucket in conocidos or bucket in ignorados:
        return 0

    group = [o for o in estado_05i.get("observations", []) if o.get("run_bucket") == bucket]
    selecciones = _selecciones(group)
    if not selecciones:
        return 0

    observed_at = max(_parse(o["observed_at"]) for o in group)
    delay = (now - observed_at).total_seconds()
    if delay < -60 or delay > MAX_ENTRY_DELAY_SECONDS:
        state.setdefault("ignored_stale_buckets", []).append({
            "run_bucket": bucket,
            "observed_at": _iso(observed_at),
            "seen_at": _iso(now),
            "delay_seconds": delay,
            "reason": "BUCKET_NO_FRESCO_SIN_BACKFILL",
        })
        return 0

    abiertas = 0
    for nombre, candidatos in selecciones.items():
        portfolio = state["portfolios"][nombre]
        for rank_estrategia, obs in enumerate(candidatos, start=1):
            symbol = str(obs["symbol"])
            if any(p["symbol"] == symbol for p in portfolio["open_positions"]):
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": "POSICION_YA_ABIERTA",
                })
                continue
            fee = obs.get("fee_taker_bps_por_lado")
            if fee is None:
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": "FEE_DESCONOCIDA",
                })
                continue

            filtros = _filtros(binance, cache_exchange, state, symbol)
            if filtros is None:
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": "FILTROS_EXCHANGE_NO_DISPONIBLES",
                })
                continue

            riesgo = _estado_riesgo_virtual(portfolio, now)
            propuesta = PropuestaOperacion(
                symbol=symbol,
                side=Lado.COMPRA,
                precio=float(obs["entry_price"]),
                base_quantity_modelo=None,
                min_notional=float(filtros.min_notional),
            )
            veredicto = motor.evaluar(
                propuesta,
                capital_disponible=float(portfolio["capital_usd"]),
                estado=riesgo,
            )
            if not veredicto.aprobado:
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": f"RIESGO:{veredicto.limite_violado or veredicto.motivo}",
                })
                continue

            aprobado_total = Decimal(str(veredicto.approved_quote_amount))
            fee_decimal = Decimal(str(fee))
            bruto_objetivo = aprobado_total / (Decimal("1") + fee_decimal / _BPS)
            libro = _book(binance, cache_books, symbol, state)
            try:
                fill = calcular_fill_compra(
                    order_book=libro,
                    quote_amount=bruto_objetivo,
                    fee_taker_bps_por_lado=fee_decimal,
                    **_kwargs_filtros(filtros),
                )
            except Exception as exc:
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": f"EJECUCION:{type(exc).__name__}:{exc}",
                })
                continue
            if not fill.completo or fill.quote_neto is None:
                portfolio["skipped_entries"].append({
                    "run_bucket": bucket, "symbol": symbol,
                    "reason": f"SIN_FILL:{fill.motivo or fill.estado}",
                })
                continue
            if fill.quote_neto > aprobado_total + Decimal("1e-12"):
                raise RuntimeError("05K excederia capital autorizado por MotorRiesgo")

            portfolio["capital_usd"] = float(portfolio["capital_usd"]) - float(fill.quote_neto)
            portfolio["open_positions"].append({
                "portfolio": nombre,
                "run_bucket": bucket,
                "symbol": symbol,
                "strategy_rank": rank_estrategia,
                "base_rank_05i": int(obs["rank"]),
                "observed_at": obs["observed_at"],
                "opened_at": _iso(now),
                "due_at": obs["due_at"],
                "entry_delay_seconds": delay,
                "entry_reference_price": float(obs["entry_price"]),
                "entry_fill_price": float(fill.precio_vwap),
                "base_quantity": float(fill.base_ejecutada),
                "entry_quote_gross": float(fill.quote_bruto),
                "entry_quote_net": float(fill.quote_neto),
                "entry_fee_usd": float(fill.fee_usd),
                "entry_slippage_bps": float(fill.slippage_bps),
                "fee_taker_bps_por_lado": float(fee),
                "entry_step_size": float(filtros.step_size),
                "entry_min_qty": float(filtros.min_qty),
                "entry_max_qty": float(filtros.max_qty),
                "entry_min_notional": float(filtros.min_notional),
            })
            abiertas += 1

    state.setdefault("processed_buckets", []).append(bucket)
    return abiertas


def _stats(valores):
    xs = [float(x) for x in valores if x is not None and math.isfinite(float(x))]
    if not xs:
        return {"n": 0, "mean": None, "median": None, "min": None,
                "max": None, "positive_rate": None}
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "median": statistics.median(xs),
        "min": min(xs),
        "max": max(xs),
        "positive_rate": sum(1 for x in xs if x > 0) / len(xs),
    }


def construir_resumen(state: dict) -> dict:
    portfolios = {}
    cerrados_bucket = {}
    for nombre in PORTFOLIOS:
        p = state["portfolios"][nombre]
        closed = list(p.get("closed_trades", []))
        open_ = list(p.get("open_positions", []))
        pnl = sum(float(t["pnl_realizado_usd"]) for t in closed)
        fees = (
            sum(float(t.get("entry_fee_usd", 0)) + float(t.get("exit_fee_usd", 0))
                for t in closed)
            + sum(float(t.get("entry_fee_usd", 0)) for t in open_)
        )
        portfolios[nombre] = {
            "initial_capital_usd": float(p["initial_capital_usd"]),
            "cash_usd": float(p["capital_usd"]),
            "open_positions": len(open_),
            "open_cost_usd": sum(float(t["entry_quote_net"]) for t in open_),
            "closed_trades": len(closed),
            "realized_pnl_usd": pnl,
            "realized_pnl_on_initial_pct": pnl / float(p["initial_capital_usd"]) * 100.0,
            "realized_net_bps": _stats([t.get("retorno_realizado_neto_bps") for t in closed]),
            "fees_executed_usd": fees,
            "skipped_entries": len(p.get("skipped_entries", [])),
            "equity_mark_to_market_available": len(open_) == 0,
        }
        por_bucket = defaultdict(list)
        for t in closed:
            por_bucket[t["run_bucket"]].append(t)
        cerrados_bucket[nombre] = por_bucket

    paired = []
    buckets = sorted(set(cerrados_bucket[PORTFOLIO_BASE]) &
                     set(cerrados_bucket[PORTFOLIO_CHALLENGER]))
    for bucket in buckets:
        base = cerrados_bucket[PORTFOLIO_BASE][bucket]
        chal = cerrados_bucket[PORTFOLIO_CHALLENGER][bucket]
        if len(base) != TOP_N or len(chal) != TOP_N:
            continue
        base_coste = sum(float(t["entry_quote_net"]) for t in base)
        chal_coste = sum(float(t["entry_quote_net"]) for t in chal)
        base_pnl = sum(float(t["pnl_realizado_usd"]) for t in base)
        chal_pnl = sum(float(t["pnl_realizado_usd"]) for t in chal)
        base_bps = base_pnl / base_coste * 10_000.0
        chal_bps = chal_pnl / chal_coste * 10_000.0
        paired.append({
            "run_bucket": bucket,
            "base_realized_pnl_usd": base_pnl,
            "challenger_realized_pnl_usd": chal_pnl,
            "base_realized_net_bps": base_bps,
            "challenger_realized_net_bps": chal_bps,
            "challenger_minus_base_net_bps": chal_bps - base_bps,
        })

    return {
        "phase": "05K",
        "mode": "SHADOW_EXECUTION",
        "generated_at": _iso(datetime.now(timezone.utc)),
        "orders_executed": False,
        "llm_called": False,
        "database_touched": False,
        "scanner_modified": False,
        "backfill_allowed": False,
        "entry_freshness_max_seconds": MAX_ENTRY_DELAY_SECONDS,
        "risk_engine_used_for_sizing": True,
        "exchange_min_notional_checked": True,
        "exchange_lot_size_checked": True,
        "exchange_filters_source": "BINANCE_EXCHANGE_INFO_CURRENT",
        "execution_model": "ORDER_BOOK_VWAP_TAKER_FEE_EXCHANGE_FILTERS",
        "orderbook_calls": int(state.get("orderbook_calls", 0)),
        "exchange_info_calls": int(state.get("exchange_info_calls", 0)),
        "processed_buckets": len(state.get("processed_buckets", [])),
        "ignored_stale_buckets": len(state.get("ignored_stale_buckets", [])),
        "portfolios": portfolios,
        "paired_complete_buckets": len(paired),
        "challenger_minus_base_net_bps": _stats(
            [b["challenger_minus_base_net_bps"] for b in paired]
        ),
        "paired_buckets": paired,
        "interpretation": (
            "Ejecucion prospectiva de Top-5 base y challenger con sizing del "
            "MotorRiesgo, filtros actuales de Binance, profundidad real y fees; "
            "no autoriza trading real."
        ),
    }


def procesar(estado_05i: dict, state: dict, binance, now: datetime,
             motor: MotorRiesgo | None = None) -> tuple[int, int, dict]:
    motor = motor or MotorRiesgo()
    cache_books = {}
    cache_exchange = {}
    cerradas = _cerrar_vencidas(
        state, binance, now, cache_books, cache_exchange)
    abiertas = _entrada_fresca(
        estado_05i, state, binance, now, cache_books, cache_exchange, motor)
    state["last_run_at"] = _iso(now)
    return abiertas, cerradas, construir_resumen(state)


def main() -> None:
    if settings.MODO_REAL:
        raise RuntimeError("05K solo puede ejecutarse en PAPER; LIVE bloqueado")
    now = datetime.now(timezone.utc)
    estado_05i = cargar_05i()
    state = cargar_estado()
    binance = BinanceConnector()
    abiertas, cerradas, summary = procesar(estado_05i, state, binance, now)
    _guardar(STATE, state)
    _guardar(SUMMARY, summary)
    print(
        f"[SHADOW-05K] abiertas={abiertas} cerradas={cerradas} "
        f"buckets={summary['processed_buckets']} paired={summary['paired_complete_buckets']} "
        f"books={summary['orderbook_calls']} exchangeInfo={summary['exchange_info_calls']}"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"state={STATE.relative_to(RAIZ_REPO)}")
    print(f"summary={SUMMARY.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
