from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.protocolo_crossvenue_carry_04h1 import (  # noqa: E402
    AWS_REQUESTER_PAYS_FULL_2024_2025_AUTORIZADO_04H1,
    HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
    HYPERLIQUID_ASSET_CTXS_PREFIX_04H1,
    HYPERLIQUID_DOWNLOAD_2026_PERMITIDO_04H1,
    HYPERLIQUID_DOWNLOAD_DESDE_04H1,
    HYPERLIQUID_DOWNLOAD_DIAS_ESPERADOS_04H1,
    HYPERLIQUID_DOWNLOAD_HASTA_04H1,
)

AUTH_ENV = "ALLOW_HYPERLIQUID_REQUESTER_PAYS_FULL_04H1"
DATA_DIR = ROOT / "data" / "research" / "04h1" / "hyperliquid" / "asset_ctxs"
REPORT_PATH = ROOT / "artifacts" / "hyperliquid-asset-ctxs-download-04h1.json"


def _dates():
    start = datetime.strptime(HYPERLIQUID_DOWNLOAD_DESDE_04H1, "%Y%m%d").date()
    end = datetime.strptime(HYPERLIQUID_DOWNLOAD_HASTA_04H1, "%Y%m%d").date()
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _write_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _validate_protocol() -> list:
    dates = list(_dates())
    if not AWS_REQUESTER_PAYS_FULL_2024_2025_AUTORIZADO_04H1:
        raise RuntimeError("El protocolo no autoriza la descarga completa 2024-2025.")
    if HYPERLIQUID_DOWNLOAD_2026_PERMITIDO_04H1:
        raise RuntimeError("Candado roto: 2026 no puede estar permitido.")
    if dates[0].strftime("%Y%m%d") != "20240101":
        raise RuntimeError("Fecha inicial fuera del protocolo 04H-1.")
    if dates[-1].strftime("%Y%m%d") != "20251231":
        raise RuntimeError("Fecha final fuera del protocolo 04H-1.")
    if len(dates) != HYPERLIQUID_DOWNLOAD_DIAS_ESPERADOS_04H1:
        raise RuntimeError("Cantidad de días distinta al protocolo 04H-1.")
    if any(day.year >= 2026 for day in dates):
        raise RuntimeError("Candado roto: la descarga intenta tocar 2026.")
    return dates


def main() -> int:
    dates = _validate_protocol()
    report = {
        "phase": "04H-1",
        "source": "hyperliquid official requester-pays asset_ctxs",
        "bucket": HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
        "from": HYPERLIQUID_DOWNLOAD_DESDE_04H1,
        "to": HYPERLIQUID_DOWNLOAD_HASTA_04H1,
        "expected_days": len(dates),
        "downloaded_now": 0,
        "reused_local": 0,
        "missing_remote": [],
        "errors": [],
        "downloaded_bytes": 0,
        "local_total_bytes": 0,
        "completed": False,
    }

    if os.environ.get(AUTH_ENV) != "YES":
        report["errors"].append(f"Falta {AUTH_ENV}=YES; se rehúsa cualquier llamada requester-pays.")
        _write_report(report)
        return 2

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3")

    for index, day in enumerate(dates, start=1):
        stamp = day.strftime("%Y%m%d")
        target = DATA_DIR / f"{stamp}.csv.lz4"
        part = DATA_DIR / f"{stamp}.csv.lz4.part"

        if target.exists() and target.stat().st_size > 0:
            report["reused_local"] += 1
            report["local_total_bytes"] += target.stat().st_size
            print(f"[{index:03d}/{len(dates)}] REUSE {target.name} ({target.stat().st_size} bytes)")
            continue

        if part.exists():
            part.unlink()

        key = f"{HYPERLIQUID_ASSET_CTXS_PREFIX_04H1}/{stamp}.csv.lz4"
        try:
            response = s3.get_object(
                Bucket=HYPERLIQUID_ASSET_CTXS_BUCKET_04H1,
                Key=key,
                RequestPayer="requester",
            )
            with part.open("wb") as handle:
                while True:
                    chunk = response["Body"].read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            if part.stat().st_size <= 0:
                raise RuntimeError("archivo descargado vacío")
            part.replace(target)
            size = target.stat().st_size
            report["downloaded_now"] += 1
            report["downloaded_bytes"] += size
            report["local_total_bytes"] += size
            print(f"[{index:03d}/{len(dates)}] DOWNLOADED {target.name} ({size} bytes)")
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                report["missing_remote"].append(stamp)
                print(f"[{index:03d}/{len(dates)}] MISSING {stamp}")
            else:
                report["errors"].append({"date": stamp, "type": type(exc).__name__, "error": str(exc)})
                print(f"[{index:03d}/{len(dates)}] ERROR {stamp}: {exc}")
        except Exception as exc:
            report["errors"].append({"date": stamp, "type": type(exc).__name__, "error": str(exc)})
            print(f"[{index:03d}/{len(dates)}] ERROR {stamp}: {exc}")
        finally:
            if part.exists():
                part.unlink()
            _write_report(report)

    present_days = len([p for p in DATA_DIR.glob("*.csv.lz4") if p.stat().st_size > 0])
    report["present_days"] = present_days
    report["coverage_days"] = present_days / len(dates)
    report["completed"] = not report["errors"] and present_days == len(dates)
    _write_report(report)

    print(json.dumps({
        "present_days": report["present_days"],
        "expected_days": report["expected_days"],
        "coverage_days": report["coverage_days"],
        "downloaded_now": report["downloaded_now"],
        "reused_local": report["reused_local"],
        "missing_remote": len(report["missing_remote"]),
        "errors": len(report["errors"]),
        "downloaded_bytes": report["downloaded_bytes"],
        "report": str(REPORT_PATH),
    }, indent=2))

    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
