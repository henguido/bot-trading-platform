from __future__ import annotations

import csv
import io
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import boto3
import lz4.frame

from backend.economia.protocolo_crossvenue_carry_04h1 import (
    ACTIVOS_04H1,
    AWS_REQUESTER_PAYS_AUTORIZADO_04H1,
    HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
    HYPERLIQUID_ASSET_CTXS_PREFIX_04H1,
    HYPERLIQUID_PROBE_DATE_04H1,
    HYPERLIQUID_PROBE_DIAS_MAX_04H1,
    HYPERLIQUID_REQUESTER_PAYS_04H1,
    PROBE_COBERTURA_MIN_04H1,
    PROBE_HORAS_ESPERADAS_04H1,
)

ARTIFACT_PATH = Path("artifacts/hyperliquid-asset-ctxs-probe-04h1.json")
AUTH_ENV = "ALLOW_HYPERLIQUID_REQUESTER_PAYS_PROBE"
ALIASES = {
    "coin": ("coin", "symbol", "asset", "name"),
    "time": ("time", "timestamp", "ts", "datetime"),
    "oracle": ("oraclepx", "oracle_px", "oracleprice", "oracle_price"),
    "mark": ("markpx", "mark_px", "markprice", "mark_price"),
}


def _write_artifact(payload: dict) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalized(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("-", "_")


def _resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalized(name): name for name in fieldnames if name}
    resolved: dict[str, str] = {}
    for logical, aliases in ALIASES.items():
        for alias in aliases:
            key = _normalized(alias)
            if key in normalized:
                resolved[logical] = normalized[key]
                break
    return resolved


def _parse_utc_hour(raw: str) -> datetime:
    value = raw.strip()
    if not value:
        raise ValueError("timestamp vacío")

    try:
        numeric = Decimal(value)
    except InvalidOperation:
        numeric = None

    if numeric is not None:
        seconds = float(numeric)
        if abs(seconds) >= 1_000_000_000_000:
            seconds /= 1000.0
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)

    return dt.replace(minute=0, second=0, microsecond=0)


def _positive_decimal(raw: str) -> Decimal:
    value = Decimal(raw.strip())
    if not value.is_finite() or value <= 0:
        raise ValueError("precio no positivo o no finito")
    return value


def _audit_csv(csv_bytes: bytes, probe_date: str) -> dict:
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    fieldnames = reader.fieldnames or []
    columns = _resolve_columns(fieldnames)
    missing_columns = sorted({"coin", "time", "oracle", "mark"} - set(columns))

    result: dict = {
        "headers": fieldnames,
        "resolved_columns": columns,
        "missing_required_columns": missing_columns,
        "rows_total": 0,
        "rows_target_assets": 0,
        "rows_valid_prices": 0,
        "invalid_rows": 0,
        "assets": {},
    }
    if missing_columns:
        return result

    expected_day = datetime.strptime(probe_date, "%Y%m%d").date()
    hourly: dict[str, set[str]] = defaultdict(set)
    per_asset_rows: dict[str, int] = defaultdict(int)
    per_asset_valid: dict[str, int] = defaultdict(int)
    samples: dict[str, dict] = {}

    for row in reader:
        result["rows_total"] += 1
        coin = (row.get(columns["coin"]) or "").strip().upper()
        if coin not in ACTIVOS_04H1:
            continue

        result["rows_target_assets"] += 1
        per_asset_rows[coin] += 1
        try:
            hour = _parse_utc_hour(row.get(columns["time"]) or "")
            oracle = _positive_decimal(row.get(columns["oracle"]) or "")
            mark = _positive_decimal(row.get(columns["mark"]) or "")
            if hour.date() != expected_day:
                raise ValueError("timestamp fuera del día autorizado")
        except (ValueError, InvalidOperation, OverflowError):
            result["invalid_rows"] += 1
            continue

        result["rows_valid_prices"] += 1
        per_asset_valid[coin] += 1
        hourly[coin].add(hour.isoformat())
        samples.setdefault(
            coin,
            {
                "hour_utc": hour.isoformat(),
                "oracle_px": str(oracle),
                "mark_px": str(mark),
            },
        )

    all_pass = True
    for coin in ACTIVOS_04H1:
        hours = len(hourly[coin])
        coverage = Decimal(hours) / Decimal(PROBE_HORAS_ESPERADAS_04H1)
        passed = coverage >= PROBE_COBERTURA_MIN_04H1
        all_pass = all_pass and passed
        result["assets"][coin] = {
            "rows": per_asset_rows[coin],
            "valid_price_rows": per_asset_valid[coin],
            "unique_hours": hours,
            "expected_hours": PROBE_HORAS_ESPERADAS_04H1,
            "coverage": str(coverage),
            "passed_99pct_gate": passed,
            "sample": samples.get(coin),
        }

    result["passed_probe_gate"] = all_pass
    return result


def main() -> int:
    base = {
        "phase": "04H-1",
        "source": "hyperliquid official requester-pays asset_ctxs",
        "bucket": HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
        "probe_date": HYPERLIQUID_PROBE_DATE_04H1,
        "max_authorized_days": HYPERLIQUID_PROBE_DIAS_MAX_04H1,
        "requester_pays": HYPERLIQUID_REQUESTER_PAYS_04H1,
        "assets": list(ACTIVOS_04H1),
    }

    if not AWS_REQUESTER_PAYS_AUTORIZADO_04H1:
        base["error"] = "El protocolo no autoriza requester-pays."
        _write_artifact(base)
        return 2
    if os.environ.get(AUTH_ENV) != "YES":
        base["error"] = f"Falta {AUTH_ENV}=YES; se rehúsa cualquier llamada con coste."
        _write_artifact(base)
        return 2
    if HYPERLIQUID_PROBE_DIAS_MAX_04H1 != 1:
        base["error"] = "El probe dejó de estar limitado exactamente a un día."
        _write_artifact(base)
        return 2

    key = f"{HYPERLIQUID_ASSET_CTXS_PREFIX_04H1}/{HYPERLIQUID_PROBE_DATE_04H1}.csv.lz4"
    base["key"] = key

    try:
        s3 = boto3.client("s3")
        response = s3.get_object(
            Bucket=HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
            Key=key,
            RequestPayer="requester",
        )
        compressed = response["Body"].read()
        base["compressed_bytes"] = len(compressed)
        base["content_length_header"] = response.get("ContentLength")
        base["etag"] = str(response.get("ETag", "")).strip('"')
        csv_bytes = lz4.frame.decompress(compressed)
        base["decompressed_bytes"] = len(csv_bytes)
        base["audit"] = _audit_csv(csv_bytes, HYPERLIQUID_PROBE_DATE_04H1)
    except Exception as exc:
        base["error_type"] = type(exc).__name__
        base["error"] = str(exc)
        _write_artifact(base)
        return 1

    _write_artifact(base)
    if base["audit"]["missing_required_columns"]:
        return 1
    return 0 if base["audit"].get("passed_probe_gate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
