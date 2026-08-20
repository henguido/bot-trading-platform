"""Pruebas del diagnostico de desarrollo 2025 para 04B."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

import backend.economia.diagnostico_edge_desarrollo as diag
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_relativo_v2 import EstadoRelativoV2, ObservacionRelativaV2
from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.protocolo_edge_v2 import VALIDACION_DESDE_MS
from backend.economia.protocolo_edge_v4 import ConfiguracionRegimenV4
from backend.economia.walk_forward_celdas import ResultadoFoldCeldas, ResultadoWalkForwardCeldas
from backend.economia.walk_forward_edge import FoldTemporal

RAIZ = Path(__file__).resolve().parents[1]
RUNNER = RAIZ / "scripts" / "run_edge_diagnostico_desarrollo.py"


def pred(symbol: str, ts: int, *, predicho_bps, real_bps=0) -> PrediccionCeldas:
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


def resultado_modelo_sintetico():
    fold = diag.FOLDS_DIAGNOSTICO_DESARROLLO_2025[0]
    ps = tuple(pred(f"S{i:02d}", fold.valid_desde_ms + 1, predicho_bps=30, real_bps=40)
               for i in range(15))
    return ResultadoWalkForwardCeldas(
        horizonte_horas=8,
        n_bins=3,
        min_muestras=30,
        min_symbols=3,
        min_timestamps=20,
        max_radio=0,
        folds=(ResultadoFoldCeldas(
            fold=fold,
            n_train_crudo=300,
            n_train_no_solapado=75,
            n_validacion_cruda=90,
            n_validacion_no_solapada=15,
            n_descartadas_embargo=4,
            estado="DISPONIBLE",
            predicciones=ps,
            motivo=None,
        ),),
        n_folds_disponibles=1,
        n_objetivo=len(ps),
        n_estimadas=len(ps),
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
        n_timestamps_cross_section=1,
        uplift_cross_section_medio=Decimal("0.01"),
        fraccion_timestamps_uplift_positivo=Decimal("1"),
        n_meses_cross_section=1,
        meses_uplift_positivo=1,
        uplift_mensual_min=Decimal("0.01"),
        uplift_mensual_p25=Decimal("0.01"),
        uplift_mensual_p50=Decimal("0.01"),
    )


def test_folds_diagnostico_desarrollo_no_tocan_2026():
    assert diag.DIAGNOSTICO_DESARROLLO_HASTA_MS < VALIDACION_DESDE_MS
    assert all(
        f.valid_hasta_ms <= VALIDACION_DESDE_MS
        for f in diag.FOLDS_DIAGNOSTICO_DESARROLLO_2025
    )


def test_resumen_predichos_cuenta_hurdle_por_regimen():
    ts = diag.FOLDS_DIAGNOSTICO_DESARROLLO_2025[0].valid_desde_ms + 1
    datos = (
        pred("A", ts, predicho_bps=30),
        pred("B", ts, predicho_bps=26),
        pred("C", ts, predicho_bps=24),
        pred("D", ts, predicho_bps=50),
        pred("E", ts, predicho_bps=10),
    )
    regimen = {
        (ts, "A"): Decimal("1"),
        (ts, "B"): Decimal("-1"),
        (ts, "C"): Decimal("1"),
        (ts, "D"): Decimal("-1"),
    }

    r = diag.resumir_predichos_hurdle(
        datos,
        regimen,
        hurdle_predicho_bps=25,
        regimen_minimo_bps=0,
    )

    assert r.n_predicciones == 5
    assert r.n_sin_regimen == 1
    assert r.n_regimen_no_negativo == 2
    assert r.n_regimen_negativo == 2
    assert r.n_sobre_hurdle == 3
    assert r.n_sobre_hurdle_regimen_no_negativo == 1
    assert r.n_sobre_hurdle_regimen_negativo == 2
    assert r.predicho_bps_max_regimen_no_negativo == Decimal("30.0000")
    assert r.predicho_bps_max_regimen_negativo == Decimal("50.0000")


def test_diagnostico_elimina_2026_antes_de_evaluar(monkeypatch):
    vistos = []

    def fake(observaciones, **kwargs):
        datos = tuple(observaciones)
        vistos.extend(o.estado.timestamp_ms for o in datos)
        assert all(t < VALIDACION_DESDE_MS for t in vistos)
        return resultado_modelo_sintetico()

    monkeypatch.setattr(diag, "evaluar_walk_forward_celdas", fake)
    config = ConfiguracionRegimenV4()
    datos = [obs("A", VALIDACION_DESDE_MS - 1), obs("B", VALIDACION_DESDE_MS)]

    r = diag.diagnosticar_edge_desarrollo_2025(datos, configuraciones=[config])

    assert vistos == [VALIDACION_DESDE_MS - 1]
    assert r.n_observaciones_pre_2026 == 1
    assert r.n_configuraciones == 1


def test_diagnostico_rechaza_folds_que_entran_a_2026():
    malo = (FoldTemporal(VALIDACION_DESDE_MS - 1, VALIDACION_DESDE_MS + 1),)

    with pytest.raises(ValueError, match="no pueden tocar 2026"):
        diag.diagnosticar_edge_desarrollo_2025([], folds=malo)


def test_runner_diagnostico_no_usa_validacion_2026_ni_holdout_final():
    fuente = RUNNER.read_text(encoding="utf-8")
    assert "end_ms = DIAGNOSTICO_DESARROLLO_HASTA_MS" in fuente
    assert "VALIDACION_HASTA_MS" not in fuente
    assert "TEST_HASTA_MS" not in fuente
    assert "validacion_2026_open" in fuente
    assert "test_may_jul_open" in fuente
    arbol = ast.parse(fuente)
    assert "DIAGNOSTICO_DESARROLLO_HASTA_MS" in ast.dump(arbol)
    assert "VALIDACION_DESDE_MS" in ast.dump(arbol)
