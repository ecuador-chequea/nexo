"""
Cliente para las APIs en vivo de SERCOP (search_ocds y record).

Incluye caché local en SQLite: dado que el portal es lento/inestable
(según reportas), no tiene sentido re-consultar el mismo año+keyword
cada vez que recargas la app. El caché tiene un TTL configurable.
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

import requests

SEARCH_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds"
RECORD_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/record"

CACHE_DB = Path(__file__).parent.parent / "cache.sqlite3"
DEFAULT_TTL_SECONDS = 60 * 60 * 12  # 12 horas


def _get_conn():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cache (
            cache_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )"""
    )
    return conn


def _cache_get(key: str, ttl: int) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT payload, fetched_at FROM cache WHERE cache_key = ?", (key,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    payload, fetched_at = row
    if time.time() - fetched_at > ttl:
        return None
    return json.loads(payload)


def _cache_set(key: str, payload: dict):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cache (cache_key, payload, fetched_at) VALUES (?, ?, ?)",
        (key, json.dumps(payload), time.time()),
    )
    conn.commit()
    conn.close()


def _request_with_retries(url: str, params: dict, max_retries: int = 3, timeout: int = 30) -> dict:
    last_exc = None
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))  # backoff simple
    raise RuntimeError(
        f"No se pudo consultar {url} tras {max_retries} intentos. "
        f"El portal puede estar caído o lento. Último error: {last_exc}"
    )


def search_year(
    year: int,
    keyword: str = "",
    buyer: str = "",
    supplier: str = "",
    max_pages: int = 30,
    use_cache: bool = True,
    ttl: int = DEFAULT_TTL_SECONDS,
    progress_callback=None,
) -> list[dict]:
    """Busca procesos para UN año. Para rangos de años, llamar varias
    veces (ver search_year_range)."""
    cache_key = f"search|{year}|{keyword}|{buyer}|{supplier}"
    if use_cache:
        cached = _cache_get(cache_key, ttl)
        if cached is not None:
            return cached

    all_results = []
    page = 1
    while page <= max_pages:
        params = {"year": year, "search": keyword, "page": page}
        if buyer:
            params["buyer"] = buyer
        if supplier:
            params["supplier"] = supplier

        data = _request_with_retries(SEARCH_URL, params)

        # La forma exacta de la respuesta puede variar; se maneja de
        # forma defensiva probando las claves más probables.
        registros = data.get("data") or data.get("records") or []
        if not registros:
            break

        all_results.extend(registros)
        if progress_callback:
            progress_callback(year, page, len(all_results))

        page += 1
        time.sleep(0.4)  # ser buen ciudadano con el servidor

    if use_cache:
        _cache_set(cache_key, all_results)

    return all_results


def search_year_range(
    year_from: int,
    year_to: Optional[int] = None,
    keyword: str = "",
    buyer: str = "",
    supplier: str = "",
    progress_callback=None,
) -> list[dict]:
    year_to = year_to or year_from
    combined = []
    for year in range(year_from, year_to + 1):
        combined.extend(
            search_year(
                year, keyword=keyword, buyer=buyer, supplier=supplier,
                progress_callback=progress_callback,
            )
        )
    return combined


def get_record(ocid: str, use_cache: bool = True, ttl: int = DEFAULT_TTL_SECONDS) -> dict:
    cache_key = f"record|{ocid}"
    if use_cache:
        cached = _cache_get(cache_key, ttl)
        if cached is not None:
            return cached

    data = _request_with_retries(RECORD_URL, {"ocid": ocid})

    if use_cache:
        _cache_set(cache_key, data)
    return data
