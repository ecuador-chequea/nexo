"""
Parser de consultas en lenguaje libre a filtros estructurados.

Deliberadamente NO usa un LLM. La razón: para nombres de instituciones,
un modelo de lenguaje puede "inventar" o parafrasear el nombre oficial
("Presidencia" -> "Gobierno Nacional", por ejemplo), mientras que el
matching difuso (fuzzy) contra los nombres reales que existen en los
datos de SERCOP es más preciso porque compara contra la verdad, no
contra lo que el modelo cree que debería decir.

El resultado de parse_query() SIEMPRE debe mostrarse al usuario antes
de ejecutar la búsqueda, para que confirme o corrija — nunca se debe
ejecutar una búsqueda "a ciegas" basada en una interpretación automática.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz, process as rf_process

from .institutions import INSTITUTION_SEEDS

CURRENT_YEAR = 2026  # ajustar si hace falta; también se puede pasar por parámetro

# Palabras conectoras que indican rango de fechas
_RANGE_WORDS = r"(?:desde|entre|del?|a|hasta|y|-|/|al)"

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass
class ParsedQuery:
    raw_text: str
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    institution_guess: Optional[str] = None       # alias detectado, ej. "presidencia"
    institution_candidates: list = field(default_factory=list)  # nombres reales sugeridos
    keyword: str = ""                               # lo que sobra, para full-text search
    notes: list = field(default_factory=list)


def _extract_years(text: str) -> tuple[Optional[int], Optional[int], str]:
    """Busca años de 4 dígitos y determina si es rango o año único.
    Devuelve (year_from, year_to, texto_sin_fechas)."""
    years = [int(m.group()) for m in _YEAR_RE.finditer(text)]
    if not years:
        return None, None, text

    year_from, year_to = min(years), max(years)

    # elimina del texto los años y palabras conectoras adyacentes para
    # no contaminar la extracción de institución/keyword
    cleaned = _YEAR_RE.sub("", text)
    cleaned = re.sub(
        r"\b(desde|entre|hasta|del?|al?)\b", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -/")
    return year_from, year_to, cleaned


def _extract_institution(text: str, score_cutoff: int = 75):
    """Intenta reconocer un alias de institución dentro del texto usando
    fuzzy matching contra INSTITUTION_SEEDS. Devuelve (alias, candidatos_reales,
    texto_restante)."""
    tokens_lower = text.lower()

    best_alias = None
    best_score = 0
    for alias in INSTITUTION_SEEDS:
        score = fuzz.partial_ratio(alias, tokens_lower)
        if score > best_score:
            best_score = score
            best_alias = alias

    if best_score < score_cutoff or best_alias is None:
        return None, [], text

    candidates = INSTITUTION_SEEDS[best_alias]

    # remueve el alias del texto (aproximado, por palabras) para aislar
    # el resto como keyword
    remaining = text
    for word in best_alias.split():
        remaining = re.sub(re.escape(word), "", remaining, flags=re.IGNORECASE)
    remaining = re.sub(r"\s{2,}", " ", remaining).strip()

    return best_alias, candidates, remaining


def parse_query(text: str, current_year: int = CURRENT_YEAR) -> ParsedQuery:
    result = ParsedQuery(raw_text=text)

    year_from, year_to, text_no_dates = _extract_years(text)
    result.year_from = year_from
    result.year_to = year_to
    if year_from and not year_to:
        result.notes.append(f"Se detectó un solo año ({year_from}); se buscará solo ese año.")
    if year_from and year_to and year_from == year_to:
        result.year_to = None

    alias, candidates, remaining = _extract_institution(text_no_dates)
    result.institution_guess = alias
    result.institution_candidates = candidates
    if alias:
        result.notes.append(
            f"Se interpretó '{alias}' como institución. Verifica el nombre exacto sugerido "
            f"antes de buscar."
        )

    result.keyword = remaining.strip()
    if not result.keyword and not alias:
        result.notes.append(
            "No se detectó ni institución ni fecha; se usará todo el texto como palabra clave."
        )
        result.keyword = text.strip()

    return result


def rank_institution_names(alias_or_text: str, known_names: list[str], limit: int = 5):
    """Dado un texto y una lista de nombres reales de compradores/proveedores
    (por ejemplo, extraídos de un archivo de descarga masiva ya cargado),
    devuelve los mejores matches difusos. Útil en el modo de archivos, donde
    no hay un servidor que haga el matching por nosotros."""
    if not known_names:
        return []
    matches = rf_process.extract(
        alias_or_text, known_names, scorer=fuzz.WRatio, limit=limit
    )
    return [(name, score) for name, score, _ in matches]
