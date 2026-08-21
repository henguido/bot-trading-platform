from backend.economia.auditoria_carry_04c0 import (
    ObjetoS3Carry04C0,
    _dated_objects,
    _expiry,
    _parse_s3,
    listar_prefix_04c0,
)


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def _xml(contents, *, truncated=False, token=None):
    rows = "".join(
        f"<Contents><Key>{key}</Key><Size>{size}</Size></Contents>" for key, size in contents
    )
    next_token = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    return (
        f"<?xml version='1.0'?><ListBucketResult>{rows}"
        f"<IsTruncated>{str(truncated).lower()}</IsTruncated>{next_token}</ListBucketResult>"
    ).encode()


def test_expiry_dated_valida_y_filtra_ventana():
    assert _expiry("BTCUSDT_250926")[1].isoformat() == "2025-09-26"
    assert _expiry("ETHUSDT_221230")[0] == "ETH"
    assert _expiry("BTCUSDT") is None
    assert _expiry("BTCUSDT_260925") is None


def test_parse_s3_extrae_key_y_size():
    objetos, truncado, token = _parse_s3(
        _xml([("data/test.zip", 123)], truncated=True, token="abc")
    )
    assert objetos == (ObjetoS3Carry04C0("data/test.zip", 123),)
    assert truncado is True
    assert token == "abc"


def test_listar_prefix_pagina_sin_perder_objetos():
    pages = [
        _xml([("data/a.zip", 1)], truncated=True, token="next"),
        _xml([("data/b.zip", 2)], truncated=False),
    ]
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, dict(params), timeout))
        return FakeResponse(pages[len(calls) - 1])

    result = listar_prefix_04c0("data/futures/um/monthly/klines/BTCUSDT_", http_get=fake_get)
    assert result.completo is True
    assert result.n_requests == 2
    assert [o.key for o in result.objetos] == ["data/a.zip", "data/b.zip"]
    assert calls[1][1]["continuation-token"] == "next"


def test_dated_objects_acepta_solo_1h_zip_positivo_y_2022_2025():
    objetos = (
        ObjetoS3Carry04C0(
            "data/futures/um/monthly/klines/BTCUSDT_250926/1h/BTCUSDT_250926-1h-2025-08.zip",
            100,
        ),
        ObjetoS3Carry04C0(
            "data/futures/um/monthly/klines/BTCUSDT_250926/5m/BTCUSDT_250926-5m-2025-08.zip",
            100,
        ),
        ObjetoS3Carry04C0(
            "data/futures/um/monthly/klines/BTCUSDT_250926/1h/BTCUSDT_250926-1h-2025-09.zip",
            0,
        ),
        ObjetoS3Carry04C0(
            "data/futures/um/monthly/klines/BTCUSDT_260925/1h/BTCUSDT_260925-1h-2026-08.zip",
            100,
        ),
    )
    parsed = _dated_objects(objetos, "klines")
    assert list(parsed) == ["BTCUSDT_250926"]
    assert parsed["BTCUSDT_250926"] == [(2025, 8, 100)]
