from scripts.analyze_edge_calibration_05f import construir_resumen


def _obs(*, p25, mediana, media, real, coste=20.0):
    return {
        "settled": True,
        "realized_gross_bps": real,
        "known_cost_total_bps": coste,
        "evaluation": {
            "edge": {
                "retorno_p25_bps": p25,
                "retorno_mediano_bps": mediana,
                "retorno_medio_bps": media,
            }
        },
    }


def test_05f_compara_estimadores_sin_modificar_05a():
    estado = {"observations": [
        _obs(p25=-10, mediana=30, media=40, real=60),
        _obs(p25=-5, mediana=15, media=35, real=-30),
    ]}
    r = construir_resumen(estado)
    assert r["phase"] == "05F"
    assert r["modifies_05a"] is False
    assert r["calibratable_oos_observations"] == 2
    assert r["estimators"]["p25"]["hypothetical_approved"] == 0
    assert r["estimators"]["media"]["hypothetical_approved"] == 2


def test_05f_no_backfillea_observaciones_antiguas_sin_media():
    vieja = {
        "settled": True,
        "realized_gross_bps": 100,
        "known_cost_total_bps": 20,
        "evaluation": {"edge": {
            "retorno_p25_bps": -20,
            "retorno_mediano_bps": 10,
        }},
    }
    r = construir_resumen({"observations": [vieja]})
    assert r["matured_05a_observations"] == 1
    assert r["calibratable_oos_observations"] == 0
    assert r["estimators"]["p25"]["predictions"] == 0
