import io
import zipfile

from backend.economia.historico_perp_v16 import descargar_perp_mes_v16, parsear_perp_csv_v16

T0 = 1640995200000
DIA = 86_400_000


def _csv():
    return (
        "open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_base,taker_quote,ignore\n"
        f"{T0},100,110,90,105,10,{T0 + DIA - 1},1000,20,5,500,0\n"
        f"{T0 + DIA},105,115,95,110,11,{T0 + 2*DIA - 1},1100,21,6,600,0\n"
    ).encode()


def _zip_bytes(data):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        z.writestr("BTCUSDT-1d-2022-01.csv", data)
    return bio.getvalue()


class Resp:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_parsea_futures_kline_oficial_con_cabecera():
    velas = parsear_perp_csv_v16(_csv())
    assert len(velas) == 2
    assert velas[0].open_time_ms == T0
    assert str(velas[0].close) == "105"


def test_descarga_zip_valido_sin_auth():
    urls = []
    def get(url, *, timeout):
        urls.append(url)
        return Resp(_zip_bytes(_csv()))
    r = descargar_perp_mes_v16("BTCUSDT", 2022, 1, http_get=get)
    assert r.completa is True
    assert len(r.velas) == 2
    assert "/futures/um/monthly/klines/BTCUSDT/1d/" in urls[0]


def test_404_es_ausencia_explicita():
    r = descargar_perp_mes_v16(
        "BNBUSDT", 2022, 1,
        http_get=lambda *a, **k: Resp(status=404),
    )
    assert r.completa is False
    assert r.status_http == 404
    assert r.velas == ()
    assert r.error == "NO_ENCONTRADO"


def test_ohlc_invalido_falla_cerrado():
    bad = f"{T0},100,99,90,105,10,{T0 + DIA - 1},1000,20,5,500,0\n".encode()
    r = descargar_perp_mes_v16(
        "BTCUSDT", 2022, 1,
        http_get=lambda *a, **k: Resp(_zip_bytes(bad)),
    )
    assert r.completa is False
    assert r.velas == ()
