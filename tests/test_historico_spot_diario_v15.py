from backend.economia.historico_spot_diario_v15 import DIA_MS, descargar_spot_diario_v15

T0 = 1640995200000


def _fila(ts, close="105"):
    return [ts, "100", "110", "90", close, "1", ts + DIA_MS - 1, "100", 5, "0.5", "50", "0"]


class Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_descarga_spot_1d_pagina_y_valida_sin_auth():
    llamadas = []

    def get(url, *, params, timeout):
        llamadas.append((url, dict(params), timeout))
        if params["startTime"] == T0:
            return Resp([_fila(T0), _fila(T0 + DIA_MS)])
        return Resp([_fila(T0 + 2 * DIA_MS, "106")])

    r = descargar_spot_diario_v15(
        "BTCUSDT", start_ms=T0, end_ms=T0 + 3 * DIA_MS,
        limit=2, http_get=get,
    )
    assert r.completa is True
    assert r.n_requests == 2
    assert len(r.barras) == 3
    assert r.barras[-1].close.as_tuple() == __import__("decimal").Decimal("106").as_tuple()
    assert all("signature" not in p and "apiKey" not in p for _, p, _ in llamadas)


def test_fallo_en_segunda_pagina_invalida_toda_la_serie():
    n = 0

    def get(url, *, params, timeout):
        nonlocal n
        n += 1
        if n == 1:
            return Resp([_fila(T0), _fila(T0 + DIA_MS)])
        return Resp([], 500)

    r = descargar_spot_diario_v15(
        "BTCUSDT", start_ms=T0, end_ms=T0 + 3 * DIA_MS,
        limit=2, http_get=get,
    )
    assert r.completa is False
    assert r.barras == ()
    assert r.n_requests == 2


def test_payload_no_lista_falla_cerrado():
    r = descargar_spot_diario_v15(
        "BTCUSDT", start_ms=T0, end_ms=T0 + DIA_MS,
        http_get=lambda *a, **k: Resp({"oops": True}),
    )
    assert r.completa is False
    assert r.barras == ()


def test_parametros_invalidos_se_rechazan_antes_de_red():
    try:
        descargar_spot_diario_v15("BTC-USDT", start_ms=T0, end_ms=T0 + DIA_MS)
    except ValueError as exc:
        assert "symbol" in str(exc)
    else:
        raise AssertionError("debio rechazar symbol")
