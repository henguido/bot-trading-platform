"""Pruebas de validacion 04B-v4 con regimen absoluto."""
from __future__ import annotations

from decimal import Decimal

import backend.economia.experimento_edge_v4 as exp
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_relativo_v2 import EstadoRelativoV2, ObservacionRelativaV2
from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.evaluacion_regimen import evaluar_senales_regimen_cost_aware
from backend.economia.protocolo_edge_v4 import (
    FOLDS_VALIDACION_ENE_ABR_2026,
    TEST_DESDE_MS,
    ConfiguracionRegimenV4,
)
from backend.economia.walk_forward_celdas import ResultadoFoldCeldas, ResultadoWalkForwardCeldas


def pred(symbol: str, ts: int, *, predicho_bps, real_bps) -> PrediccionCeldas:
    return PrediccionCeldas(
        symbol=symbol,
        timestamp_ms=ts,
        predicho=Decimal(str(predicho_bps)) / Decimal("10000"),
        real=Decimal(str(real_bps)) / Decimal("10000"),
        radio_usado=0,
        n_muestras_soporte=30,
        n_symbols_soporte=3,
        n_timestamps_soporte=20,
        max_symbol_share=Decimal("0.34"),
        max_timestamp_share=Decimal("0.05"),
    )


def grupo(ts: int, *, top_predicho=30, top_real=40, resto_real=0):
    salida = [pred("S00", ts, predicho_bps=top_predicho, real_bps=top_real)]
    for i in range(1, 15):
        salida.append(pred(
            f"S{i:02d}",
            ts,
            predicho_bps=10 - i / 100,
            real_bps=resto_real,
        ))
    return salida


def resultado_modelo_sintetico(*, top_predicho=30, top_real=40):
    folds = []
    predicciones = []
    for fold in FOLDS_VALIDACION_ENE_ABR_2026:
        ps = tuple(grupo(
            fold.valid_desde_ms + 1,
            top_predicho=top_predicho,
            top_real=top_real,
        ))
        predicciones.extend(ps)
        folds.append(ResultadoFoldCeldas(
            fold=fold,
            n_train_crudo=300,
            n_train_no_solapado=75,
            n_validacion_cruda=90,
            n_validacion_no_solapada=15,
            n_descartadas_embargo=4,
            estado="DISPONIBLE",
            predicciones=ps,
            motivo=None,
        ))
    return ResultadoWalkForwardCeldas(
        horizonte_horas=8,
        n_bins=3,
        min_muestras=30,
        min_symbols=3,
        min_timestamps=20,
        max_radio=0,
        folds=tuple(folds),
        n_folds_disponibles=4,
        n_objetivo=len(predicciones),
        n_estimadas=len(predicciones),
        cobertura=Decimal("1"),
        retorno_real_objetivo_medio=Decimal("0"),
        retorno_real_estimadas_medio=Decimal("0"),
        sesgo_seleccion_cobertura=Decimal("0"),
        mae_prediccion=Decimal("0.01"),
        exactitud_direccional=Decimal("0.55"),
        retorno_real_top25_predicho=Decimal("0.02"),
        uplift_top25_vs_estimadas=Decimal("0.01"),
        uplift_top25_vs_objetivo=Decimal("0.01"),
        radio_p95=0.0,
        max_symbol_share_p95=0.34,
        max_timestamp_share_p95=0.05,
        n_timestamps_cross_section=4,
        uplift_cross_section_medio=Decimal("0.01"),
        fraccion_timestamps_uplift_positivo=Decimal("1"),
        n_meses_cross_section=4,
        meses_uplift_positivo=4,
        uplift_mensual_min=Decimal("0.01"),
        uplift_mensual_p25=Decimal("0.01"),
        uplift_mensual_p50=Decimal("0.01"),
    )


def obs(symbol, ts, *, regimen_bps=0):
    estado = EstadoRelativoV2(
        symbol=symbol,
        timestamp_ms=ts,
        close=Decimal("100"),
        rank_retorno_4h=Decimal("0.5"),
        rank_retorno_24h=Decimal("0.5"),
        rank_sorpresa_volumen_4h=Decimal("0.5"),
        mediana_retorno_24h_mercado=Decimal(str(regimen_bps)) / Decimal("10000"),
    )
    return ObservacionRelativaV2(
        estado=estado,
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=8,
            retorno_cierre=Decimal("0.01"),
            mfe=Decimal("0.01"),
            mae=Decimal("0"),
        ),),
    )


def mapa_regimen_positivo(modelo):
    return {
        (p.timestamp_ms, p.symbol): Decimal("1")
        for p in exp._predicciones_de_modelo(modelo)
    }


def test_criterios_v4_exigen_regimen_neto_y_estabilidad():
    modelo = resultado_modelo_sintetico(top_predicho=30, top_real=40)
    regimen = evaluar_senales_regimen_cost_aware(
        exp._predicciones_de_modelo(modelo),
        mapa_regimen_positivo(modelo),
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
        folds=FOLDS_VALIDACION_ENE_ABR_2026,
    )

    pasa, motivos = exp._aplicar_criterios_v4(modelo, regimen)

    assert pasa
    assert motivos == ()


def test_criterios_v4_rechazan_cuando_regimen_no_aprueba_timestamps():
    modelo = resultado_modelo_sintetico(top_predicho=30, top_real=100)
    regimen = {
        (p.timestamp_ms, p.symbol): Decimal("-1")
        for p in exp._predicciones_de_modelo(modelo)
    }
    resultado_regimen = evaluar_senales_regimen_cost_aware(
        exp._predicciones_de_modelo(modelo),
        regimen,
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
        folds=FOLDS_VALIDACION_ENE_ABR_2026,
    )

    pasa, motivos = exp._aplicar_criterios_v4(modelo, resultado_regimen)

    assert not pasa
    assert "SIN_REGIMEN_APROBADO" in motivos
    assert "COBERTURA_REGIMEN_INSUFICIENTE" in motivos
    assert "SIN_SENALES_REGIMEN_COST_AWARE" in motivos


def test_regimen_v4_sale_de_feature_conocida_en_t():
    ts = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    datos = [obs("A", ts, regimen_bps=Decimal("2.5"))]

    regimen = exp._regimen_bps_por_clave(datos)

    assert regimen[(ts, "A")] == Decimal("2.5")


def test_validacion_v4_elimina_holdout_final_antes_de_evaluar(monkeypatch):
    vistos = []

    def fake(observaciones, **kwargs):
        datos = tuple(observaciones)
        vistos.extend(o.estado.timestamp_ms for o in datos)
        assert all(t < TEST_DESDE_MS for t in vistos)
        return resultado_modelo_sintetico()

    monkeypatch.setattr(exp, "evaluar_walk_forward_celdas", fake)
    config = ConfiguracionRegimenV4()
    datos = [obs("A", TEST_DESDE_MS - 1), obs("B", TEST_DESDE_MS)]

    r = exp.evaluar_validacion_v4_predeclarada(datos, configuraciones=[config])

    assert vistos == [TEST_DESDE_MS - 1]
    assert r.n_observaciones_pre_test == 1


def test_selector_v4_prefiere_mas_soporte_sin_usar_performance():
    modelo = resultado_modelo_sintetico()
    regimen = evaluar_senales_regimen_cost_aware(
        exp._predicciones_de_modelo(modelo),
        mapa_regimen_positivo(modelo),
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
        folds=FOLDS_VALIDACION_ENE_ABR_2026,
    )
    r30 = exp.ResultadoConfiguracionV4(
        ConfiguracionRegimenV4(min_muestras=30, max_radio=0),
        modelo,
        regimen,
        True,
        (),
    )
    r60 = exp.ResultadoConfiguracionV4(
        ConfiguracionRegimenV4(min_muestras=60, max_radio=0),
        modelo,
        regimen,
        True,
        (),
    )

    elegida = exp.seleccionar_configuracion_no_performance_v4((r30, r60))

    assert elegida == r60.configuracion
