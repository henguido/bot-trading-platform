"""Prepare an independent frozen-strategy cohort and immediately capture 05M.

Never reads or updates the cumulative 05I/05J/05K artifact paths. Run as a new
process: imports of existing research adapters happen after environment guards.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.erm.readiness import validate_fee
from scripts.shadow_emergency_risk_05m import guard_environment, write_report, main as capture_main

FROZEN_ROOTS = ("backend/scanner.py", "backend/risk/motor.py",
                "scripts/shadow_scanner_unified_05i.py",
                "scripts/analyze_scanner_challenger_05j.py",
                "scripts/shadow_strategy_execution_05k.py",
                "scripts/shadow_emergency_risk_05m.py",
                "scripts/run_erm_05m_prospective.py")
FROZEN_ENVIRONMENT = ("requirements.txt", "constraints.txt")


def _local_module_paths(module):
    if not module or module.split(".")[0] not in {"backend", "scripts"}:
        return set()
    base = ROOT.joinpath(*module.split("."))
    candidates = (base.with_suffix(".py"), base / "__init__.py")
    return {candidate for candidate in candidates if candidate.is_file()}


def _dependency_closure():
    """Return every local Python source reachable from the experimental roots."""
    pending = [ROOT / name for name in FROZEN_ROOTS]
    found = set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        if not path.is_file() or not path.is_relative_to(ROOT):
            raise ValueError(f"invalid frozen dependency: {path}")
        found.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module:
                    modules.append(node.module)
                    modules.extend(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
            for module in modules:
                pending.extend(_local_module_paths(module) - found)
    return found


def fingerprint():
    paths = _dependency_closure()
    paths.update(ROOT / name for name in FROZEN_ENVIRONMENT if (ROOT / name).is_file())
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def prepare_cohort(output, fee, *, observer, executor, clock=time.time):
    """Inject the unchanged 05I and 05K functions, operating on fresh dictionaries."""
    validate_fee(fee, clock())
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    hashes = fingerprint()
    source_i = {"phase": "05I", "mode": "SHADOW", "observations": []}
    observed = datetime.fromtimestamp(clock(), timezone.utc)
    added = observer(source_i, observed)
    if added != 20:
        raise ValueError("INDEPENDENT_COHORT_REQUIRES_COMPLETE_TOP20")
    source_k, summary = executor(source_i, datetime.fromtimestamp(clock(), timezone.utc))
    source_k["research_stream"] = "ERM_05M_INDEPENDENT"
    source_k["official_05ijk_evidence"] = False
    manifest = {"research_stream": "ERM_05M_INDEPENDENT", "official_05ijk_evidence": False,
                "created_at": observed.isoformat(), "frozen_files_sha256": hashes,
                "fee_evidence": fee, "orders_executed": False, "scanner_modified": False,
                "database_touched": False, "LIVE": False, "enabled_05E": False}
    if fingerprint() != hashes:
        raise RuntimeError("frozen code changed during preparation")
    if len(source_k["portfolios"]["BASE_05I"]["open_positions"]) != 5:
        raise ValueError("INDEPENDENT_COHORT_REQUIRES_FIVE_EXECUTABLE_BASE_LOTS")
    output.mkdir(parents=True, exist_ok=False)
    write_report(output / "scanner-independent-05i.json", source_i)
    write_report(output / "source-independent-05k.json", source_k)
    write_report(output / "summary-independent-05k.json", summary)
    write_report(output / "manifest-05m.json", manifest)
    return output / "source-independent-05k.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fee-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture-seconds", type=int, default=15000)
    args = parser.parse_args(argv)
    guard_environment()
    if not 1 <= args.capture_seconds <= 86400:
        parser.error("capture seconds must be 1..86400")
    fee = json.loads(args.fee_evidence.read_text(encoding="utf-8"))
    validate_fee(fee, time.time())
    # Process-only isolation before importing the original research adapters.
    os.environ.update(BINANCE_API_KEY="", BINANCE_API_SECRET="", OPENAI_API_KEY="",
                      APP_ENV="test", DATABASE_URL="sqlite:///:memory:",
                      SECRET_KEY="synthetic-isolated-erm-05m-research-only",
                      RESEARCH_TAKER_FEE_BPS=str(fee["bps"]),
                      RESEARCH_TAKER_FEE_SOURCE=fee["source"],
                      RESEARCH_TAKER_FEE_VERIFIED_AT=datetime.fromtimestamp(fee["verified_at"], timezone.utc).isoformat())
    from backend.config import settings
    from backend.connectors.crypto.binance_public_market import BinancePublicMarketData
    from scripts import shadow_scanner_unified_05i as scanner
    from scripts import shadow_strategy_execution_05k as execution
    if settings.BINANCE_API_KEY or settings.BINANCE_API_SECRET or settings.MODO_REAL or settings.DATABASE_URL != "sqlite:///:memory:":
        raise RuntimeError("run independent cohort in a fresh isolated process")
    client = BinancePublicMarketData(timeout=5)

    def observe(state, now):
        return scanner._observar(state, client, now)

    def execute(state_i, now):
        state_k = execution.nuevo_estado(500)
        _, _, summary = execution.procesar(state_i, state_k, client, now)
        return state_k, summary

    root = args.output_dir.resolve()
    source_path = prepare_cohort(root, fee, observer=observe, executor=execute)
    return capture_main(["--source", str(source_path), "--fee-evidence", str(args.fee_evidence.resolve()),
                         "--capture-seconds", str(args.capture_seconds), "--output-dir", str(root / "capture")])


if __name__ == "__main__":
    raise SystemExit(main())
