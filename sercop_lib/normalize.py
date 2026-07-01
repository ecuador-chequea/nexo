"""
Convierte un "release" OCDS (el formato anidado que usa SERCOP) en una
ficha plana con los campos que pediste: número de proceso, estado,
institución contratante, proveedor, fecha del proceso, enlace.

OJO — dos cosas que hay que verificar con casos reales antes de confiar
ciegamente en esto:

1. "Estado" no es un campo directo en OCDS. Se infiere de qué etapas
   (tags) están presentes en el release. La lógica de abajo es una
   primera aproximación; conviene validarla contra 10-15 procesos que
   tú ya conozcas el estado real, y ajustar.

2. El enlace al portal: no logré confirmar el patrón exacto de URL para
   enlazar directo a un proceso (el buscador de datosabiertos es una
   SPA renderizada en el cliente). Por ahora se genera un enlace de
   *búsqueda* por OCID en el buscador de datos abiertos, no un enlace
   directo a la ficha. Hay que probarlo con un OCID real y ajustar
   build_portal_link() si el patrón no funciona.
"""
from dataclasses import dataclass, asdict
from typing import Optional


ESTADO_POR_ETAPA = {
    "implementation": "Implementación / ejecución",
    "contract": "Contratado",
    "award": "Adjudicado",
    "tender": "En proceso de oferta",
    "planning": "Planificación",
}

# Orden de prioridad: si el release tiene varias etapas, se reporta la más avanzada
_ORDEN_ETAPAS = ["implementation", "contract", "award", "tender", "planning"]


@dataclass
class Ficha:
    numero_proceso: str
    estado: str
    institucion_contratante: str
    proveedor: str
    fecha_proceso: str
    monto: Optional[str]
    enlace: str
    ocid: str

    def to_dict(self):
        return asdict(self)


def _inferir_estado(tags: list[str]) -> str:
    for etapa in _ORDEN_ETAPAS:
        if etapa in tags:
            return ESTADO_POR_ETAPA[etapa]
    return "Estado no determinado"


def _extraer_proveedor(release: dict) -> str:
    # el proveedor "ganador" suele aparecer en awards[].suppliers[]
    awards = release.get("awards", [])
    for award in awards:
        suppliers = award.get("suppliers", [])
        if suppliers:
            return suppliers[0].get("name", "")
    # si no hay adjudicación todavía, no hay proveedor definitivo
    return "(sin adjudicar)"


def build_portal_link(ocid: str) -> str:
    """Enlace directo al proceso. Patrón VERIFICADO contra resultados reales
    de datosabiertos.compraspublicas.gob.ec (antes esto era una suposición
    sin confirmar; ya se comprobó con procesos reales)."""
    return f"https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/ocds/{ocid}"


def normalize_search_result(item: dict) -> Optional[Ficha]:
    """Normaliza un item de /api/search_ocds.

    Nombres de campo CONFIRMADOS contra la respuesta real (no contra
    documentación de terceros, que resultó estar desactualizada): id,
    ocid, year, month, method, internal_type, locality, region,
    suppliers, buyer, amount, date, title, description, budget.

    'estado' sigue sin venir en la búsqueda; se resuelve solo al abrir
    el detalle (ver get_full_ficha en app.py)."""
    ocid = item.get("ocid", "")
    if not ocid:
        return None

    return Ficha(
        numero_proceso=ocid,
        estado="(clic para ver detalle)",
        institucion_contratante=item.get("buyer", ""),
        proveedor=item.get("suppliers") or "(ver ficha — no indexado en la búsqueda)",
        fecha_proceso=item.get("date", ""),
        monto=item.get("amount"),
        enlace=build_portal_link(ocid),
        ocid=ocid,
    )


def normalize_release(record: dict) -> Optional[Ficha]:
    """record: un objeto tal como lo devuelve el endpoint /api/record.
    Se usa el último release (más reciente) para reflejar el estado
    más actual del proceso.

    NOTA sobre el ocid: se prueba primero en el nivel superior de la
    respuesta (record['ocid']) y, si no está ahí, se usa el que trae
    el propio release (release['ocid']). Esto se agregó porque en la
    práctica el nivel superior venía vacío para el ocid mientras que
    el resto de campos (buyer, awards, tender) sí se extraían bien de
    adentro de releases — señal de que la respuesta es más parecida a
    un "release package" OCDS que a un "record package", donde el
    ocid no siempre se repite arriba."""
    releases = record.get("releases", [])
    if not releases:
        return None

    release = releases[-1]  # el más reciente
    ocid = record.get("ocid") or release.get("ocid", "")
    tags = release.get("tag", [])

    buyer = release.get("buyer", {}) or {}
    tender = release.get("tender", {}) or {}

    fecha = release.get("date", "") or tender.get("tenderPeriod", {}).get("startDate", "")
    monto = None
    tender_value = tender.get("value", {})
    if tender_value:
        amount = tender_value.get("amount")
        currency = tender_value.get("currency", "")
        if amount is not None:
            monto = f"{amount} {currency}".strip()

    return Ficha(
        numero_proceso=ocid,
        estado=_inferir_estado(tags),
        institucion_contratante=buyer.get("name", ""),
        proveedor=_extraer_proveedor(release),
        fecha_proceso=fecha,
        monto=monto,
        enlace=build_portal_link(ocid),
        ocid=ocid,
    )


def normalize_bulk_row(row: dict) -> Optional[Ficha]:
    """Normaliza una fila del CSV/JSON de descarga masiva (main.csv /
    main.jsonl). La estructura de las descargas masivas es más plana
    que la del API en vivo pero los nombres de columna hay que
    confirmarlos contra el archivo real que se cargue — este mapeo usa
    los nombres más probables según la documentación pública, pero
    puede necesitar ajuste."""
    ocid = row.get("ocid") or row.get("main_ocid", "")
    if not ocid:
        return None

    return Ficha(
        numero_proceso=ocid,
        estado=row.get("status", row.get("tender_status", "Estado no determinado")),
        institucion_contratante=row.get("buyer_name", row.get("parties_name", "")),
        proveedor=row.get("awards_suppliers_name", "(sin adjudicar)"),
        fecha_proceso=row.get("date", row.get("tender_tenderPeriod_startDate", "")),
        monto=row.get("tender_value_amount"),
        enlace=build_portal_link(ocid),
        ocid=ocid,
    )
