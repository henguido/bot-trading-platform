import threading
import time

from backend.coordinador import CoordinadorTrading


class CandadoFalso:
    def __init__(self):
        self.adquirido = False
        self.liberaciones = 0

    def adquirir(self):
        self.adquirido = True
        return True

    def liberar(self):
        self.adquirido = False
        self.liberaciones += 1


def test_shutdown_cooperativo_detiene_hilo_antes_de_liberar_liderazgo():
    stop = threading.Event()
    candado = CandadoFalso()
    iniciado = threading.Event()

    def loop():
        iniciado.set()
        while not stop.wait(0.01):
            pass

    c = CoordinadorTrading(
        loop,
        candado=candado,
        stop_event=stop,
        stop_timeout=1.0,
    )

    assert c.iniciar() is True
    assert iniciado.wait(0.5)
    assert c.activo is True
    assert candado.adquirido is True

    assert c.detener() is True
    assert stop.is_set() is True
    assert c.activo is False
    assert c.es_lider is False
    assert candado.adquirido is False
    assert candado.liberaciones == 1


def test_hilo_no_cooperativo_retiene_candado_y_liderazgo():
    stop = threading.Event()
    candado = CandadoFalso()
    liberar_loop = threading.Event()

    def loop():
        liberar_loop.wait(1.0)

    c = CoordinadorTrading(
        loop,
        candado=candado,
        stop_event=stop,
        stop_timeout=0.01,
    )

    try:
        assert c.iniciar() is True
        time.sleep(0.01)
        assert c.detener() is False
        assert stop.is_set() is True
        assert c.es_lider is True
        assert candado.adquirido is True
        assert candado.liberaciones == 0
    finally:
        liberar_loop.set()
        time.sleep(0.02)
        assert c.detener() is True
        assert candado.adquirido is False
