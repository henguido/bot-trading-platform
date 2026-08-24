from decimal import Decimal

import pytest

from backend.economia.costes import estimar_roundtrip
from backend.economia.rentabilidad import (
    APTA,
    COSTES_INCOMPLETOS,
    EDGE_DESCONOCIDO,
    EDGE_NO_POSITIVO,
    MARGEN_NETO_INSUFICIENTE,
    NO_APTA,
    NO_EVALUABLE,
    evaluar_desde_componentes,
    evaluar_rentabilidad,
)


def costes_completos():
    return estimar_roundtrip(
        notional_usd="100",
        spread_bps="4",
        fee_taker_bps_por_lado="5",
        slippage_bps_por_lado="2",
        exigir_costo_ia=False,
    )


def test_aprueba_solo_si_edge_neto_supera_margen_explicito():
    # Coste = 4 + 2*5 + 2*2 = 18 bps. Edge 30 => neto 12 bps.
    r = evaluar_rentabilidad(
        edge_bruto_bps="30",
        costes=costes_completos(),
        margen_neto_minimo_bps="10",
    )
    assert r.estado == APTA
    assert r.apta is True
    assert r.coste_total_bps == Decimal("18")
    assert r.edge_neto_bps == Decimal("12")
    assert r.edge_neto_usd == Decimal("0.12")
    assert r.multiplo_edge_sobre_coste == Decimal("30") / Decimal("18")
    assert r.motivos == ()


def test_rechaza_edge_positivo_si_no_deja_margen_neto_requerido():
    r = evaluar_rentabilidad(
        edge_bruto_bps="25",
        costes=costes_completos(),
        margen_neto_minimo_bps="10",
    )
    assert r.estado == NO_APTA
    assert r.apta is False
    assert r.edge_neto_bps == Decimal("7")
    assert r.motivos == (MARGEN_NETO_INSUFICIENTE,)


def test_edge_igual_al_coste_puede_medirse_con_margen_cero_pero_no_con_margen_positivo():
    base = costes_completos()
    exploratoria = evaluar_rentabilidad(
        edge_bruto_bps="18", costes=base, margen_neto_minimo_bps="0")
    assert exploratoria.apta is True
    assert exploratoria.edge_neto_bps == Decimal("0")

    conservadora = evaluar_rentabilidad(
        edge_bruto_bps="18", costes=base, margen_neto_minimo_bps="0.01")
    assert conservadora.apta is False
    assert conservadora.motivos == (MARGEN_NETO_INSUFICIENTE,)


def test_edge_cero_o_negativo_no_es_operable():
    for edge in ("0", "-1"):
        r = evaluar_rentabilidad(
            edge_bruto_bps=edge,
            costes=costes_completos(),
            margen_neto_minimo_bps="0",
        )
        assert r.estado == NO_APTA
        assert EDGE_NO_POSITIVO in r.motivos


def test_edge_desconocido_es_no_evaluable_no_cero():
    r = evaluar_rentabilidad(
        edge_bruto_bps=None,
        costes=costes_completos(),
        margen_neto_minimo_bps="5",
    )
    assert r.estado == NO_EVALUABLE
    assert r.evaluable is False
    assert r.edge_neto_bps is None
    assert r.edge_neto_usd is None
    assert r.motivos == (EDGE_DESCONOCIDO,)


def test_costes_incompletos_bloquean_aunque_edge_sea_alto():
    incompletos = estimar_roundtrip(
        notional_usd="100",
        spread_bps="2",
        fee_taker_bps_por_lado=None,
        slippage_bps_por_lado="1",
        exigir_costo_ia=False,
    )
    r = evaluar_rentabilidad(
        edge_bruto_bps="500",
        costes=incompletos,
        margen_neto_minimo_bps="0",
    )
    assert r.estado == NO_EVALUABLE
    assert r.apta is False
    assert r.edge_neto_bps is None
    assert COSTES_INCOMPLETOS in r.motivos


def test_camino_sin_llm_no_inventa_coste_ia_pero_si_exige_componentes_de_mercado():
    r = evaluar_desde_componentes(
        edge_bruto_bps="30",
        margen_neto_minimo_bps="5",
        notional_usd="100",
        spread_bps="4",
        fee_taker_bps_por_lado="5",
        slippage_bps_por_lado="2",
        exigir_costo_ia=False,
    )
    assert r.apta is True
    assert "costo_ia" not in r.costes.faltantes


def test_si_se_usa_ia_su_coste_es_obligatorio_y_falla_cerrado_si_falta():
    r = evaluar_desde_componentes(
        edge_bruto_bps="100",
        margen_neto_minimo_bps="0",
        notional_usd="100",
        spread_bps="2",
        fee_taker_bps_por_lado="5",
        slippage_bps_por_lado="1",
        costo_ia_asignado_usd=None,
        exigir_costo_ia=True,
    )
    assert r.estado == NO_EVALUABLE
    assert COSTES_INCOMPLETOS in r.motivos
    assert "costo_ia" in r.costes.faltantes


def test_coste_ia_se_convierte_a_bps_y_reduce_edge_neto():
    # Mercado: 2 + 10 + 2 = 14 bps. IA $0.10 sobre $100 = 10 bps.
    r = evaluar_desde_componentes(
        edge_bruto_bps="40",
        margen_neto_minimo_bps="15",
        notional_usd="100",
        spread_bps="2",
        fee_taker_bps_por_lado="5",
        slippage_bps_por_lado="1",
        costo_ia_asignado_usd="0.10",
        exigir_costo_ia=True,
    )
    assert r.coste_total_bps == Decimal("24")
    assert r.edge_neto_bps == Decimal("16")
    assert r.apta is True


def test_margen_negativo_no_se_permite_para_forzar_operaciones():
    with pytest.raises(ValueError, match="no puede ser negativo"):
        evaluar_rentabilidad(
            edge_bruto_bps="10",
            costes=costes_completos(),
            margen_neto_minimo_bps="-1",
        )
