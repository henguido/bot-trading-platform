"""Smoke runtime de solo lectura para PAPER v1.

Valida una instancia ya arrancada sin autenticarse, sin tocar la base de datos,
sin migrar y sin invocar endpoints de trading. Solo consulta ``/health`` y
comprueba invariantes operativos que deben cumplirse antes de considerar una
sesion PAPER util para observacion:

- modo efectivo PAPER y LIVE deshabilitado;
- esquema Alembic alineado;
- proceso de trading activo;
- instancia lider.

Uso local despues de arrancar el backend con ``scripts/start_paper.ps1`` o
``start.sh``::

    python scripts/smoke_paper_runtime.py

Puede apuntarse a otra URL con ``--base-url``. El resultado se imprime como
JSON para que pueda archivarse como evidencia de release.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

import requests

from backend.esquema import ALINEADO


@dataclass(frozen=True)
class Check:
    codigo: str
    nivel: str  # OK | BLOCKER
    detalle: str


def evaluar_health(payload) -> dict:
    """Evalua el contrato publico de ``/health`` sin inferir datos ausentes."""
    checks: list[Check] = []

    def add(codigo: str, ok: bool, detalle_ok: str, detalle_blocker: str) -> None:
        checks.append(Check(codigo, "OK" if ok else "BLOCKER",
                            detalle_ok if ok else detalle_blocker))

    if not isinstance(payload, dict):
        checks.append(Check("HEALTH_PAYLOAD", "BLOCKER", "respuesta /health no es un objeto JSON"))
    else:
        trading_mode = str(payload.get("trading_mode", "")).upper()
        modo_real = payload.get("modo_real")
        add(
            "MODO_PAPER",
            trading_mode == "PAPER" and modo_real is False,
            "TRADING_MODE=PAPER y modo_real=false",
            f"modo inseguro o ambiguo: trading_mode={trading_mode!r} modo_real={modo_real!r}",
        )

        esquema = payload.get("esquema")
        esquema = esquema if isinstance(esquema, dict) else {}
        estado = esquema.get("estado")
        actual = esquema.get("revision_actual")
        esperada = esquema.get("revision_esperada")
        alineado = estado == ALINEADO and actual is not None and actual == esperada
        add(
            "ALEMBIC",
            alineado,
            f"esquema alineado en {actual}",
            f"esquema no alineado: estado={estado!r} actual={actual!r} esperada={esperada!r}",
        )

        bucle = payload.get("bucle_activo")
        add(
            "BUCLE",
            bucle is True,
            "bucle operativo activo",
            f"bucle no activo: {bucle!r}; motivo={payload.get('motivo_inactivo')!r}",
        )

        lider = payload.get("es_lider")
        add(
            "LIDERAZGO",
            lider is True,
            "instancia actual es lider",
            f"instancia no lider: {lider!r}",
        )

    blockers = [c for c in checks if c.nivel == "BLOCKER"]
    return {
        "release": "PAPER_V1_RUNTIME",
        "ready": not blockers,
        "status": "READY" if not blockers else "NOT_READY",
        "blockers": len(blockers),
        "checks": [asdict(c) for c in checks],
    }


def consultar_health(base_url: str, *, timeout: float = 5.0, session=None) -> dict:
    """Consulta exclusivamente ``GET /health`` y devuelve su JSON."""
    cliente = session or requests.Session()
    url = f"{base_url.rstrip('/')}/health"
    respuesta = cliente.get(url, timeout=timeout)
    respuesta.raise_for_status()
    payload = respuesta.json()
    if not isinstance(payload, dict):
        raise ValueError("/health no devolvio un objeto JSON")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Smoke runtime de solo lectura para PAPER v1")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    try:
        payload = consultar_health(args.base_url, timeout=args.timeout)
        resultado = evaluar_health(payload)
    except Exception as exc:
        resultado = {
            "release": "PAPER_V1_RUNTIME",
            "ready": False,
            "status": "NOT_READY",
            "blockers": 1,
            "checks": [{
                "codigo": "HEALTH_HTTP",
                "nivel": "BLOCKER",
                "detalle": f"no se pudo validar /health: {type(exc).__name__}: {exc}",
            }],
        }

    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
