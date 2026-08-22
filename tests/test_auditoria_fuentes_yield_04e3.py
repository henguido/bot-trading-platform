from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.economia.auditoria_fuentes_yield_04e3 import (
    ObjetoS3_04E3,
    evaluar_options_04e3,
    extraer_fecha_key_04e3,
    parse_s3_page_04e3,
)
from backend.economia.protocolo_fuentes_yield_04e3 import (
    OPTIONS_STATUS_APTO_04E3,
    OPTIONS_STATUS_INCOMPLETO_04E3,
)


def test_parse_s3_page_con_paginacion():
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>
      <IsTruncated>true</IsTruncated>
      <Contents><Key>data/option/daily/EOHSummary/a-2022-01-01.zip</Key><Size>123</Size></Contents>
      <NextContinuationToken>abc</NextContinuationToken>
    </ListBucketResult>"""
    rows, truncated, token = parse_s3_page_04e3(xml)
    assert truncated is True
    assert token == "abc"
    assert len(rows) == 1
    assert rows[0].size == 123


def test_extraer_fecha_usa_ultima_fecha_y_rechaza_invalida():
    assert extraer_fecha_key_04e3("x/2022-01-01/y-2023-05-12.zip") == date(2023, 5, 12)
    assert extraer_fecha_key_04e3("sin-fecha.zip") is None
    with pytest.raises(ValueError, match="fecha inválida"):
        extraer_fecha_key_04e3("x-2023-02-31.zip")


def _objetos_completos() -> list[ObjetoS3_04E3]:
    out = []
    for year in (2022, 2023, 2024, 2025):
        d = date(year, 1, 1)
        for i in range(350):
            day = d + timedelta(days=i)
            out.append(ObjetoS3_04E3(f"data/option/daily/EOHSummary/EOH-{day.isoformat()}.zip", 100 + i))
    return out


def test_options_apto_con_350_dias_por_anio():
    result = evaluar_options_04e3(_objetos_completos(), pages=2, listings_complete=True)
    assert result.apt is True
    assert result.status == OPTIONS_STATUS_APTO_04E3
    assert dict(result.days_by_year) == {2022: 350, 2023: 350, 2024: 350, 2025: 350}
    assert result.zero_size_zip_objects == 0
    assert result.duplicate_keys == 0
    assert result.compressed_bytes_2022_2025 > 0


def test_options_incompleto_por_cobertura_zero_size_y_listado():
    rows = _objetos_completos()
    rows = [row for row in rows if "2022-12" not in row.key]
    rows.append(ObjetoS3_04E3("data/option/daily/EOHSummary/EOH-2025-12-31.zip", 0))
    result = evaluar_options_04e3(rows, pages=20, listings_complete=False)
    assert result.apt is False
    assert result.status == OPTIONS_STATUS_INCOMPLETO_04E3
    assert "LISTADO_S3_INCOMPLETO" in result.reasons
    assert "ZIPS_TAMANO_CERO" in result.reasons
    assert any(reason.startswith("COBERTURA_2022_MENOR_") for reason in result.reasons)
