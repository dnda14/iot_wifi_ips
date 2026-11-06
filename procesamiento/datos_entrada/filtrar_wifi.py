#!/usr/bin/env python3
"""
Filtra archivos TXT de escaneos Wi-Fi por una lista de BSSID conocidos.

Uso:
1. Coloca este script en la carpeta que contiene tus archivos .txt.
2. Ejecuta: python filtrar_wifi.py
3. Los resultados aparecerán en la carpeta "txt_filtrados".
   Los archivos originales no se modifican.

Los TXT deben tener una cabecera con columnas como:
timestamp_ms,fecha_hora,lugar,fuente,bssid,ssid,rssi_dbm,frecuencia_mhz,edad_s
"""

import csv
from pathlib import Path

# Carpeta donde está este script y los TXT originales.
CARPETA_ENTRADA = Path(__file__).resolve().parent
CARPETA_SALIDA = CARPETA_ENTRADA / "txt_filtrados"

# Se usan exactamente los BSSID indicados por el equipo.
# OJO: el BSSID de Lab 4 está escrito como b7:a0 según lo informado.
# Si en el TXT aparece b7:af, no se incluirá automáticamente porque es distinto.
BSSID_INFO = {
    "98:97:d1:93:e6:52": ("Lab 4", "WLAN_E650"),
    "70:0b:01:ef:f6:27": ("301", "sc-f620_5G"),
    "70:0b:01:ef:f6:26": ("301", "sc-f620"),
    "a4:88:73:40:c8:c0": ("301", "wifi_compu"),
    "a4:88:73:40:a4:00": ("Lab 3", "wifi_compu"),
    "a4:88:73:40:b7:a0": ("Lab 4", "wifi_compu"),
    "30:b5:c2:ef:3e:f0": ("301", "ACM"),
    "fc:5a:1d:7e:0e:48": ("Lab 3", "Movistar"),
}

COLUMNAS_EXTRA = ["router_area", "router_name"]


def normalizar_bssid(valor):
    """Normaliza espacios y mayúsculas/minúsculas, sin alterar el identificador."""
    return (valor or "").strip().lower()


def detectar_delimitador(muestra):
    """Detecta delimitador común; usa coma si no puede identificarlo."""
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def procesar_archivo(ruta_txt):
    try:
        with ruta_txt.open("r", encoding="utf-8-sig", newline="") as archivo:
            muestra = archivo.read(8192)
            archivo.seek(0)

            delimitador = detectar_delimitador(muestra)
            lector = csv.DictReader(archivo, delimiter=delimitador)

            if not lector.fieldnames:
                print(f"[OMITIDO] {ruta_txt.name}: archivo vacío o sin cabecera.")
                return None

            # Permite encontrar bssid aunque la cabecera tenga espacios o mayúsculas.
            nombres_normalizados = {
                nombre.strip().lower(): nombre for nombre in lector.fieldnames
                if nombre is not None
            }
            columna_bssid = nombres_normalizados.get("bssid")

            if columna_bssid is None:
                print(f"[OMITIDO] {ruta_txt.name}: no existe la columna 'bssid'.")
                return None

            columnas_originales = list(lector.fieldnames)
            columnas_salida = [
                c for c in columnas_originales if c not in COLUMNAS_EXTRA
            ] + COLUMNAS_EXTRA

            filas_filtradas = []
            encontrados = set()
            total = 0

            for fila in lector:
                total += 1
                bssid = normalizar_bssid(fila.get(columna_bssid))

                if bssid not in BSSID_INFO:
                    continue

                area, nombre_router = BSSID_INFO[bssid]
                fila["router_area"] = area
                fila["router_name"] = nombre_router
                filas_filtradas.append(fila)
                encontrados.add(bssid)

        CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
        ruta_salida = CARPETA_SALIDA / ruta_txt.name

        with ruta_salida.open("w", encoding="utf-8-sig", newline="") as archivo_salida:
            escritor = csv.DictWriter(
                archivo_salida,
                fieldnames=columnas_salida,
                delimiter=",",
                extrasaction="ignore",
            )
            escritor.writeheader()
            escritor.writerows(filas_filtradas)

        return {
            "archivo": ruta_txt.name,
            "total": total,
            "filtradas": len(filas_filtradas),
            "bssid_encontrados": encontrados,
            "salida": ruta_salida,
        }

    except (OSError, UnicodeError, csv.Error) as error:
        print(f"[ERROR] {ruta_txt.name}: {error}")
        return None


def main():
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    # Evita volver a procesar los resultados generados por este mismo script.
    archivos_txt = [
        ruta for ruta in CARPETA_ENTRADA.glob("*.txt")
        if ruta.is_file() and ruta.parent != CARPETA_SALIDA
    ]

    if not archivos_txt:
        print("No se encontraron archivos .txt junto al script.")
        print(f"Carpeta revisada: {CARPETA_ENTRADA}")
        return

    print(f"Archivos encontrados: {len(archivos_txt)}")
    print(f"Resultados en: {CARPETA_SALIDA}\n")

    bssid_vistos = set()
    total_original = 0
    total_filtrado = 0

    for ruta in sorted(archivos_txt):
        resultado = procesar_archivo(ruta)
        if resultado is None:
            continue

        total_original += resultado["total"]
        total_filtrado += resultado["filtradas"]
        bssid_vistos.update(resultado["bssid_encontrados"])

        print(
            f"[OK] {resultado['archivo']}: "
            f"{resultado['filtradas']} de {resultado['total']} filas conservadas "
            f"-> {resultado['salida'].name}"
        )

    print("\n--- Resumen general ---")
    print(f"Filas revisadas: {total_original}")
    print(f"Filas filtradas: {total_filtrado}")
    print(f"BSSID objetivo encontrados: {len(bssid_vistos)} de {len(BSSID_INFO)}")

    print("\nBSSID objetivo sin coincidencias en ningún TXT:")
    faltantes = sorted(set(BSSID_INFO) - bssid_vistos)
    if faltantes:
        for bssid in faltantes:
            area, nombre = BSSID_INFO[bssid]
            print(f"  - {bssid} ({area} / {nombre})")
    else:
        print("  Ninguno")

    print(
        "\nNota: el script filtra por BSSID exacto. "
        "No reemplaza ni modifica los archivos originales."
    )


if __name__ == "__main__":
    main()
