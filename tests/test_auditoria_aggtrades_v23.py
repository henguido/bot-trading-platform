from __future__ import annotations

from backend.economia.auditoria_aggtrades_v23 import auditar_aggtrades_v23
from backend.economia.historico_aggtrades_v23 import (
    ArchivoAggTradesV23,
    ListadoAggTradesV23,
    listar_aggtrades_v23,
)
from backend.economia.protocolo_aggtrades_v23 import (
    DESARROLLO_2026_ABIERTO_V23,
    IMPUTACION_PERMITIDA_V23,
    MERCADOS_V23,
    TEST_MAY_JUL_ABIERTO_V23,
    UNIVERSO_AGGTRADES_V23,
    USA_RETORNOS_V23,
)


def _listado(mercado: str, symbol: str, *, omitir=()):
    omitidos = set(omitir)
    archivos = []
    for year in range(2022, 2026):
        for month in range(1, 13):
            if (year, month) in omitidos:
                continue
            key = (
                f"data/{'spot' if mercado == 'spot' else 'futures/um'}"
                f"/monthly/aggTrades/{symbol}/{symbol}-aggTrades-"
                f"{year:04d}-{month:02d}.zip"
            )
            archivos.append(
                ArchivoAggTradesV23(
                    mercado=mercado,
                    symbol=symbol,
                    year=year,
                    month=month,
                    key=key,
                    size=100,
                )
            )
    return ListadoAggTradesV23(
        mercado=mercado,
        symbol=symbol,
        archivos=tuple(archivos),
        completa=True,
        n_requests=1,
        error=None,
    )


def _dataset(*, faltantes=None):
    faltantes = faltantes or {}
    return {
        (mercado, symbol): _listado(
            mercado,
            symbol,
            omitir=faltantes.get((mercado, symbol), ()),
        )
        for mercado in MERCADOS_V23
        for symbol in UNIVERSO_AGGTRADES_V23
    }


def test_v23_mantiene_2026_cerrado_y_no_usa_retornos():
    assert DESARROLLO_2026_ABIERTO_V23 is False
    assert TEST_MAY_JUL_ABIERTO_V23 is False
    assert IMPUTACION_PERMITIDA_V23 is False
    assert USA_RETORNOS_V23 is False


def test_dataset_completo_es_apto():
    audit = auditar_aggtrades_v23(_dataset())
    assert audit.dataset_apto is True
    assert audit.n_listados_completos == 40
    assert audit.n_simbolos_pareados_aptos == 20
    assert audit.meses_cross_section_pareada == 48
    assert audit.bytes_total == 20 * 2 * 48 * 100
    assert audit.motivos_rechazo == ()


def test_un_symbol_sin_cuatro_meses_sigue_dejando_cross_section_apta():
    symbol = UNIVERSO_AGGTRADES_V23[0]
    faltan = ((2022, 1), (2022, 2), (2022, 3), (2022, 4))
    audit = auditar_aggtrades_v23(
        _dataset(
            faltantes={
                ("spot", symbol): faltan,
                ("futures_um", symbol): faltan,
            }
        )
    )
    assert audit.dataset_apto is True
    cobertura = next(x for x in audit.simbolos_pareados if x.symbol == symbol)
    assert cobertura.apto is False
    assert audit.n_simbolos_pareados_aptos == 19


def test_catorce_simbolos_pareados_rechaza_dataset():
    faltantes = {}
    for symbol in UNIVERSO_AGGTRADES_V23[:6]:
        faltantes[("futures_um", symbol)] = tuple(
            (year, month)
            for year in range(2022, 2026)
            for month in range(1, 13)
        )
    audit = auditar_aggtrades_v23(_dataset(faltantes=faltantes))
    assert audit.dataset_apto is False
    assert "SIMBOLOS_PAREADOS_APTOS_INSUFICIENTES" in audit.motivos_rechazo
    assert "COBERTURA_CROSS_SECTION_PAREADA_GLOBAL_INSUFICIENTE" in audit.motivos_rechazo


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_listado_s3_filtra_2026_y_parsea_tamano():
    symbol = "BTCUSDT"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <IsTruncated>false</IsTruncated>
  <Contents>
    <Key>data/spot/monthly/aggTrades/{symbol}/{symbol}-aggTrades-2025-12.zip</Key>
    <Size>12345</Size>
  </Contents>
  <Contents>
    <Key>data/spot/monthly/aggTrades/{symbol}/{symbol}-aggTrades-2026-01.zip</Key>
    <Size>999</Size>
  </Contents>
</ListBucketResult>""".encode()

    def fake_get(*args, **kwargs):
        return _Resp(xml)

    listado = listar_aggtrades_v23("spot", symbol, http_get=fake_get)
    assert listado.completa is True
    assert len(listado.archivos) == 1
    assert listado.archivos[0].periodo == (2025, 12)
    assert listado.archivos[0].size == 12345
