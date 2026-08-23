from backend.economia.fuente_0xarchive_04h1 import (
    WINDOW_DAYS_0XARCHIVE_04H1,
    coverage_04h1,
    fetch_price_history_04h1,
    parse_price_point_04h1,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, text="", headers=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_parse_price_point_acepta_schema_snake_case():
    p = parse_price_point_04h1({
        "timestamp": "2024-01-01T00:00:00Z",
        "mark_price": "42000.1",
        "oracle_price": "41999.9",
        "mid_price": "42000.0",
    })
    assert p.timestamp_ms == 1704067200000
    assert p.mark_price == 42000.1
    assert p.oracle_price == 41999.9
    assert p.mid_price == 42000.0


def test_fetch_price_history_pagina_y_no_expone_key():
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        cursor = kwargs["params"].get("cursor")
        if cursor is None:
            return FakeResponse({
                "data": [{
                    "timestamp": "2024-01-01T00:00:00Z",
                    "mark_price": "42000",
                    "oracle_price": "42001",
                    "mid_price": "42000.5",
                }],
                "meta": {"next_cursor": "next-1"},
            })
        return FakeResponse({
            "data": [{
                "timestamp": "2024-01-01T01:00:00Z",
                "mark_price": "42010",
                "oracle_price": "42011",
                "mid_price": "42010.5",
            }],
            "meta": {"next_cursor": None},
        })

    points = fetch_price_history_04h1(
        "BTC",
        1704067200000,
        1704074400000,
        "secret-read-only-key",
        request_get=fake_get,
    )
    assert len(points) == 2
    assert len(calls) == 2
    assert calls[0][0].endswith("/v1/hyperliquid/prices/BTC")
    assert calls[0][1]["headers"]["X-API-Key"] == "secret-read-only-key"
    assert "secret-read-only-key" not in str(calls[0][1]["params"])


def test_fetch_price_history_divide_rango_en_ventanas_y_luego_oi_exacto():
    calls = []
    day = 86_400_000
    start = 1704067200000
    end = start + 65 * day

    def fake_get(url, **kwargs):
        params = kwargs["params"]
        calls.append((url, params["start"], params["end"]))
        # Una observación exactamente al inicio de cada ventana: fuerza fallback OI.
        return FakeResponse({
            "data": [{
                "timestamp": params["start"],
                "mark_price": "100",
                "oracle_price": "100",
            }],
            "meta": {},
        })

    points = fetch_price_history_04h1("BTC", start, end, "k", request_get=fake_get)
    assert WINDOW_DAYS_0XARCHIVE_04H1 == 30
    expected_windows = [
        (start, start + 30 * day),
        (start + 30 * day, start + 60 * day),
        (start + 60 * day, end),
    ]
    assert [(lo, hi) for _, lo, hi in calls[:3]] == expected_windows
    assert all("/v1/hyperliquid/prices/BTC" in url for url, _, _ in calls[:3])
    assert [(lo, hi) for _, lo, hi in calls[3:]] == expected_windows
    assert all("/v1/hyperliquid/openinterest/BTC" in url for url, _, _ in calls[3:])
    assert len(points) == 3
    assert len({p.timestamp_ms for p in points}) == 3


def test_fetch_price_history_subdivide_400_hasta_funcionar():
    start = 1704067200000
    end = start + 4 * 86_400_000
    calls = []

    def fake_get(url, **kwargs):
        lo, hi = kwargs["params"]["start"], kwargs["params"]["end"]
        calls.append((lo, hi))
        if hi - lo > 2 * 86_400_000:
            return FakeResponse({"error": "range too large"}, status_code=400)
        return FakeResponse({
            "data": [{"timestamp": lo, "mark_price": "10", "oracle_price": "10"}],
            "meta": {},
        })

    points = fetch_price_history_04h1("BTC", start, end, "k", request_get=fake_get)
    assert len(points) == 2
    assert calls[0] == (start, end)
    assert calls[1][0] == start
    assert calls[2][1] == end


def test_fetch_price_history_rechaza_duplicados():
    def fake_get(url, **kwargs):
        return FakeResponse({
            "data": [
                {"timestamp": 1704067200000, "mark_price": "1", "oracle_price": "1"},
                {"timestamp": 1704067200000, "mark_price": "1", "oracle_price": "1"},
            ],
            "meta": {},
        })

    try:
        fetch_price_history_04h1(
            "BTC", 1704067200000, 1704074400000, "k", request_get=fake_get
        )
    except ValueError as exc:
        assert str(exc) == "OXARCHIVE_DUPLICATE_TIMESTAMP"
    else:
        raise AssertionError("duplicate timestamp must fail closed")


def test_coverage_04h1():
    rows = [
        parse_price_point_04h1({
            "timestamp": 1704067200000 + i * 3600000,
            "mark_price": "10",
            "oracle_price": "10",
        })
        for i in range(99)
    ]
    assert coverage_04h1(rows, 100) == 0.99
