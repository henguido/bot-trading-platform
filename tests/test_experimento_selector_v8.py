from dataclasses import replace
from decimal import Decimal

import backend.economia.experimento_selector_v8 as exp
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_selector_v8 import EstadoSelectorV8, ObservacionSelectorV8


def _obs(ts: int, symbol: str = "BTCUSDT"):
    return ObservacionSelectorV8(
        estado=EstadoSelectorV8(
            symbol=symbol,
            timestamp_ms=ts,
            close=Decimal("100"),
            rank_retorno_4h=Decimal("0.5"),
            rank_retorno_24h=Decimal("0.5"),
            rank_sorpresa_volumen_4h=Decimal("0.5"),
            mediana_retorno_24h_mercado=Decimal("0"),
            dispersion_iqr_retorno_24h_mercado=Decimal("0.02"),
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=24,
            retorno_cierre=Decimal("0.01"),
            mfe=Decimal("0.02"),
            mae=Decimal("-0.01"),
        ),),
    )


def _resultado(c, *, pasa=True, robusta=False):
    return exp.ResultadoConfiguracionSelectorV8(
        configuracion=c,
        n_timestamps_evaluables=200,
        n_senales=120,
        retorno_neto_medio_bps=Decimal("50"),
        fraccion_senales_neto_positivo=Decimal("0.6"),
        n_meses_con_senal=12,
        meses_netos_positivos=9,
        n_folds_con_senal=4,
        folds_netos_positivos=3,
        supera_criterios=pasa,
        motivos_rechazo=() if pasa else ("X",),
        robusta_grid=robusta,
        senales=(),
    )


def test_grid_v8_tiene_exactamente_32_configuraciones():
    configs = exp.configuraciones_v8_predeclaradas()
    assert len(configs) == 32
    assert len(set(configs)) == 32


def test_vecindad_requiere_cambio_en_una_sola_dimension():
    a = exp.ConfiguracionSelectorV8(3, 3, 3, 60, 0)
    b = exp.ConfiguracionSelectorV8(4, 3, 3, 60, 0)
    c = exp.ConfiguracionSelectorV8(4, 4, 3, 60, 0)
    assert exp._dimension_vecina(a, b) == "rank_bins"
    assert exp._dimension_vecina(a, c) is None


def test_robustez_exige_vecinos_aprobados_en_dos_dimensiones():
    centro = exp.ConfiguracionSelectorV8(3, 3, 3, 60, 0)
    rank = exp.ConfiguracionSelectorV8(4, 3, 3, 60, 0)
    soporte = exp.ConfiguracionSelectorV8(3, 3, 3, 120, 0)
    rs = exp._marcar_robustez([
        _resultado(centro),
        _resultado(rank),
        _resultado(soporte),
    ])
    r = next(x for x in rs if x.configuracion == centro)
    assert r.robusta_grid
    assert set(r.dimensiones_vecinas_robustas) == {"rank_bins", "min_muestras"}


def test_selector_no_performance_ignora_retorno_realizado():
    a = exp.ConfiguracionSelectorV8(3, 3, 3, 60, 0)
    b = exp.ConfiguracionSelectorV8(4, 4, 4, 120, 1)
    ra = _resultado(a, robusta=True)
    rb = _resultado(b, robusta=True)
    elegido_1 = exp.seleccionar_configuracion_no_performance_v8([ra, rb])
    # Cambiar PnL/hit-rate no puede cambiar el selector geometrico.
    ra2 = replace(ra, retorno_neto_medio_bps=Decimal("-999"), fraccion_senales_neto_positivo=Decimal("0"))
    rb2 = replace(rb, retorno_neto_medio_bps=Decimal("9999"), fraccion_senales_neto_positivo=Decimal("1"))
    elegido_2 = exp.seleccionar_configuracion_no_performance_v8([ra2, rb2])
    assert elegido_1 == elegido_2


def test_evaluacion_filtra_2026_antes_de_configuraciones(monkeypatch):
    visto = []

    def falso(datos, c):
        visto.extend(o.estado.timestamp_ms for o in datos)
        return _resultado(c, pasa=False)

    monkeypatch.setattr(exp, "_evaluar_config", falso)
    c = exp.ConfiguracionSelectorV8(3, 3, 3, 60, 0)
    datos = (
        _obs(exp.FIN_2025_MS - 1, "AUSDT"),
        _obs(exp.FIN_2025_MS + 1, "BUSDT"),
    )
    r = exp.evaluar_selector_v8_desarrollo(datos, configuraciones=[c])
    assert r.n_observaciones_desarrollo == 1
    assert visto == [exp.FIN_2025_MS - 1]
