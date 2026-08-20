from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from backend.economia.auditoria_funding_v18 import auditar_funding_v18
from backend.economia.historico_funding_v18 import EventoFundingV18
from backend.economia.protocolo_funding_v18 import DESDE_V18, UNIVERSO_FUNDING_V18

_DIA_MS = 86_400_000
_HORA_MS = 3_600_000


def _evento(symbol: str, ts: int, rate: str = "0.0001"):
    return EventoFundingV18(symbol, ts, Decimal(rate))


def _serie_diaria(symbol: str, n_dias: int):
    base = int(DESDE_V18.timestamp() * 1000)
    return tuple(_evento(symbol, base + i * _DIA_MS) for i in range(n_dias))


def test_quince_simbolos_con_cobertura_total_hacen_dataset_apto():
    n_dias = (DESDE_V18.replace(year=2026) - DESDE_V18).days
    series = {
        symbol: _serie_diaria(symbol, n_dias)
        for symbol in UNIVERSO_FUNDING_V18[:15]
    }
    audit = auditar_funding_v18(series)
    assert audit.dataset_apto is True
    assert audit.n_simbolos_aptos == 15
    assert audit.fraccion_cross_section_completa == Decimal("1")
    assert audit.min_simbolos_en_dia == 15
    assert all(a.apto for a in audit.anios)


def test_catorce_simbolos_no_alcanzan_cross_section_predeclarada():
    n_dias = (DESDE_V18.replace(year=2026) - DESDE_V18).days
    series = {
        symbol: _serie_diaria(symbol, n_dias)
        for symbol in UNIVERSO_FUNDING_V18[:14]
    }
    audit = auditar_funding_v18(series)
    assert audit.dataset_apto is False
    assert "SIMBOLOS_APTOS_INSUFICIENTES" in audit.motivos_rechazo
    assert "COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE" in audit.motivos_rechazo


def test_duplicado_no_se_oculta_en_cobertura_diaria():
    symbol = UNIVERSO_FUNDING_V18[0]
    base = int(DESDE_V18.timestamp() * 1000)
    series = {symbol: (_evento(symbol, base), _evento(symbol, base))}
    audit = auditar_funding_v18(series)
    c = audit.simbolos[0]
    assert c.duplicados == 1
    assert c.n_dias_con_evento == 1
    assert c.apto is False


def test_intervalos_8h_y_4h_se_reportan_sin_imponer_cadencia_fija():
    symbol = UNIVERSO_FUNDING_V18[0]
    base = int(DESDE_V18.timestamp() * 1000)
    eventos = (
        _evento(symbol, base + 6),
        _evento(symbol, base + 8 * _HORA_MS + 9),
        _evento(symbol, base + 12 * _HORA_MS + 13),
    )
    audit = auditar_funding_v18({symbol: eventos})
    intervalos = dict(audit.simbolos[0].intervalos_horas)
    assert intervalos["8"] == 1
    assert intervalos["4"] == 1


def test_gap_mayor_24h_es_visible_pero_no_se_rellena():
    symbol = UNIVERSO_FUNDING_V18[0]
    base = int(DESDE_V18.timestamp() * 1000)
    eventos = (
        _evento(symbol, base),
        _evento(symbol, base + 3 * _DIA_MS),
    )
    audit = auditar_funding_v18({symbol: eventos})
    c = audit.simbolos[0]
    assert c.n_dias_con_evento == 2
    assert c.gaps_mayores_24h == 1
    assert c.max_gap_horas == Decimal("72.000")


def test_simbolos_ausentes_siguen_visibles_en_manifest():
    audit = auditar_funding_v18({})
    assert len(audit.simbolos) == len(UNIVERSO_FUNDING_V18)
    assert all(c.n_eventos == 0 for c in audit.simbolos)
    assert audit.dataset_apto is False
