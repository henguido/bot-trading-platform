from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone


MAX_AGE = timedelta(days=7)


def diagnosticar_fee_taker_manual(
    now: datetime | None = None,
    *,
    environ=None,
):
    """Diagnostico puro y seguro de la fee manual verificada.

    No hace red ni expone credenciales. Distingue ausencia, invalidez,
    caducidad y evidencia vigente para que readiness/observabilidad no tengan
    que interpretar ``None`` de forma ambigua.
    """
    env = os.environ if environ is None else environ
    raw = env.get("RESEARCH_TAKER_FEE_BPS")
    fuente = (env.get("RESEARCH_TAKER_FEE_SOURCE") or "").strip()
    verificada = env.get("RESEARCH_TAKER_FEE_VERIFIED_AT")

    base = {
        "status": "NO_DISPONIBLE",
        "fee_taker_bps_por_lado": None,
        "fuente_fee": None,
        "fee_verified_at": None,
        "age_seconds": None,
        "max_age_seconds": int(MAX_AGE.total_seconds()),
    }

    if not raw and not fuente and not verificada:
        return base
    if not raw or not fuente or not verificada:
        return {**base, "status": "INVALIDA"}

    try:
        fee = float(raw)
        fecha = datetime.fromisoformat(str(verificada).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return {**base, "status": "INVALIDA"}

    if fecha.tzinfo is None or fecha.utcoffset() is None:
        return {**base, "status": "INVALIDA"}

    ahora = now or datetime.now(timezone.utc)
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        return {**base, "status": "INVALIDA"}

    ahora = ahora.astimezone(timezone.utc)
    fecha = fecha.astimezone(timezone.utc)

    if not math.isfinite(fee) or fee < 0:
        return {**base, "status": "INVALIDA"}

    edad = ahora - fecha
    age_seconds = edad.total_seconds()
    datos = {
        **base,
        "fee_taker_bps_por_lado": fee,
        "fuente_fee": fuente,
        "fee_verified_at": fecha.isoformat(),
        "age_seconds": age_seconds,
    }

    if edad < timedelta(minutes=-5):
        return {**datos, "status": "INVALIDA"}
    if edad > MAX_AGE:
        return {**datos, "status": "VENCIDA"}
    return {**datos, "status": "VERIFICADA"}


def fee_taker_manual_verificada(
    now: datetime | None = None,
    *,
    environ=None,
):
    diagnostico = diagnosticar_fee_taker_manual(now, environ=environ)
    if diagnostico["status"] != "VERIFICADA":
        return None
    return {
        "fee_taker_bps_por_lado": diagnostico["fee_taker_bps_por_lado"],
        "fuente_fee": diagnostico["fuente_fee"],
        "fee_verified_at": diagnostico["fee_verified_at"],
    }
