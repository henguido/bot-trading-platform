from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone


MAX_AGE = timedelta(days=7)


def fee_taker_manual_verificada(now: datetime | None = None):
    raw = os.getenv("RESEARCH_TAKER_FEE_BPS")
    fuente = (os.getenv("RESEARCH_TAKER_FEE_SOURCE") or "").strip()
    verificada = os.getenv("RESEARCH_TAKER_FEE_VERIFIED_AT")

    if not raw or not fuente or not verificada:
        return None

    try:
        fee = float(raw)
        fecha = datetime.fromisoformat(verificada.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if fecha.tzinfo is None or fecha.utcoffset() is None:
        return None

    ahora = now or datetime.now(timezone.utc)
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        return None

    ahora = ahora.astimezone(timezone.utc)
    fecha = fecha.astimezone(timezone.utc)

    if not math.isfinite(fee) or fee < 0:
        return None

    edad = ahora - fecha
    if edad < timedelta(minutes=-5) or edad > MAX_AGE:
        return None

    return {
        "fee_taker_bps_por_lado": fee,
        "fuente_fee": fuente,
        "fee_verified_at": fecha.isoformat(),
    }
