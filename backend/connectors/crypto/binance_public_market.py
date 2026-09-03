"""Cliente REST de solo mercado para Binance Spot.

Usa el endpoint oficial de market-data-only documentado por Binance:
https://data-api.binance.vision. No recibe API keys, no expone endpoints de
cuenta y no puede enviar ordenes. Está pensado para investigación/shadows y
para evitar que un cliente privado haga `ping` contra api.binance.com antes de
leer datos públicos.
"""
from __future__ import annotations

from typing import Any

import requests


PUBLIC_BASE_URL = "https://data-api.binance.vision"


class BinancePublicMarketData:
    def __init__(self, *, session=None, base_url: str = PUBLIC_BASE_URL, timeout: int = 20):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)

    def _get(self, path: str, *, params=None):
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params or None,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_exchange_symbols_info(self, medicion=None) -> dict[str, dict[str, Any]]:
        try:
            payload = self._get("/api/v3/exchangeInfo")
        except Exception as exc:
            print(f"⚠️ No se pudo obtener exchangeInfo publico de Binance: {type(exc).__name__}: {exc}")
            return {}
        filas = payload.get("symbols", ()) if isinstance(payload, dict) else ()
        return {
            str(fila["symbol"]): fila
            for fila in filas or ()
            if isinstance(fila, dict) and fila.get("symbol")
        }

    def get_price_snapshot(self, medicion=None) -> dict[str, float]:
        try:
            filas = self._get("/api/v3/ticker/price")
        except Exception as exc:
            print(f"⚠️ No se pudo obtener snapshot publico de Binance: {type(exc).__name__}: {exc}")
            return {}
        snapshot = {}
        for fila in filas or ():
            try:
                snapshot[str(fila["symbol"])] = float(fila["price"])
            except (KeyError, TypeError, ValueError):
                continue
        return snapshot

    def get_market_metrics(self, medicion=None) -> dict[str, dict[str, Any]]:
        try:
            filas = self._get("/api/v3/ticker/24hr")
        except Exception as exc:
            print(f"⚠️ No se pudieron obtener metricas publicas de Binance: {type(exc).__name__}: {exc}")
            return {}
        salida = {}
        for fila in filas or ():
            if isinstance(fila, dict) and fila.get("symbol"):
                salida[str(fila["symbol"])] = fila
        return salida

    def get_recent_klines(self, symbol: str, *, interval="1h", limit=1000, medicion=None):
        try:
            filas = self._get(
                "/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": int(limit)},
            )
        except Exception as exc:
            print(f"⚠️ No se pudieron obtener velas publicas de {symbol}: {type(exc).__name__}: {exc}")
            return []
        return filas if isinstance(filas, list) else []

    def get_order_book(self, symbol: str, *, limit=100, medicion=None):
        try:
            libro = self._get(
                "/api/v3/depth",
                params={"symbol": symbol, "limit": int(limit)},
            )
        except Exception as exc:
            print(f"⚠️ No se pudo obtener profundidad publica de {symbol}: {type(exc).__name__}: {exc}")
            return {}
        return libro if isinstance(libro, dict) else {}
