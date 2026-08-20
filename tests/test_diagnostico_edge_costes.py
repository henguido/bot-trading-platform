"""04B-v2b · diagnostico de edge bruto contra costes 04A."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.costes import estimar_roundtrip
from backend.economia.diagnostico_edge_costes import (
    COSTE_NO_DISPONIBLE,
    CUBRE_COSTES,
    NO_CUBRE_COSTES,
    diagnosticar_edge_vs_costes,
    fee_taker_break_even_por_lado_bps,
)

RAIZ = Path(__file__).resolve().parents[1]
EDGE_V2_ROBUSTO_BPS = Decimal("3.411755004224985882828268115")


def test_edge_v2_no_cubre_fee_taker_por_lado_de_10_bps_aun_sin_otras_fricciones():
    costes = estimar_roundtrip(
        notional_usd=100,
        spread_bps=0,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )

    d = diagnosticar_edge_vs_costes(EDGE_V2_ROBUSTO_BPS, costes)

    assert d.estado == NO_CUBRE_COSTES
    assert d.coste_total_bps == Decimal("20")
    assert d.edge_neto_antes_margen_bps == EDGE_V2_ROBUSTO_BPS - Decimal("20")
    assert d.motivos == ("coste_total_mayor_que_edge_bruto",)


def test_break_even_fee_muestra_que_v2_tolera_menos_de_2_bps_por_lado():
    umbral = fee_taker_break_even_por_lado_bps(EDGE_V2_ROBUSTO_BPS)
    assert umbral == EDGE_V2_ROBUSTO_BPS / Decimal("2")
    assert umbral < Decimal("2")


def test_coste_incompleto_falla_cerrado_y_no_inventa_total_cero():
    costes = estimar_roundtrip(
        notional_usd=100,
        spread_bps=1,
        fee_taker_bps_por_lado=None,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )

    d = diagnosticar_edge_vs_costes(EDGE_V2_ROBUSTO_BPS, costes)

    assert d.estado == COSTE_NO_DISPONIBLE
    assert d.coste_total_bps is None
    assert d.edge_neto_antes_margen_bps is None
    assert "coste_fee_taker_no_disponible" in d.motivos


def test_margen_seguridad_se_resta_despues_del_coste_total():
    costes = estimar_roundtrip(
        notional_usd=100,
        spread_bps=2,
        fee_taker_bps_por_lado=1,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )

    sin_margen = diagnosticar_edge_vs_costes(5, costes, margen_seguridad_bps=0)
    con_margen = diagnosticar_edge_vs_costes(5, costes, margen_seguridad_bps=2)

    assert sin_margen.estado == CUBRE_COSTES
    assert sin_margen.edge_neto_despues_margen_bps == Decimal("1")
    assert con_margen.estado == NO_CUBRE_COSTES
    assert con_margen.edge_neto_antes_margen_bps == Decimal("1")
    assert con_margen.edge_neto_despues_margen_bps == Decimal("-1")
    assert con_margen.motivos == ("margen_seguridad_no_cubierto",)


@pytest.mark.parametrize("kwargs", [
    {"spread_bps": -1},
    {"slippage_bps_por_lado": -1},
    {"costo_ia_bps": -1},
    {"margen_seguridad_bps": -1},
])
def test_break_even_rechaza_fricciones_negativas(kwargs):
    with pytest.raises(ValueError):
        fee_taker_break_even_por_lado_bps(EDGE_V2_ROBUSTO_BPS, **kwargs)


def test_modulo_no_importa_red_bd_scanner_risk_llm_ni_trading():
    fuente = RAIZ / "backend" / "economia" / "diagnostico_edge_costes.py"
    tree = ast.parse(fuente.read_text(encoding="utf-8"))
    prohibidos = {
        "requests", "sqlalchemy", "backend.app", "backend.scanner",
        "backend.risk", "backend.connectors", "backend.telemetria_llm",
        "backend.main", "openai", "binance",
    }
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not (imports & prohibidos)
