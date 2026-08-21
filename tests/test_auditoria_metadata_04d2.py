from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

from backend.economia.auditoria_metadata_04d2 import (
    Credenciales04D2,
    construir_query_firmada_04d2,
    ejecutar_auditoria_metadata_04d2,
)
from backend.economia.protocolo_metadata_04d2 import (
    STATUS_APTA_04D2,
    STATUS_NO_CREDS_04D2,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return FakeResponse({"ok": True})


class ForbiddenSession:
    def get(self, *args, **kwargs):
        raise AssertionError("no debe haber red sin opt-in/credenciales")


def test_signature_es_determinista():
    query = construir_query_firmada_04d2(
        {"symbol": "BTCUSDT"}, "secret-sintetico", timestamp_ms=1700000000000
    )
    base = urlencode(sorted({
        "symbol": "BTCUSDT", "recvWindow": "5000", "timestamp": "1700000000000"
    }.items()))
    expected = hmac.new(b"secret-sintetico", base.encode(), hashlib.sha256).hexdigest()
    assert query == f"{base}&signature={expected}"


def test_sin_credenciales_no_hace_red(monkeypatch):
    monkeypatch.delenv("ALLOW_04D2_ACCOUNT_READONLY", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    result = ejecutar_auditoria_metadata_04d2(session=ForbiddenSession())
    assert result.status == STATUS_NO_CREDS_04D2
    assert result.executed is False
    assert result.metadata == {}


def test_con_credenciales_sinteticas_solo_hace_gets_firmados():
    session = FakeSession()
    credentials = Credenciales04D2("key-sintetica", "secret-sintetico")
    result = ejecutar_auditoria_metadata_04d2(session=session, credentials=credentials)
    assert result.status == STATUS_APTA_04D2
    assert result.executed is True
    assert len(session.calls) == 8
    for url, headers, timeout in session.calls:
        assert "signature=" in url
        assert "timestamp=" in url
        assert headers == {"X-MBX-APIKEY": "key-sintetica"}
        assert "secret-sintetico" not in url
        assert timeout == 20
