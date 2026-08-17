"""04A · Las fuentes existentes no deben duplicarse ni reinterpretarse."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import models
from backend.economia.costes import estimar_roundtrip
from backend.scanner import leer_metricas
from backend.telemetria_llm import DISPONIBLE, NO_DISPONIBLE, calcular_costo_usd

RAIZ = Path(__file__).resolve().parents[1]
ORDENES_REPO = RAIZ / "backend" / "app" / "services" / "ordenes_repo.py"


def test_spread_del_modelo_coincide_con_el_scanner():
    fila = {
        "lastPrice": "100", "bidPrice": "99.95", "askPrice": "100.05",
        "quoteVolume": "1000000", "count": "5000",
        "highPrice": "105", "lowPrice": "95", "priceChangePercent": "2",
    }
    m = leer_metricas("XUSDT", fila)
    e = estimar_roundtrip(
        notional_usd=10,
        spread_bps=m.spread_bps,
        fee_taker_bps_por_lado=0,
        slippage_bps_por_lado=0,
        costo_ia_asignado_usd=0,
    )
    assert float(e.spread_bps) == pytest.approx(m.spread_bps)
    assert e.total_bps is not None


def test_fill_persiste_comision_cruda_del_broker():
    columnas = {c.name for c in models.Fill.__table__.columns}
    assert {"commission", "commission_asset"} <= columnas

    fuente = ORDENES_REPO.read_text(encoding="utf-8")
    assert 'commission=fill.get("commission")' in fuente
    assert 'commission_asset=fill.get("commission_asset")' in fuente


def test_coste_llm_no_inventa_tarifas():
    costo, estado, _ = calcular_costo_usd(1279, 525)
    assert costo is None
    assert estado == NO_DISPONIBLE


def test_coste_llm_configurado_se_puede_asignar_al_modelo():
    costo, estado, _ = calcular_costo_usd(
        1279, 525, precio_input_por_1m=2.5, precio_output_por_1m=10.0)
    assert estado == DISPONIBLE
    assert costo == pytest.approx(0.0084475)

    e = estimar_roundtrip(
        notional_usd=10,
        spread_bps=10,
        fee_taker_bps_por_lado=10,
        slippage_bps_por_lado=5,
        costo_ia_asignado_usd=costo,
    )
    # IA sola representa ~8.4475 bps sobre 10 USDT.
    ia_bps = costo / 10 * 10_000
    assert ia_bps == pytest.approx(8.4475)
    assert float(e.total_bps) == pytest.approx(58.4475)


def test_04a_no_modifica_la_comision_realizada():
    # El modelo pre-trade vive en otro modulo y no toca la persistencia de fills.
    fuente = (RAIZ / "backend" / "economia" / "costes.py").read_text(encoding="utf-8")
    assert "models.Fill" not in fuente
    assert "registrar_fill" not in fuente
    assert "procesar_fills" not in fuente
