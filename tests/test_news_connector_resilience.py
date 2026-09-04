"""Regresiones de resiliencia para el contexto externo de noticias.

Las noticias son auxiliares: una credencial ausente o un proveedor lento no
pueden bloquear ni falsear el ciclo de trading. Estas pruebas no salen a red.
"""

import requests

from backend.connectors.apis.news_connector import (
    NEWS_REQUEST_TIMEOUT_SECONDS,
    NewsConnector,
)


class RespuestaFalsa:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_sin_credenciales_no_hace_red(monkeypatch):
    conector = NewsConnector()
    conector.api_key = None
    conector.newsapi_key = None

    def red_prohibida(*args, **kwargs):
        raise AssertionError("sin credencial no debe existir requests.get")

    monkeypatch.setattr(requests, "get", red_prohibida)

    assert conector.obtener_noticias_recientes() == []
    assert conector.obtener_noticias_stocks() == []
    assert conector.obtener_noticias_forex() == []
    assert conector.obtener_noticias_combinadas() == []


def test_cryptopanic_usa_timeout_acotado(monkeypatch):
    conector = NewsConnector()
    conector.api_key = "token-sintetico"
    vistos = []

    def get_falso(url, *, params, timeout):
        vistos.append((url, timeout, params.get("auth_token")))
        return RespuestaFalsa({"results": [{"title": "Titular"}]})

    monkeypatch.setattr(requests, "get", get_falso)

    assert conector.obtener_noticias_recientes(1) == ["Titular"]
    assert vistos == [(conector.base_url, NEWS_REQUEST_TIMEOUT_SECONDS, "token-sintetico")]


def test_newsapi_usa_timeout_acotado_en_ambos_contextos(monkeypatch):
    conector = NewsConnector()
    conector.newsapi_key = "key-sintetica"
    timeouts = []

    def get_falso(url, *, params, timeout):
        timeouts.append(timeout)
        return RespuestaFalsa({"articles": [{"title": "Contexto"}]})

    monkeypatch.setattr(requests, "get", get_falso)

    assert conector.obtener_noticias_stocks(1) == ["Contexto"]
    assert conector.obtener_noticias_forex(1) == ["Contexto"]
    assert timeouts == [NEWS_REQUEST_TIMEOUT_SECONDS, NEWS_REQUEST_TIMEOUT_SECONDS]


def test_timeout_de_proveedor_degrada_a_lista_vacia(monkeypatch):
    conector = NewsConnector()
    conector.api_key = "token-sintetico"

    def get_lento(*args, **kwargs):
        raise requests.Timeout("proveedor lento")

    monkeypatch.setattr(requests, "get", get_lento)

    assert conector.obtener_noticias_recientes() == []
