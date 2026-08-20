from decimal import Decimal

from backend.economia.auditoria_perp_v16 import auditar_perp_v16
from backend.economia.edge_historico import Vela
from backend.economia.protocolo_perp_v16 import DESDE_V16, DIAS_ESPERADOS_V16

DIA = 86_400_000
T0 = int(DESDE_V16.timestamp() * 1000)


def _vela(ts):
    return Vela(ts, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("1"), ts + DIA - 1, Decimal("100"), 1)


def _serie(n=DIAS_ESPERADOS_V16):
    return tuple(_vela(T0 + i * DIA) for i in range(n))


def test_15_series_completas_hacen_dataset_apto():
    r = auditar_perp_v16({f"S{i:02d}": _serie() for i in range(15)})
    assert r.dataset_apto is True
    assert r.n_simbolos_aptos == 15
    assert r.fraccion_cross_section_completa == Decimal("1")


def test_14_series_no_alcanzan_cross_section():
    r = auditar_perp_v16({f"S{i:02d}": _serie() for i in range(14)})
    assert r.dataset_apto is False
    assert "SIMBOLOS_APTOS_INSUFICIENTES" in r.motivos_rechazo
    assert "COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE" in r.motivos_rechazo


def test_gap_es_visible_y_no_se_rellena():
    serie = list(_serie())
    del serie[100]
    r = auditar_perp_v16({f"S{i:02d}": tuple(serie) for i in range(15)})
    c = r.simbolos[0]
    assert c.n_gaps == 1
    assert c.max_gap_dias == 1
    assert c.n_dias == DIAS_ESPERADOS_V16 - 1


def test_universo_tardio_resta_cobertura_real():
    tarde = tuple(_vela(T0 + i * DIA) for i in range(300, DIAS_ESPERADOS_V16))
    r = auditar_perp_v16({f"S{i:02d}": tarde for i in range(15)})
    assert r.dataset_apto is False
    assert all(c.fraccion_cobertura < Decimal("0.95") for c in r.simbolos)
