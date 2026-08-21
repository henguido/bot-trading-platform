"""04D-2: auditor de metadata Binance USER_DATA estrictamente read-only."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import requests

from backend.economia.protocolo_metadata_04d2 import (
    API_KEY_ENV_04D2,
    API_SECRET_ENV_04D2,
    FUTURES_ACCOUNT_CONFIG_PATH_04D2,
    FUTURES_BASE_URL_04D2,
    FUTURES_COMMISSION_PATH_04D2,
    HTTP_METHODS_PERMITIDOS_04D2,
    LEVERAGE_BRACKET_PATH_04D2,
    MULTI_ASSETS_MODE_PATH_04D2,
    READONLY_OPT_IN_ENV_04D2,
    RECV_WINDOW_MS_04D2,
    SIMBOLOS_04D2,
    SPOT_BASE_URL_04D2,
    SPOT_COMMISSION_PATH_04D2,
    STATUS_APTA_04D2,
    STATUS_ERROR_04D2,
    STATUS_NO_CREDS_04D2,
    TIMEOUT_SEGUNDOS_04D2,
)


@dataclass(frozen=True)
class Credenciales04D2:
    api_key: str
    api_secret: str


@dataclass(frozen=True)
class ResultadoMetadata04D2:
    status: str
    executed: bool
    reasons: tuple[str, ...]
    metadata: Mapping[str, Any]


def cargar_credenciales_04d2() -> Credenciales04D2 | None:
    if os.getenv(READONLY_OPT_IN_ENV_04D2) != "1":
        return None
    key = os.getenv(API_KEY_ENV_04D2, "").strip()
    secret = os.getenv(API_SECRET_ENV_04D2, "").strip()
    if not key or not secret:
        return None
    return Credenciales04D2(key, secret)


def construir_query_firmada_04d2(
    params: Mapping[str, Any],
    secret: str,
    *,
    timestamp_ms: int | None = None,
) -> str:
    payload = dict(params)
    payload["recvWindow"] = RECV_WINDOW_MS_04D2
    payload["timestamp"] = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
    query = urlencode(sorted((k, str(v)) for k, v in payload.items()))
    signature = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{query}&signature={signature}"


def signed_get_04d2(
    session: requests.Session,
    base_url: str,
    path: str,
    params: Mapping[str, Any],
    credentials: Credenciales04D2,
) -> Any:
    if HTTP_METHODS_PERMITIDOS_04D2 != ("GET",):
        raise RuntimeError("candado HTTP 04D-2 alterado")
    query = construir_query_firmada_04d2(params, credentials.api_secret)
    response = session.get(
        f"{base_url}{path}?{query}",
        headers={"X-MBX-APIKEY": credentials.api_key},
        timeout=TIMEOUT_SEGUNDOS_04D2,
    )
    response.raise_for_status()
    return response.json()


def ejecutar_auditoria_metadata_04d2(
    session: requests.Session | None = None,
    credentials: Credenciales04D2 | None = None,
) -> ResultadoMetadata04D2:
    credentials = credentials or cargar_credenciales_04d2()
    if credentials is None:
        return ResultadoMetadata04D2(
            status=STATUS_NO_CREDS_04D2,
            executed=False,
            reasons=(
                "opt-in read-only y/o credenciales ausentes",
                "CI no debe recibir credenciales reales",
            ),
            metadata={},
        )

    session = session or requests.Session()
    metadata: dict[str, Any] = {
        "spot_commission": {},
        "futures_commission": {},
        "leverage_brackets": {},
    }
    reasons: list[str] = []
    try:
        for symbol in SIMBOLOS_04D2:
            metadata["spot_commission"][symbol] = signed_get_04d2(
                session, SPOT_BASE_URL_04D2, SPOT_COMMISSION_PATH_04D2,
                {"symbol": symbol}, credentials,
            )
            metadata["futures_commission"][symbol] = signed_get_04d2(
                session, FUTURES_BASE_URL_04D2, FUTURES_COMMISSION_PATH_04D2,
                {"symbol": symbol}, credentials,
            )
            metadata["leverage_brackets"][symbol] = signed_get_04d2(
                session, FUTURES_BASE_URL_04D2, LEVERAGE_BRACKET_PATH_04D2,
                {"symbol": symbol}, credentials,
            )

        metadata["multi_assets_mode"] = signed_get_04d2(
            session, FUTURES_BASE_URL_04D2, MULTI_ASSETS_MODE_PATH_04D2,
            {}, credentials,
        )
        metadata["futures_account_config"] = signed_get_04d2(
            session, FUTURES_BASE_URL_04D2, FUTURES_ACCOUNT_CONFIG_PATH_04D2,
            {}, credentials,
        )
    except Exception as exc:
        reasons.append(f"{type(exc).__name__}:{exc}")
        # Nunca incluir key/secret en resultado, aun en errores.
        safe = {k: v for k, v in metadata.items()}
        return ResultadoMetadata04D2(STATUS_ERROR_04D2, True, tuple(reasons), safe)

    return ResultadoMetadata04D2(STATUS_APTA_04D2, True, (), metadata)
