import io
import zipfile
from datetime import timedelta
from decimal import Decimal

import pytest

from backend.economia.auditoria_derivados_v14 import auditar_derivados_v14
from backend.economia.historico_derivados_v14 import (
    PremiumDiarioV14,
    descargar_premium_mes_v14,
    parsear_premium_csv_v14,
)
from backend.economia.protocolo_derivados_v14 import (
    DESDE_V14,
    DIAS_ESPERADOS_V14,
    MIN_SIMBOLOS_POR_DIA_V14,
)


def _zip(csv_text: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("x.csv", csv_text)
    return b.getvalue()


def test_parser_acepta_cabecera_y_premium_negativo():
    t = int(DESDE_V14.timestamp() * 1000)
    filas = (
        "open_time,open,high,low,close,volume\n"
        f"{t},-0.001,-0.0005,-0.002,-0.0015,0\n"
    ).encode()
    r = parsear_premium_csv_v14(filas)
    assert len(r) == 1
    assert r[0].open == Decimal("-0.001")
    assert r[0].close == Decimal("-0.0015")


def test_parser_normaliza_microsegundos():
    t_ms = int(DESDE_V14.timestamp() * 1000)
    r = parsear_premium_csv_v14(
        f"{t_ms * 1000},0.001,0.002,0.0005,0.0015\n".encode()
    )
    assert r[0].open_time_ms == t_ms


def test_parser_rechaza_ohlc_inconsistente_y_duplicados():
    t = int(DESDE_V14.timestamp() * 1000)
    with pytest.raises(ValueError, match="OHLC"):
        parsear_premium_csv_v14(f"{t},0.1,0.05,0.0,0.1\n".encode())
    with pytest.raises(ValueError, match="duplicados"):
        parsear_premium_csv_v14(
            (f"{t},0,1,-1,0\n" f"{t},0,1,-1,0\n").encode()
        )


def test_descarga_404_queda_explicita_y_no_inventa_barras():
    class R:
        status_code = 404
        content = b""
        def raise_for_status(self):
            raise AssertionError("no debe llamarse para 404")
    r = descargar_premium_mes_v14("BTCUSDT", 2022, 1, http_get=lambda *a, **k: R())
    assert not r.completa
    assert r.status_http == 404
    assert r.error == "NO_ENCONTRADO"
    assert r.barras == ()


def test_descarga_zip_valido():
    t = int(DESDE_V14.timestamp() * 1000)
    contenido = _zip(f"{t},0,0.001,-0.001,0.0002\n")
    class R:
        status_code = 200
        content = contenido
        def raise_for_status(self): pass
    r = descargar_premium_mes_v14("BTCUSDT", 2022, 1, http_get=lambda *a, **k: R())
    assert r.completa
    assert len(r.barras) == 1


def _serie_completa():
    out = []
    d = DESDE_V14
    for _ in range(DIAS_ESPERADOS_V14):
        t = int(d.timestamp() * 1000)
        out.append(PremiumDiarioV14(t, Decimal("0"), Decimal("0.001"), Decimal("-0.001"), Decimal("0")))
        d += timedelta(days=1)
    return tuple(out)


def test_auditoria_aprueba_15_series_completas():
    series = {f"S{i:02d}USDT": _serie_completa() for i in range(MIN_SIMBOLOS_POR_DIA_V14)}
    a = auditar_derivados_v14(series)
    assert a.n_simbolos_aptos == MIN_SIMBOLOS_POR_DIA_V14
    assert a.fraccion_cross_section_completa == Decimal("1")
    assert a.min_simbolos_en_dia == MIN_SIMBOLOS_POR_DIA_V14
    assert all(x.apto for x in a.anios)
    assert a.dataset_apto


def test_auditoria_rechaza_si_solo_14_simbolos_tienen_cobertura():
    series = {f"S{i:02d}USDT": _serie_completa() for i in range(MIN_SIMBOLOS_POR_DIA_V14 - 1)}
    a = auditar_derivados_v14(series)
    assert not a.dataset_apto
    assert "SIMBOLOS_APTOS_INSUFICIENTES" in a.motivos_rechazo
    assert "COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE" in a.motivos_rechazo


def test_gap_se_reporta_sin_rellenar():
    serie = list(_serie_completa())
    del serie[100:103]
    a = auditar_derivados_v14({"BTCUSDT": tuple(serie)})
    c = a.simbolos[0]
    assert c.n_dias == DIAS_ESPERADOS_V14 - 3
    assert c.n_gaps == 1
    assert c.max_gap_dias == 3
