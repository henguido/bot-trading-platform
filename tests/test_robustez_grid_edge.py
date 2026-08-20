"""Candados contra seleccionar falsos positivos aislados entre 72 configs."""

from backend.economia.experimento_edge import (
    ResultadoConfiguracionFalsacion,
    ResultadoValidacionFalsacion,
    _dimension_vecina,
    _marcar_robustez_grid,
)
from backend.economia.protocolo_experimento_edge import ConfiguracionCeldas


def cfg(h=4, bins=4, muestras=30, radio=1):
    return ConfiguracionCeldas(h, bins, muestras, radio)


def resultado(c, pasa=True):
    # `resultado` no participa en la regla de robustez: esta solo consume
    # configuracion + booleano de criterios predeclarados ya calculado.
    return ResultadoConfiguracionFalsacion(
        configuracion=c,
        resultado=None,
        folds_con_uplift_positivo=4,
        folds_cross_section_positivos=4,
        supera_criterios_minimos=pasa,
        motivos_rechazo=() if pasa else ("FALLO",),
    )


def test_dimension_vecina_exige_un_solo_cambio_adyacente():
    centro = cfg()
    assert _dimension_vecina(centro, cfg(bins=3)) == "n_bins"
    assert _dimension_vecina(centro, cfg(muestras=60)) == "min_muestras"
    assert _dimension_vecina(centro, cfg(radio=2)) == "max_radio"
    assert _dimension_vecina(centro, cfg(bins=3, radio=2)) is None
    assert _dimension_vecina(cfg(bins=3), cfg(bins=6)) is None
    assert _dimension_vecina(centro, cfg(h=8)) is None


def test_config_aprobada_con_vecinos_en_dos_dimensiones_es_robusta():
    centro = resultado(cfg())
    vecino_bins = resultado(cfg(bins=3))
    vecino_muestras = resultado(cfg(muestras=60))
    marcados = _marcar_robustez_grid((centro, vecino_bins, vecino_muestras))
    m = next(x for x in marcados if x.configuracion == centro.configuracion)
    assert m.robusta_grid
    assert m.dimensiones_vecinas_robustas == ("min_muestras", "n_bins")


def test_exito_aislado_no_habilita_test():
    marcados = _marcar_robustez_grid((resultado(cfg()),))
    assert not marcados[0].robusta_grid
    assert marcados[0].dimensiones_vecinas_robustas == ()


def test_vecinos_que_no_pasan_no_cuentan():
    centro = resultado(cfg())
    vecino_bins = resultado(cfg(bins=3), pasa=False)
    vecino_radio = resultado(cfg(radio=2), pasa=False)
    m = _marcar_robustez_grid((centro, vecino_bins, vecino_radio))[0]
    assert not m.robusta_grid
    assert m.dimensiones_vecinas_robustas == ()


def test_estabilidad_en_una_sola_dimension_sigue_siendo_insuficiente():
    centro = resultado(cfg())
    # Dos vecinos de radio, pero representan una sola dimension de estabilidad.
    r0 = resultado(cfg(radio=0))
    r2 = resultado(cfg(radio=2))
    m = _marcar_robustez_grid((centro, r0, r2))[0]
    assert not m.robusta_grid
    assert m.dimensiones_vecinas_robustas == ("max_radio",)


def test_resumen_reporta_robustas_y_horizontes_sin_elegir_ganador():
    rs = _marcar_robustez_grid((
        resultado(cfg(h=4)),
        resultado(cfg(h=4, bins=3)),
        resultado(cfg(h=4, muestras=60)),
        resultado(cfg(h=8)),
    ))
    resumen = ResultadoValidacionFalsacion(
        n_observaciones_desarrollo=100,
        n_configuraciones=len(rs),
        resultados=rs,
    )
    assert resumen.n_superan_minimos == 4
    assert resumen.n_robustas_grid == 1
    assert resumen.horizontes_robustos == (4,)
    assert not hasattr(resumen, "ganador")
