# logger.py

import csv
import os

# Nombre de los archivos de registro
LOG_TXT = "registro_operaciones.txt"
LOG_CSV = "registro_operaciones.csv"

def registrar_operacion(fecha_hora, symbol, decision, precio_actual, capital_usd, position_quantity):
    """Registra una operación en formato bonito (.txt) y en formato estructurado (.csv)"""

    # Formato bonito para el .txt
    entrada_txt = (
        f"[{fecha_hora}] Análisis {symbol}:\n"
        f"    - Decisión: {decision}\n"
        f"    - Precio actual: ${precio_actual:,.2f}\n"
        f"    - Capital disponible: ${capital_usd:,.2f}\n"
        f"    - Cantidad invertida: {position_quantity:.6f} unidades\n\n"
    )

    # Escribir en el archivo .txt
    with open(LOG_TXT, mode='a', encoding='utf-8') as file_txt:
        file_txt.write(entrada_txt)

    # Formato estructurado para el .csv
    archivo_nuevo = not os.path.exists(LOG_CSV)

    with open(LOG_CSV, mode='a', newline='', encoding='utf-8') as file_csv:
        writer = csv.writer(file_csv)

        if archivo_nuevo:
            writer.writerow(["fecha_hora", "symbol", "decision", "precio_actual", "capital_usd", "position_quantity"])

        writer.writerow([
            fecha_hora,
            symbol,
            decision,
            f"{precio_actual:.2f}",
            f"{capital_usd:.2f}",
            f"{position_quantity:.6f}"
        ])
