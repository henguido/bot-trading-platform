"""Smoke HTTP de solo lectura para el frontend PAPER v1.

Valida que la interfaz ya arrancada responda como documento HTML. No inicia
sesión, no llama endpoints de trading y no modifica estado. Está pensado para
ser ejecutado por el launcher después de levantar Vite, antes de declarar el
stack PAPER listo para uso.
"""
from __future__ import annotations

import argparse
import json

import requests


def evaluar_respuesta(status_code, content_type, body) -> dict:
    checks = []

    status_ok = status_code == 200
    checks.append({
        "codigo": "FRONTEND_HTTP_200",
        "nivel": "OK" if status_ok else "BLOCKER",
        "detalle": f"status={status_code!r}",
    })

    tipo = str(content_type or "").lower()
    html_ok = "text/html" in tipo
    checks.append({
        "codigo": "FRONTEND_HTML",
        "nivel": "OK" if html_ok else "BLOCKER",
        "detalle": f"content-type={content_type!r}",
    })

    texto = body if isinstance(body, str) else ""
    documento_ok = "<html" in texto.lower() or "<!doctype html" in texto.lower()
    checks.append({
        "codigo": "FRONTEND_DOCUMENT",
        "nivel": "OK" if documento_ok else "BLOCKER",
        "detalle": "documento HTML detectado" if documento_ok else "respuesta sin documento HTML reconocible",
    })

    blockers = [c for c in checks if c["nivel"] == "BLOCKER"]
    return {
        "release": "PAPER_V1_FRONTEND",
        "ready": not blockers,
        "status": "READY" if not blockers else "NOT_READY",
        "blockers": len(blockers),
        "checks": checks,
    }


def consultar_frontend(base_url: str, *, timeout: float = 5.0, session=None) -> dict:
    cliente = session or requests.Session()
    respuesta = cliente.get(base_url.rstrip("/"), timeout=timeout)
    return evaluar_respuesta(
        respuesta.status_code,
        respuesta.headers.get("content-type"),
        respuesta.text,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Smoke HTTP del frontend PAPER v1")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    try:
        resultado = consultar_frontend(args.base_url, timeout=args.timeout)
    except Exception as exc:
        resultado = {
            "release": "PAPER_V1_FRONTEND",
            "ready": False,
            "status": "NOT_READY",
            "blockers": 1,
            "checks": [{
                "codigo": "FRONTEND_HTTP",
                "nivel": "BLOCKER",
                "detalle": f"no se pudo validar frontend: {type(exc).__name__}: {exc}",
            }],
        }

    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
