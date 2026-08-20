from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.economia.auditoria_posicionamiento_v20 import auditar_posicionamiento_v20
from backend.economia.historico_posicionamiento_v20 import (
    ArchivoMetricasV20,
    CampoCalidadV20,
    ListadoMetricasV20,
    ResumenArchivoMetricasV20,
)
from backend.economia.protocolo_posicionamiento_v20 import (
    CAMPOS_CORE_OI_V20,
    CAMPOS_RATIOS_V20,
    DESARROLLO_2026_ABIERTO_V20,
    DESDE_V20,
    DIAS_ESPERADOS_V20,
    TEST_MAY_JUL_ABIERTO_V20,
    UNIVERSO_POSICIONAMIENTO_V20,
)


def _key(symbol, fecha):
    return f"data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{fecha.isoformat()}.zip"


def _listado(symbol, n_dias=DIAS_ESPERADOS_V20):
    base = DESDE_V20.date()
    archivos = tuple(
        ArchivoMetricasV20(symbol, base + timedelta(days=i), _key(symbol, base + timedelta(days=i)), 100)
        for i in range(n_dias)
    )
    return ListadoMetricasV20(symbol, archivos, True, 2, None)


def _campos(*, ratio_invalido=None, core_positivos=288):
    out = []
    for nombre in CAMPOS_CORE_OI_V20 + CAMPOS_RATIOS_V20:
        if nombre == ratio_invalido:
            out.append(CampoCalidadV20(nombre, 288, 0, 0))
        elif nombre in CAMPOS_CORE_OI_V20:
            out.append(CampoCalidadV20(nombre, 288, 288, core_positivos))
        else:
            out.append(CampoCalidadV20(nombre, 288, 288, 288))
    return tuple(out)


def _muestras(*, ratio_invalido=None, n_5m=287, core_positivos=288, no_ascendentes=0, duplicados=0):
    out = []
    for symbol in UNIVERSO_POSICIONAMIENTO_V20:
        for year in (2022, 2023, 2024, 2025):
            for month in range(1, 13):
                fecha = date(year, month, 15)
                out.append(ResumenArchivoMetricasV20(
                    symbol=symbol,
                    fecha=fecha,
                    key=_key(symbol, fecha),
                    completa=True,
                    n_filas=288,
                    primer_ts_ms=1,
                    ultimo_ts_ms=2,
                    duplicados=duplicados,
                    no_ascendentes=no_ascendentes,
                    n_deltas=287,
                    n_deltas_5m=n_5m,
                    campos=_campos(ratio_invalido=ratio_invalido, core_positivos=core_positivos),
                    error=None,
                ))
    return tuple(out)


def test_dataset_completo_core_sano_es_apto():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    r = auditar_posicionamiento_v20(listados, _muestras())
    assert r.dataset_apto is True
    assert r.core_oi_apto is True
    assert r.n_simbolos_aptos == 20
    assert r.fraccion_cross_section_completa == 1
    assert r.fraccion_muestras_parseadas == 1
    assert r.fraccion_cadencia_5m == 1
    assert set(r.campos_ratios_usables) == set(CAMPOS_RATIOS_V20)


def test_ratio_historicamente_incompleto_se_reporta_sin_corromper_core_oi():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    faltante = "sum_toptrader_long_short_ratio"
    r = auditar_posicionamiento_v20(listados, _muestras(ratio_invalido=faltante))
    assert r.dataset_apto is True
    assert r.core_oi_apto is True
    assert faltante not in r.campos_ratios_usables
    campo = next(c for c in r.campos if c.nombre == faltante)
    assert campo.fraccion_valida == 0
    assert campo.usable is False


def test_catorce_simbolos_no_alcanzan_cobertura_cross_section():
    listados = {}
    for i, s in enumerate(UNIVERSO_POSICIONAMIENTO_V20):
        listados[s] = _listado(s) if i < 14 else ListadoMetricasV20(s, (), True, 1, None)
    r = auditar_posicionamiento_v20(listados, _muestras())
    assert r.dataset_apto is False
    assert "SIMBOLOS_ARCHIVO_APTOS_INSUFICIENTES" in r.motivos_rechazo
    assert "COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE" in r.motivos_rechazo


def test_core_oi_con_demasiados_ceros_falla_aunque_archivo_este_completo():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    r = auditar_posicionamiento_v20(listados, _muestras(core_positivos=280))
    assert r.dataset_apto is False
    assert r.core_oi_apto is False
    assert "CORE_OPEN_INTEREST_NO_APTO" in r.motivos_rechazo


def test_cadencia_degradada_falla_sin_rellenar_snapshots():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    r = auditar_posicionamiento_v20(listados, _muestras(n_5m=250))
    assert r.dataset_apto is False
    assert r.fraccion_cadencia_5m < 0.95
    assert "CADENCIA_5M_INSUFICIENTE" in r.motivos_rechazo


def test_v20_estricto_sigue_rechazando_orden_fisico_no_ascendente():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    r = auditar_posicionamiento_v20(listados, _muestras(no_ascendentes=1))
    assert r.dataset_apto is False
    assert "TIMESTAMPS_NO_ASCENDENTES_EN_MUESTRA" in r.motivos_rechazo


def test_v20a_acepta_reorden_canonico_pero_no_duplicados():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    orden = auditar_posicionamiento_v20(
        listados,
        _muestras(no_ascendentes=2),
        rechazar_no_ascendentes=False,
    )
    assert orden.dataset_apto is True
    assert orden.no_ascendentes_muestra > 0
    assert "TIMESTAMPS_NO_ASCENDENTES_EN_MUESTRA" not in orden.motivos_rechazo

    duplicados = auditar_posicionamiento_v20(
        listados,
        _muestras(no_ascendentes=2, duplicados=1),
        rechazar_no_ascendentes=False,
    )
    assert duplicados.dataset_apto is False
    assert "TIMESTAMPS_DUPLICADOS_EN_MUESTRA" in duplicados.motivos_rechazo


def test_parametro_normalizacion_debe_ser_booleano():
    listados = {s: _listado(s) for s in UNIVERSO_POSICIONAMIENTO_V20}
    with pytest.raises(ValueError, match="bool"):
        auditar_posicionamiento_v20(listados, _muestras(), rechazar_no_ascendentes=1)


def test_v20_no_abre_2026_ni_holdout_final():
    assert DESARROLLO_2026_ABIERTO_V20 is False
    assert TEST_MAY_JUL_ABIERTO_V20 is False
