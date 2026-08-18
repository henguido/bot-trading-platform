"""Pruebas de validacion 04B-v2 y fixtures sinteticos corregidos."""
from __future__ import annotations

from decimal import Decimal

import backend.economia.experimento_edge_v2 as exp
from backend.economia.edge_celdas import NO_DISPONIBLE, ajustar_modelo_celdas, estimar_edge_celdas
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_relativo_v2 import (
    NOMBRES_FEATURES_RELATIVAS_V2,
    EstadoRelativoV2,
    ObservacionRelativaV2,
    vector_relativo_v2,
)
from backend.economia.protocolo_edge_v2 import (
    FOLDS_VALIDACION_ENE_ABR_2026,
    TEST_DESDE_MS,
    ConfiguracionRelativaV2,
)
from backend.economia.walk_forward_celdas import ResultadoFoldCeldas, ResultadoWalkForwardCeldas


def obs(symbol, ts, *, rank="0.10", regimen="0.00", retorno="0.01"):
    r = Decimal(retorno)
    estado = EstadoRelativoV2(
        symbol=symbol,
        timestamp_ms=ts,
        close=Decimal("100"),
        rank_retorno_4h=Decimal(rank),
        rank_retorno_24h=Decimal(rank),
        rank_sorpresa_volumen_4h=Decimal(rank),
        mediana_retorno_24h_mercado=Decimal(regimen),
    )
    return ObservacionRelativaV2(
        estado=estado,
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=4,
            retorno_cierre=r,
            mfe=max(Decimal("0"), r),
            mae=min(Decimal("0"), r),
        ),),
    )


def estado_consulta(ts=1000, *, rank="0.10", regimen="0.00"):
    return EstadoRelativoV2(
        symbol="LIVEUSDT",
        timestamp_ms=ts,
        close=Decimal("100"),
        rank_retorno_4h=Decimal(rank),
        rank_retorno_24h=Decimal(rank),
        rank_sorpresa_volumen_4h=Decimal(rank),
        mediana_retorno_24h_mercado=Decimal(regimen),
    )


def ajustar(datos, *, min_muestras=3, min_symbols=3, min_timestamps=3):
    return ajustar_modelo_celdas(
        datos,
        horizonte_horas=4,
        n_bins=2,
        min_muestras=min_muestras,
        min_symbols=min_symbols,
        min_timestamps=min_timestamps,
        max_radio=0,
        nombres_features=NOMBRES_FEATURES_RELATIVAS_V2,
        bins_por_feature=(2, 2, 2, 2),
        vectorizador=vector_relativo_v2,
    )


def test_fixture_cluster_positivo_tiene_tres_simbolos_para_min_symbols_tres():
    datos = [
        obs("A", 1, rank="0.10", retorno="0.03"),
        obs("B", 2, rank="0.10", retorno="0.02"),
        obs("C", 3, rank="0.10", retorno="0.01"),
        obs("X", 4, rank="0.90", retorno="-0.03"),
        obs("Y", 5, rank="0.90", retorno="-0.02"),
        obs("Z", 6, rank="0.90", retorno="-0.01"),
    ]
    modelo = ajustar(datos, min_muestras=3, min_symbols=3, min_timestamps=3)
    estimacion = estimar_edge_celdas(modelo, estado_consulta())
    assert estimacion.disponible
    assert estimacion.n_symbols_unicos == 3
    assert estimacion.retorno_esperado > 0


def test_soporte_insuficiente_se_prueba_sin_hacer_fallar_el_fit():
    datos = [
        obs("A", 1, rank="0.10"),
        obs("B", 2, rank="0.10"),
        obs("C", 3, rank="0.10"),
        obs("X", 4, rank="0.90"),
        obs("Y", 5, rank="0.90"),
        obs("Z", 6, rank="0.90"),
    ]
    # Train total = 6 y min_muestras = 4, asi que el modelo ajusta.
    # La celda consultada solo tiene 3 muestras, por eso falla en estimacion.
    modelo = ajustar(datos, min_muestras=4, min_symbols=3, min_timestamps=3)
    estimacion = estimar_edge_celdas(modelo, estado_consulta())
    assert estimacion.estado == NO_DISPONIBLE
    assert estimacion.motivo == "soporte_insuficiente"
    assert estimacion.n_muestras == 3


def pred(symbol, ts, predicho, real):
    from backend.economia.evaluacion_celdas import PrediccionCeldas
    return PrediccionCeldas(
        symbol, ts, Decimal(predicho), Decimal(real),
        0, 30, 3, 20, Decimal("0.34"), Decimal("0.05"))


def resultado_sintetico(*, cobertura="1", uplift_cs="0.01",
                         frac_ts_cs="0.60", meses_cs=4, meses_pos=3,
                         folds_positivos=4):
    folds = []
    for i, f in enumerate(FOLDS_VALIDACION_ENE_ABR_2026):
        predicciones = []
        for j in range(15):
            predicho = Decimal("0.015") - Decimal(j) / Decimal("10000")
            real = Decimal("0.010") - Decimal(j) / Decimal("10000")
            if i >= folds_positivos:
                real = -real
            predicciones.append(pred(f"S{j:02d}", f.valid_desde_ms + 1, predicho, real))
        folds.append(ResultadoFoldCeldas(
            f, 300, 75, 90, 15, 4, "DISPONIBLE", tuple(predicciones), None))
    return ResultadoWalkForwardCeldas(
        horizonte_horas=4, n_bins=3, min_muestras=30,
        min_symbols=3, min_timestamps=20, max_radio=1,
        folds=tuple(folds), n_folds_disponibles=4,
        n_objetivo=100, n_estimadas=int(Decimal(cobertura) * 100),
        cobertura=Decimal(cobertura),
        retorno_real_objetivo_medio=Decimal("0"),
        retorno_real_estimadas_medio=Decimal("0"),
        sesgo_seleccion_cobertura=Decimal("0"),
        mae_prediccion=Decimal("0.01"),
        exactitud_direccional=Decimal("0.55"),
        retorno_real_top25_predicho=Decimal("0.02"),
        uplift_top25_vs_estimadas=Decimal("0.01"),
        uplift_top25_vs_objetivo=Decimal("0.01"),
        radio_p95=1.0,
        max_symbol_share_p95=0.34,
        max_timestamp_share_p95=0.05,
        n_timestamps_cross_section=100,
        uplift_cross_section_medio=Decimal(uplift_cs),
        fraccion_timestamps_uplift_positivo=Decimal(frac_ts_cs),
        n_meses_cross_section=meses_cs,
        meses_uplift_positivo=meses_pos,
        uplift_mensual_min=Decimal("-0.01"),
        uplift_mensual_p25=Decimal("0.001"),
        uplift_mensual_p50=Decimal("0.01"),
    )


def test_criterios_v2_exigen_cross_section_estable():
    pasa, motivos, folds_cs = exp._aplicar_criterios_v2(
        resultado_sintetico(
            cobertura="0.49", uplift_cs="0", frac_ts_cs="0.49",
            meses_cs=3, meses_pos=2, folds_positivos=2,
        ),
        min_activos_cross_section=15,
    )
    assert folds_cs == 2
    assert not pasa
    assert "COBERTURA_INSUFICIENTE" in motivos
    assert "SIN_UPLIFT_CROSS_SECTION" in motivos
    assert "CROSS_SECTION_INESTABLE_TIMESTAMPS" in motivos
    assert "COBERTURA_MENSUAL_CROSS_SECTION_INSUFICIENTE" in motivos
    assert "UPLIFT_CROSS_SECTION_INESTABLE_MENSUAL" in motivos
    assert "UPLIFT_CROSS_SECTION_INESTABLE_FOLDS" in motivos


def test_validacion_v2_elimina_holdout_final_antes_de_evaluar(monkeypatch):
    vistos = []

    def fake(observaciones, **kwargs):
        datos = tuple(observaciones)
        vistos.extend(o.estado.timestamp_ms for o in datos)
        assert all(t < TEST_DESDE_MS for t in vistos)
        return resultado_sintetico()

    monkeypatch.setattr(exp, "evaluar_walk_forward_celdas", fake)
    config = ConfiguracionRelativaV2(4, 3, 3, 30, 1)
    datos = [obs("A", TEST_DESDE_MS - 1), obs("B", TEST_DESDE_MS)]
    r = exp.evaluar_validacion_v2_predeclarada(datos, configuraciones=[config])
    assert vistos == [TEST_DESDE_MS - 1]
    assert r.n_observaciones_pre_test == 1
