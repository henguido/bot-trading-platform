from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.diagnostico_base_rate_v7 import (
    ClasificacionHorizonteV7,
    ResultadoDiagnosticoBaseRateV7,
    ResumenBaseRateV7,
    clasificar_horizonte_v7,
    resumir_base_rate_v7,
)
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_relativo_v2 import EstadoRelativoV2, ObservacionRelativaV2
from backend.economia.protocolo_edge_v7 import (
    CLASE_BASELINE_VIABLE,
    CLASE_SELECCION_POTENCIAL,
    CLASE_SIN_PRESUPUESTO,
    REGIMEN_NO_NEGATIVO,
)


def close_ts(limite_iso: str) -> int:
    limite = datetime.fromisoformat(limite_iso).replace(tzinfo=timezone.utc)
    return int(limite.timestamp() * 1000) - 1


def obs(ts: int, symbol: str, *, mercado_bps=10,
        ret24=100, ret48=200, ret72=300,
        mfe24=150, mfe48=250, mfe72=350,
        mae24=-50, mae48=-75, mae72=-100):
    return ObservacionRelativaV2(
        estado=EstadoRelativoV2(
            symbol=symbol,
            timestamp_ms=ts,
            close=Decimal("100"),
            rank_retorno_4h=Decimal("0.5"),
            rank_retorno_24h=Decimal("0.5"),
            rank_sorpresa_volumen_4h=Decimal("0.5"),
            mediana_retorno_24h_mercado=Decimal(str(mercado_bps)) / Decimal("10000"),
        ),
        etiquetas=tuple(
            EtiquetaHorizonte(
                horizonte_horas=h,
                retorno_cierre=Decimal(str(r)) / Decimal("10000"),
                mfe=Decimal(str(mfe)) / Decimal("10000"),
                mae=Decimal(str(mae)) / Decimal("10000"),
            )
            for h, r, mfe, mae in (
                (24, ret24, mfe24, mae24),
                (48, ret48, mfe48, mae48),
                (72, ret72, mfe72, mae72),
            )
        ),
    )


def test_resumen_24h_resta_hurdle_y_calcula_oracle_y_dispersion():
    t = close_ts("2025-01-02T00:00:00")
    datos = (
        obs(t, "AUSDT", ret24=100, mfe24=150, mae24=-20),
        obs(t, "BUSDT", ret24=300, mfe24=350, mae24=-80),
        obs(t, "CUSDT", ret24=-100, mfe24=60, mae24=-150),
        obs(t, "DUSDT", ret24=200, mfe24=250, mae24=-40),
    )
    r = resumir_base_rate_v7(datos, horizonte_horas=24, regimen=REGIMEN_NO_NEGATIVO)
    assert r.n_observaciones == 4
    assert r.n_timestamps == 1
    assert r.retorno_medio_bps == Decimal("125")
    assert r.retorno_neto_medio_bps == Decimal("100")
    assert r.fraccion_observaciones_cubren_hurdle == Decimal("0.75")
    assert r.baseline_timestamp_neto_medio_bps == Decimal("100")
    assert r.oracle_top1_neto_medio_bps == Decimal("275")
    assert r.fraccion_timestamps_oracle_neto_positivo == Decimal("1")
    # Orden -100,100,200,300 => p25=50, p75=225 => dispersion 175.
    assert r.dispersion_p75_p25_mediana_bps == Decimal("175")


def resumen_para_clase(*, baseline=10, frac_base="0.6", meses_base=9, folds_base=3,
                       oracle=150, frac_oracle="0.8", dispersion=80, meses_oracle=10):
    return ResumenBaseRateV7(
        horizonte_horas=48,
        regimen=REGIMEN_NO_NEGATIVO,
        n_observaciones=100,
        n_timestamps=20,
        retorno_medio_bps=Decimal("35"),
        retorno_p25_bps=Decimal("-10"),
        retorno_p50_bps=Decimal("20"),
        retorno_p75_bps=Decimal("70"),
        retorno_p90_bps=Decimal("120"),
        retorno_neto_medio_bps=Decimal("10"),
        fraccion_observaciones_cubren_hurdle=Decimal("0.6"),
        mfe_p50_bps=Decimal("60"),
        mfe_p75_bps=Decimal("100"),
        mfe_p90_bps=Decimal("180"),
        mae_p10_bps=Decimal("-150"),
        mae_p25_bps=Decimal("-80"),
        mae_p50_bps=Decimal("-40"),
        fraccion_observaciones_mfe_cubre_hurdle=Decimal("0.8"),
        baseline_timestamp_neto_medio_bps=Decimal(str(baseline)),
        fraccion_timestamps_baseline_neto_positivo=Decimal(frac_base),
        oracle_top1_neto_medio_bps=Decimal(str(oracle)),
        fraccion_timestamps_oracle_neto_positivo=Decimal(frac_oracle),
        dispersion_p75_p25_mediana_bps=Decimal(str(dispersion)),
        meses_2025_con_datos=12,
        meses_2025_baseline_neto_positivo=meses_base,
        meses_2025_oracle_neto_positivo=meses_oracle,
        folds_2025_con_datos=4,
        folds_2025_baseline_neto_positivo=folds_base,
    )


def test_clasifica_baseline_viable_sin_necesitar_oracle():
    c = clasificar_horizonte_v7(resumen_para_clase())
    assert c.clase == CLASE_BASELINE_VIABLE
    assert c.motivos == ()


def test_clasifica_seleccion_potencial_si_baseline_falla_pero_hay_presupuesto():
    c = clasificar_horizonte_v7(resumen_para_clase(
        baseline=-5, frac_base="0.4", meses_base=5, folds_base=2,
        oracle=150, frac_oracle="0.75", dispersion=75, meses_oracle=10,
    ))
    assert c.clase == CLASE_SELECCION_POTENCIAL
    assert "BASELINE_NETO_MEDIO_NO_POSITIVO" in c.motivos


def test_clasifica_sin_presupuesto_si_oracle_y_dispersion_tambien_fallan():
    c = clasificar_horizonte_v7(resumen_para_clase(
        baseline=-5, frac_base="0.4", meses_base=5, folds_base=2,
        oracle=50, frac_oracle="0.4", dispersion=20, meses_oracle=4,
    ))
    assert c.clase == CLASE_SIN_PRESUPUESTO
    assert "ORACLE_SIN_HOLGURA" in c.motivos
    assert "DISPERSION_INSUFICIENTE" in c.motivos


def test_selector_prefiere_horizonte_mas_corto_y_prioriza_baseline_viable():
    resultado = ResultadoDiagnosticoBaseRateV7(
        resumenes=(),
        clasificaciones_no_negativo=(
            ClasificacionHorizonteV7(24, CLASE_SELECCION_POTENCIAL, ()),
            ClasificacionHorizonteV7(48, CLASE_BASELINE_VIABLE, ()),
            ClasificacionHorizonteV7(72, CLASE_BASELINE_VIABLE, ()),
        ),
    )
    assert resultado.horizonte_candidato == 48
