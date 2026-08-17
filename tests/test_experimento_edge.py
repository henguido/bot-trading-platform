"""Candados del runner offline de falsacion 04B."""
from decimal import Decimal

import backend.economia.experimento_edge as exp
from backend.economia.edge_historico import EstadoHistorico, EtiquetaHorizonte, ObservacionEdge
from backend.economia.protocolo_experimento_edge import ConfiguracionCeldas, CORTE_TEST_MS, FOLDS_VALIDACION_2025
from backend.economia.walk_forward_celdas import ResultadoFoldCeldas, ResultadoWalkForwardCeldas


def obs(ts, retorno="0.01"):
    r = Decimal(retorno)
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol="BTCUSDT", timestamp_ms=ts, close=Decimal("100"),
            quote_volume_24h=Decimal("1000"), trades_24h=100,
            rango_24h=Decimal("0.03"), momentum_cierre_24h_pct=Decimal("1")),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=4, retorno_cierre=r,
            mfe=max(Decimal("0"), r), mae=min(Decimal("0"), r)),),)


def pred(symbol, ts, predicho, real):
    from backend.economia.evaluacion_celdas import PrediccionCeldas
    return PrediccionCeldas(
        symbol, ts, Decimal(predicho), Decimal(real),
        0, 30, 5, 20, Decimal("0.20"), Decimal("0.05"))


def resultado_sintetico(*, cobertura="1", uplift_obj="0.01", uplift_est="0.01",
                         folds_positivos=4, uplift_cs="0.01",
                         frac_ts_cs="0.60", meses_cs=12, meses_pos=9):
    folds = []
    for i, f in enumerate(FOLDS_VALIDACION_2025):
        # Cuatro activos por timestamp para que exista ranking cross-sectional.
        if i < folds_positivos:
            ps = (
                pred("A", f.valid_desde_ms + 1, "0.04", "0.04"),
                pred("B", f.valid_desde_ms + 1, "0.02", "0.01"),
                pred("C", f.valid_desde_ms + 1, "0.00", "0.00"),
                pred("D", f.valid_desde_ms + 1, "-0.01", "-0.02"),
            )
        else:
            ps = (
                pred("A", f.valid_desde_ms + 1, "0.04", "-0.04"),
                pred("B", f.valid_desde_ms + 1, "0.02", "-0.01"),
                pred("C", f.valid_desde_ms + 1, "0.00", "0.00"),
                pred("D", f.valid_desde_ms + 1, "-0.01", "0.03"),
            )
        folds.append(ResultadoFoldCeldas(
            f, 100, 25, 40, 10, 4, "DISPONIBLE", ps, None))
    return ResultadoWalkForwardCeldas(
        horizonte_horas=4, n_bins=3, min_muestras=30,
        min_symbols=5, min_timestamps=20, max_radio=1,
        folds=tuple(folds), n_folds_disponibles=4,
        n_objetivo=100, n_estimadas=int(Decimal(cobertura) * 100),
        cobertura=Decimal(cobertura),
        retorno_real_objetivo_medio=Decimal("0"),
        retorno_real_estimadas_medio=Decimal("0"),
        sesgo_seleccion_cobertura=Decimal("0"),
        mae_prediccion=Decimal("0.01"), exactitud_direccional=Decimal("0.55"),
        retorno_real_top25_predicho=Decimal("0.02"),
        uplift_top25_vs_estimadas=Decimal(uplift_est),
        uplift_top25_vs_objetivo=Decimal(uplift_obj), radio_p95=1.0,
        max_symbol_share_p95=0.20, max_timestamp_share_p95=0.05,
        n_timestamps_cross_section=100,
        uplift_cross_section_medio=Decimal(uplift_cs),
        fraccion_timestamps_uplift_positivo=Decimal(frac_ts_cs),
        n_meses_cross_section=meses_cs,
        meses_uplift_positivo=meses_pos,
        uplift_mensual_min=Decimal("-0.01"),
        uplift_mensual_p25=Decimal("0.001"),
        uplift_mensual_p50=Decimal("0.01"),
    )


def test_test_2026_se_elimina_antes_de_evaluar(monkeypatch):
    vistos = []
    def fake(observaciones, **kwargs):
        datos = tuple(observaciones)
        vistos.extend(o.estado.timestamp_ms for o in datos)
        assert all(t < CORTE_TEST_MS for t in vistos)
        return resultado_sintetico()
    monkeypatch.setattr(exp, "evaluar_walk_forward_celdas", fake)

    config = ConfiguracionCeldas(4, 3, 30, 1)
    datos = [obs(CORTE_TEST_MS - 1), obs(CORTE_TEST_MS), obs(CORTE_TEST_MS + 1)]
    r = exp.evaluar_validacion_predeclarada(datos, configuraciones=[config])
    assert vistos == [CORTE_TEST_MS - 1]
    assert r.n_observaciones_desarrollo == 1


def test_criterios_rechazan_cobertura_insuficiente():
    pasa, motivos, _, _ = exp._aplicar_criterios(resultado_sintetico(cobertura="0.49"))
    assert not pasa
    assert "COBERTURA_INSUFICIENTE" in motivos


def test_criterios_rechazan_uplift_no_positivo():
    pasa, motivos, _, _ = exp._aplicar_criterios(
        resultado_sintetico(uplift_obj="0", uplift_est="-0.001"))
    assert not pasa
    assert "SIN_UPLIFT_VS_OBJETIVO" in motivos
    assert "SIN_UPLIFT_VS_ESTIMADAS" in motivos


def test_criterios_exigen_estabilidad_en_al_menos_tres_folds():
    pasa, motivos, n, n_cs = exp._aplicar_criterios(
        resultado_sintetico(folds_positivos=2))
    assert n == 2
    assert n_cs == 2
    assert not pasa
    assert "UPLIFT_INESTABLE_ENTRE_FOLDS" in motivos
    assert "UPLIFT_CROSS_SECTION_INESTABLE_FOLDS" in motivos


def test_criterios_rechazan_cross_section_debil():
    pasa, motivos, _, _ = exp._aplicar_criterios(resultado_sintetico(
        uplift_cs="0", frac_ts_cs="0.49", meses_cs=11, meses_pos=7))
    assert not pasa
    assert "SIN_UPLIFT_CROSS_SECTION" in motivos
    assert "CROSS_SECTION_INESTABLE_TIMESTAMPS" in motivos
    assert "COBERTURA_MENSUAL_CROSS_SECTION_INSUFICIENTE" in motivos
    assert "UPLIFT_CROSS_SECTION_INESTABLE_MENSUAL" in motivos


def test_configuracion_sana_supera_filtro_minimo_sin_elegir_ganador():
    pasa, motivos, n, n_cs = exp._aplicar_criterios(resultado_sintetico())
    assert pasa
    assert motivos == ()
    assert n == 4
    assert n_cs == 4
