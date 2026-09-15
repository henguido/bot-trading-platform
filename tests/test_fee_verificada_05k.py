from datetime import datetime, timezone

import pytest

from backend.economia.fee_verificada import fee_taker_manual_verificada


def test_fee_manual_fresca_es_utilizable(monkeypatch):
    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", "10.0")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_SOURCE",
        "manual:binance_account.commissionRates.taker",
    )
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )

    dato = fee_taker_manual_verificada(
        datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)
    )

    assert dato["fee_taker_bps_por_lado"] == 10.0
    assert dato["fuente_fee"] == (
        "manual:binance_account.commissionRates.taker"
    )


def test_fee_manual_caducada_no_se_usa(monkeypatch):
    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", "10.0")
    monkeypatch.setenv("RESEARCH_TAKER_FEE_SOURCE", "manual:test")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )

    assert fee_taker_manual_verificada(
        datetime(2026, 9, 12, 19, 0, tzinfo=timezone.utc)
    ) is None


def test_fee_manual_incompleta_no_inventa_cero(monkeypatch):
    monkeypatch.delenv("RESEARCH_TAKER_FEE_BPS", raising=False)
    monkeypatch.delenv("RESEARCH_TAKER_FEE_SOURCE", raising=False)
    monkeypatch.delenv("RESEARCH_TAKER_FEE_VERIFIED_AT", raising=False)

    assert fee_taker_manual_verificada() is None


@pytest.mark.parametrize("fee", ["nan", "inf", "-inf", "-0.1", "invalida"])
def test_fee_manual_invalida_falla_cerrado(monkeypatch, fee):
    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", fee)
    monkeypatch.setenv("RESEARCH_TAKER_FEE_SOURCE", "manual:test")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )

    assert fee_taker_manual_verificada(
        datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)
    ) is None


def test_fee_manual_rechaza_fecha_o_reloj_sin_zona_horaria(monkeypatch):
    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", "10.0")
    monkeypatch.setenv("RESEARCH_TAKER_FEE_SOURCE", "manual:test")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00",
    )
    assert fee_taker_manual_verificada(
        datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)
    ) is None

    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )
    assert fee_taker_manual_verificada(datetime(2026, 9, 4, 19, 0)) is None


def test_05i_usa_fee_manual_si_la_cuenta_no_esta_configurada(monkeypatch):
    from scripts import shadow_scanner_unified_05i as shadow

    monkeypatch.setattr(shadow.settings, "BINANCE_API_KEY", "")
    monkeypatch.setattr(shadow.settings, "BINANCE_API_SECRET", "")
    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", "10.0")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_SOURCE",
        "manual:binance_account.commissionRates.taker",
    )
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )

    fee = shadow._fee_taker_si_disponible(
        datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)
    )

    assert fee == 10.0


def test_05i_prefiere_fee_directa_de_binance(monkeypatch):
    from scripts import shadow_scanner_unified_05i as shadow

    monkeypatch.setattr(shadow.settings, "BINANCE_API_KEY", "sintetica")
    monkeypatch.setattr(shadow.settings, "BINANCE_API_SECRET", "sintetica")

    monkeypatch.setattr(
        shadow,
        "get_available_assets",
        lambda incluir_costes_cuenta=False: (
            [],
            [],
            [],
            {
                "fee_taker_bps_por_lado": 8.5,
                "fuente_fee": "binance_account.commissionRates.taker",
            },
        ),
    )

    monkeypatch.setenv("RESEARCH_TAKER_FEE_BPS", "10.0")
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_SOURCE",
        "manual:binance_account.commissionRates.taker",
    )
    monkeypatch.setenv(
        "RESEARCH_TAKER_FEE_VERIFIED_AT",
        "2026-09-04T18:47:00Z",
    )

    assert shadow._fee_taker_si_disponible(
        datetime(2026, 9, 4, 19, 0, tzinfo=timezone.utc)
    ) == 8.5
