from __future__ import annotations

import pytest

from backend.economia.edge_historico import construir_observaciones


def test_horizonte_fraccional_no_se_redondea_silenciosamente():
    with pytest.raises(ValueError):
        construir_observaciones("BTCUSDT", (), horizontes_horas=(4.5,))
