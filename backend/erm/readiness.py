"""Pure preflight for finite 05M captures; no network or persistence."""
from __future__ import annotations

import copy
import math

from backend.erm.ledger import number
from backend.erm.replay import import_base


def open_cohort(source):
    result = copy.deepcopy(source)
    result["portfolios"]["BASE_05I"]["closed_trades"] = []
    return result


def validate_fee(fee, now):
    if not isinstance(fee, dict):
        raise ValueError("FEE_MISSING")
    try:
        rate = number(fee["bps"])
        verified, expires = number(fee["verified_at"]), number(fee["expires_at"])
        source = fee["source"]
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("FEE_INVALID") from exc
    if not isinstance(source, str) or not source.strip() or not 0 <= rate < 10000 or not 0 < expires - verified <= 604800:
        raise ValueError("FEE_INVALID")
    if not verified <= number(now) <= expires:
        raise ValueError("FEE_EXPIRED_OR_FUTURE")
    return float(expires)


def capture_readiness(source, fee, *, now, seconds):
    now = float(number(now))
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 86400:
        raise ValueError("CAPTURE_SECONDS_1_TO_86400_REQUIRED")
    lots = import_base(open_cohort(source))
    blockers, warnings = [], []
    try:
        expires = validate_fee(fee, now)
    except ValueError as exc:
        blockers.append(str(exc))
        expires = None
    active = [lot for lot in lots if lot.opened <= now < lot.due]
    if not active:
        blockers.append("NO_CURRENT_OPEN_COHORT")
    if any(lot.opened > now for lot in lots):
        blockers.append("FUTURE_ENTRY_IN_SOURCE")
    if active and len(active) != len(lots):
        blockers.append("MIXED_EXPIRED_AND_ACTIVE_COHORT")
    required_seconds = math.ceil(max(lot.due + 60 for lot in active) - now) if active else None
    late = [lot.id for lot in active if now - lot.opened > 30]
    if late:
        warnings.append("LATE_START_EXCLUDED_FROM_QUALIFIED_PAIRS")
    if required_seconds is not None and seconds < required_seconds:
        warnings.append("CAPTURE_ENDS_BEFORE_HORIZON_GRACE")
    if expires is not None and active and expires < max(lot.due + 60 for lot in active):
        warnings.append("FEE_EXPIRES_BEFORE_HORIZON_GRACE")
    return {
        "ready": not blockers,
        "status": "BLOCKED" if blockers else "READY_DIAGNOSTIC_ONLY" if warnings else "READY_FULL_COVERAGE_POSSIBLE",
        "checked_at": now, "blockers": blockers, "warnings": warnings,
        "open_lots": len(active), "symbols": sorted({lot.symbol for lot in active}),
        "late_lots": late, "capture_seconds": seconds,
        "required_seconds_through_horizon": required_seconds,
        "fee_expires_at": expires,
        "note": "Readiness does not guarantee market-data availability or economic benefit.",
    }
