"""
Lectura de archivos de descarga masiva de SERCOP (CSV, XLSX, JSON/JSONL,
incluyendo .gz). Diseñado para no cargar todo en memoria de golpe,
porque un año completo puede pesar cientos de MB.

Nota sobre columnas: las descargas masivas de SERCOP tienen su propio
esquema de nombres de columna (no es idéntico al JSON del API en vivo).
normalize_bulk_row() en normalize.py asume nombres probables, pero hay
que confirmarlos contra el archivo real la primera vez que se use —
por eso get_column_preview() existe: úsalo para ver qué columnas trae
el archivo antes de mapear.
"""
import gzip
import io
import json
from pathlib import Path
from typing import Iterator

import pandas as pd


CHUNK_SIZE = 5000  # filas por chunk para CSV


def get_column_preview(file_obj, filename: str, n_rows: int = 5) -> pd.DataFrame:
    """Devuelve las primeras filas para que el usuario (o el código)
    verifique qué columnas trae el archivo antes de procesarlo completo."""
    file_obj.seek(0)
    if filename.endswith(".csv") or filename.endswith(".csv.gz"):
        return pd.read_csv(file_obj, nrows=n_rows)
    elif filename.endswith(".jsonl") or filename.endswith(".jsonl.gz"):
        opener = gzip.open if filename.endswith(".gz") else io.TextIOWrapper
        lines = []
        raw = file_obj.read()
        file_obj.seek(0)
        text = gzip.decompress(raw).decode("utf-8") if filename.endswith(".gz") else raw.decode("utf-8")
        for i, line in enumerate(text.splitlines()):
            if i >= n_rows:
                break
            lines.append(json.loads(line))
        return pd.json_normalize(lines)
    elif filename.endswith(".xlsx"):
        return pd.read_excel(file_obj, nrows=n_rows)
    else:
        raise ValueError(f"Formato no soportado: {filename}")


def iter_rows(file_obj, filename: str) -> Iterator[dict]:
    """Itera fila por fila (o chunk por chunk internamente) sin cargar
    todo el archivo en memoria a la vez."""
    file_obj.seek(0)

    if filename.endswith(".csv") or filename.endswith(".csv.gz"):
        for chunk in pd.read_csv(file_obj, chunksize=CHUNK_SIZE):
            for _, row in chunk.iterrows():
                yield row.to_dict()

    elif filename.endswith(".jsonl") or filename.endswith(".jsonl.gz"):
        raw = file_obj.read()
        text = gzip.decompress(raw).decode("utf-8") if filename.endswith(".gz") else raw.decode("utf-8")
        for line in text.splitlines():
            if line.strip():
                yield json.loads(line)

    elif filename.endswith(".xlsx"):
        # XLSX no soporta streaming tan bien como CSV; para archivos
        # grandes se recomienda pedir al usuario el CSV en su lugar.
        df = pd.read_excel(file_obj)
        for _, row in df.iterrows():
            yield row.to_dict()

    else:
        raise ValueError(
            f"Formato no soportado: {filename}. Usa CSV, JSONL (o .gz) o XLSX."
        )


def collect_distinct_values(file_obj, filename: str, column_candidates: list[str], max_rows_scan: int = 50000) -> set[str]:
    """Recorre el archivo (hasta max_rows_scan filas) y junta los valores
    distintos de las primeras columnas candidatas que existan, para
    alimentar el matching difuso de instituciones/proveedores en modo
    archivo (ver query_parser.rank_institution_names)."""
    values = set()
    scanned = 0
    for row in iter_rows(file_obj, filename):
        for col in column_candidates:
            if col in row and row[col]:
                values.add(str(row[col]))
        scanned += 1
        if scanned >= max_rows_scan:
            break
    return values
