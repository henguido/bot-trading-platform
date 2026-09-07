"""Offline 05M replay and optional finite public-data capture; never trades."""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.erm.replay import INVARIANTS, import_base, replay


def guard_environment():
    if os.getenv("TRADING_MODE", "PAPER").upper() != "PAPER" or os.getenv("ALLOW_LIVE_TRADING", "").strip() or os.getenv("MODO_REAL", "false").lower() not in {"false", "0", ""}:
        raise ValueError("05M requires PAPER and LIVE disabled")
    if Decimal(os.getenv("INITIAL_CAPITAL_USD", "500")) != 500 or Decimal(os.getenv("LIMITE_ASIGNACION_POR_OPERACION", ".02")) != Decimal(".02"):
        raise ValueError("05M requires 500 USDT / 2%")


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def write_report(path, payload):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, default=encode, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def capture(source, path, *, seconds, fee, client=None, clock=time.time, sleep=time.sleep):
    """Finite capture. No private endpoints, credentials, websocket claims or cron."""
    if not 1 <= seconds <= 86400:
        raise ValueError("capture seconds must be 1..86400")
    planned = import_base(source)
    if client is None:
        from backend.connectors.crypto.binance_public_market import BinancePublicMarketData
        client = BinancePublicMarketData(timeout=5)
    deadline = clock() + seconds
    # Exclusive evidence file: never overwrite a previous observation journal.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        while clock() < deadline:
            started = clock()
            # Continue to observe the BASE counterfactual even if ERM would exit early.
            symbols = sorted({lot.symbol for lot in planned if lot.opened <= started <= lot.due + 60})
            if not symbols:
                break
            try:
                info = client.get_exchange_symbols_info()
            except Exception:
                info = {}
            filters_at = clock()
            for symbol in symbols:
                event = {"symbol": symbol, "fee": fee, "filters_at": filters_at, "capture_source": "PUBLIC_REST_PROSPECTIVE"}
                try:
                    event["klines"] = client.get_recent_klines(symbol, interval="1m", limit=40)
                    event["book"] = client.get_order_book(symbol, limit=100)
                    event["book_at"] = clock()
                    filters = {row["filterType"]: row for row in info[symbol]["filters"]}
                    lot_filter = filters["LOT_SIZE"]
                    notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
                    event["filters"] = dict(step_size=lot_filter["stepSize"], min_qty=lot_filter["minQty"], max_qty=lot_filter["maxQty"], min_notional=notional["minNotional"])
                except Exception as exc:
                    event["capture_error"] = type(exc).__name__
                event["at"] = clock()
                stream.write(json.dumps(event, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                yield event
            remaining = min(deadline - clock(), 30 - (clock() - started))
            if remaining > 0:
                sleep(remaining)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="05K state, read-only")
    parser.add_argument("--events", type=Path, help="Recorded 05M JSONL snapshots")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture-seconds", type=int)
    parser.add_argument("--fee-evidence", type=Path, help="JSON bps/source/verified_at/expires_at (Unix seconds)")
    args = parser.parse_args(argv)
    guard_environment()
    if bool(args.events) == bool(args.capture_seconds):
        parser.error("select --events OR --capture-seconds")
    raw = args.source.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    import_base(source)
    fee = None
    if args.capture_seconds:
        if not args.fee_evidence or not 1 <= args.capture_seconds <= 86400:
            parser.error("capture requires --fee-evidence and 1..86400 seconds")
        fee = json.loads(args.fee_evidence.read_text(encoding="utf-8"))
        rate = Decimal(str(fee["bps"]))
        if not rate.is_finite() or not 0 <= rate < 10000 or not fee["source"] or not float(fee["verified_at"]) <= time.time() <= float(fee["expires_at"]) or float(fee["expires_at"]) - float(fee["verified_at"]) > 604800:
            raise ValueError("valid current fee evidence required")
        source = copy.deepcopy(source)
        # Capture follows the currently open cohort; historical closed lots lack books.
        source["portfolios"]["BASE_05I"]["closed_trades"] = []
    output = args.output_dir.resolve()
    # The research output must be a NEW directory: no source or operational files overwritten.
    output.mkdir(parents=True, exist_ok=False)
    write_report(output / "source-05k-readonly-copy.json", source)
    path = args.events
    if args.capture_seconds:
        path = output / "market-erm-05m.jsonl"
        events = capture(source, path, seconds=args.capture_seconds, fee=fee)
        with (output / "decisions-erm-05m.jsonl").open("x", encoding="utf-8", newline="\n") as decisions:
            def record(decision):
                decisions.write(json.dumps(decision, allow_nan=False) + "\n")
                decisions.flush()
                if decision.get("transition"):
                    print(json.dumps({k: decision[k] for k in ("at", "symbol", "state", "reason")}))
            result = replay(source, events, on_decision=record)
    else:
        with path.open(encoding="utf-8") as stream:
            result = replay(source, (json.loads(line) for line in stream if line.strip()))
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    result["events_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.source.read_bytes() != raw:
        raise RuntimeError("source changed externally during replay; repeat with stable snapshot")
    write_report(output / "report-erm-05m.json", result)
    print(json.dumps({**INVARIANTS, "status": result["status"], "paired_closed_lots": result["paired_closed_lots"], "qualified_pairs": result["qualified_pairs"], "report": str(output / "report-erm-05m.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
