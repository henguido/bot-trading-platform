"""
Herramienta administrativa: reinicia el esquema de la base de datos.

DESTRUCTIVA. Borra TODAS las tablas y las vuelve a crear vacias: usuarios,
portafolios, activos, transacciones y auditoria de decisiones.

Antes, este archivo ejecutaba drop_all() en el momento de importarlo, sin
confirmacion, sin comprobar el entorno y contra la DATABASE_URL real. Un doble
clic bastaba para destruir produccion (P0-7).

Ahora:
  - importar el modulo NO ejecuta nada;
  - por defecto se niega a operar y solo muestra el plan (simulacion);
  - exige una frase de confirmacion exacta, no un simple "yes";
  - detecta el entorno y trata lo desconocido como produccion (fallo seguro);
  - contra produccion exige ademas una variable de entorno deliberada;
  - nunca imprime la DATABASE_URL completa ni credenciales.

Uso:
    python borrar_historial.py                      # solo muestra el plan
    python borrar_historial.py --ejecutar --confirmar BORRAR-TODO-LOCAL
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit

# Variable de entorno adicional exigida para operar contra produccion.
VAR_AUTORIZACION_PRODUCCION = "PERMITIR_RESET_PRODUCCION"
VALOR_AUTORIZACION_PRODUCCION = "si-acepto-perder-los-datos"

# Hosts que delatan una base de datos gestionada/remota.
INDICIOS_PRODUCCION = (
    "render.com", "amazonaws.com", "neon.tech", "supabase.co",
    "azure.com", "googleapis.com", "heroku", "railway.app",
)
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1", "")


def describir_destino(database_url: str) -> str:
    """
    Describe la base de datos objetivo SIN revelar usuario, contrasena ni la
    URL completa. Es lo unico que se muestra al operador.
    """
    if not database_url:
        return "(sin DATABASE_URL configurada)"

    partes = urlsplit(database_url)
    if partes.scheme.startswith("sqlite"):
        nombre = os.path.basename(partes.path) or ":memory:"
        return f"sqlite -> fichero '{nombre}'"

    host = partes.hostname or "?"
    base = (partes.path or "").lstrip("/") or "?"
    return f"{partes.scheme} -> host={host} base={base} (usuario y contrasena ocultos)"


def detectar_entorno(database_url: str) -> str:
    """
    Devuelve 'local' o 'produccion'.

    Fallo seguro: si no se puede determinar con certeza que es local, se
    clasifica como produccion. Es preferible bloquear de mas que borrar de mas.
    """
    if not database_url:
        return "produccion"

    partes = urlsplit(database_url)

    if partes.scheme.startswith("sqlite"):
        return "local"

    host = (partes.hostname or "").lower()
    if any(indicio in host for indicio in INDICIOS_PRODUCCION):
        return "produccion"
    if host in HOSTS_LOCALES:
        return "local"
    return "produccion"


def frase_requerida(entorno: str) -> str:
    """Frase exacta que el operador debe teclear. Deliberadamente incomoda."""
    return f"BORRAR-TODO-{entorno.upper()}"


def _reset_real() -> None:
    """Ejecuta el borrado real. Se importa aqui dentro para que importar este
    modulo no arrastre ninguna conexion a base de datos."""
    from backend.app.database import engine
    from backend.app import models

    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)


def main(argv=None, *, database_url=None, ejecutor=None, entorno_os=None) -> int:
    """
    Devuelve 0 si termino correctamente (incluida la simulacion o la
    cancelacion) y un codigo distinto de 0 si se rechazo la operacion.

    `database_url`, `ejecutor` y `entorno_os` se inyectan en las pruebas para
    no tocar nunca la base de datos configurada en .env.
    """
    parser = argparse.ArgumentParser(
        description="Reinicia el esquema de la base de datos (DESTRUCTIVO).",
    )
    parser.add_argument("--ejecutar", action="store_true",
                        help="Ejecuta de verdad. Sin este flag solo se muestra el plan.")
    parser.add_argument("--confirmar", default="",
                        help="Frase de confirmacion exacta (ver salida del plan).")
    args = parser.parse_args(argv)

    variables = os.environ if entorno_os is None else entorno_os
    url = database_url if database_url is not None else variables.get("DATABASE_URL", "")
    ejecutor = ejecutor or _reset_real

    entorno = detectar_entorno(url)
    frase = frase_requerida(entorno)

    print("=" * 66)
    print("REINICIO DE BASE DE DATOS  ---  OPERACION DESTRUCTIVA")
    print("=" * 66)
    print(f"  Destino : {describir_destino(url)}")
    print(f"  Entorno : {entorno.upper()}")
    print("  Accion  : DROP de todas las tablas y creacion de un esquema vacio")
    print("            (usuarios, portafolios, activos, transacciones,")
    print("             decision_audit). Los datos NO son recuperables.")
    print("=" * 66)

    # 1) Por defecto no hace nada: solo enseña el plan.
    if not args.ejecutar:
        print("\n[SIMULACION] No se ha modificado nada.")
        print(f"  Para ejecutar de verdad:\n"
              f"    python borrar_historial.py --ejecutar --confirmar {frase}")
        return 0

    # 2) La confirmacion debe ser exacta; 'yes' o 'si' no sirven.
    if args.confirmar != frase:
        if not args.confirmar:
            print("\n[CANCELADO] Falta --confirmar. No se ha modificado nada.")
        else:
            print("\n[CANCELADO] La frase de confirmacion no coincide. "
                  "No se ha modificado nada.")
        print(f"  Se esperaba exactamente: {frase}")
        return 2

    # 3) Contra produccion hace falta una autorizacion adicional y deliberada.
    if entorno == "produccion":
        autorizacion = variables.get(VAR_AUTORIZACION_PRODUCCION, "")
        if autorizacion.strip() != VALOR_AUTORIZACION_PRODUCCION:
            print("\n[BLOQUEADO] El destino es PRODUCCION (o no se pudo verificar "
                  "que fuera local).")
            print(f"  Se requiere ademas la variable de entorno "
                  f"{VAR_AUTORIZACION_PRODUCCION} con el valor acordado.")
            print("  No se ha modificado nada.")
            return 3

    print("\n[EJECUTANDO] Reiniciando el esquema...")
    ejecutor()
    print("[OK] Esquema reiniciado.")
    return 0


if __name__ == "__main__":
    # Se carga aqui, no al importar: el modulo debe seguir siendo inocuo como
    # import. Sin esto, DATABASE_URL del .env no seria visible y la herramienta
    # clasificaria siempre el destino como PRODUCCION.
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
