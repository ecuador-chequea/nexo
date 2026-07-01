import streamlit as st
import pandas as pd

from sercop_lib.query_parser import parse_query, rank_institution_names
from sercop_lib import api_client
from sercop_lib import bulk_loader
from sercop_lib.normalize import (
    normalize_release, normalize_bulk_row, normalize_search_result, Ficha,
)

st.set_page_config(page_title="Nexo — ChequeaLab", layout="wide")
st.title("Nexo")
st.caption(
    "ChequeaLab · Rastreo de compras públicas — SERCOP. "
    "Busca en la API en vivo de datos abiertos de SERCOP o carga archivos de "
    "descarga masiva. La interpretación de tu consulta se muestra antes de "
    "buscar — revísala y corrígela si hace falta."
)

with st.expander("ℹ️ Cómo usar Nexo", expanded=False):
    st.markdown(
        "Escribe tu búsqueda en lenguaje libre (por ejemplo: *contratos "
        "comunicación presidencia desde 2023-2025*) y da clic en **Buscar en "
        "SERCOP**. Nexo interpreta el período, la institución y la palabra "
        "clave, y los muestra en campos editables — corrígelos si algo no "
        "quedó bien interpretado antes de buscar. Los resultados aparecen en "
        "una tabla; **haz clic en el checkbox de la izquierda de una fila** "
        "para abrir la ficha completa del proceso, con institución, "
        "proveedor, estado, monto y el enlace directo al portal. "
        "**Usa siempre la ficha, no la tabla, como fuente para una nota** — "
        "la tabla puede tener datos desactualizados que la ficha corrige al "
        "consultar el proceso en tiempo real."
    )

# Columnas probables donde buscar nombres de comprador/proveedor en
# archivos de descarga masiva. Ajustar si tu archivo trae otros nombres
# (usa la vista previa de columnas para confirmar).
BUYER_SUPPLIER_COLUMNS = [
    "buyer_name", "parties_name", "awards_suppliers_name", "tender_procuringEntity_name",
]

tab_live, tab_bulk = st.tabs(["📡 Búsqueda en vivo (API)", "📁 Archivos de descarga masiva"])


def render_query_box(key_prefix: str):
    """Caja de búsqueda en lenguaje libre + campos editables.

    NOTA sobre un bug que hubo aquí: Streamlit solo usa el parámetro
    `value=` de un widget la PRIMERA vez que se renderiza; en las
    siguientes ejecuciones, el widget conserva su propio valor guardado
    en session_state y el `value=` se ignora. Eso hacía que, al escribir
    una segunda búsqueda distinta, los campos de año/institución/palabra
    clave se quedaran pegados con los valores de la búsqueda anterior.
    La corrección: cuando el texto libre cambia, se escribe directamente
    en session_state ANTES de crear esos widgets — es la única forma
    confiable de actualizarlos programáticamente en Streamlit."""
    key_year_from = f"{key_prefix}_year_from"
    key_year_to = f"{key_prefix}_year_to"
    key_keyword = f"{key_prefix}_keyword"
    key_institution = f"{key_prefix}_institution"
    key_last_text = f"{key_prefix}_last_parsed_text"
    key_notes = f"{key_prefix}_parse_notes"
    key_guess = f"{key_prefix}_institution_guess"
    key_candidates = f"{key_prefix}_institution_candidates"

    # valores por defecto la primera vez que se renderiza esta caja
    st.session_state.setdefault(key_year_from, 2023)
    st.session_state.setdefault(key_year_to, st.session_state[key_year_from])
    st.session_state.setdefault(key_keyword, "")
    st.session_state.setdefault(key_institution, "")
    st.session_state.setdefault(key_notes, [])
    st.session_state.setdefault(key_candidates, [])

    free_text = st.text_input(
        "Busca en lenguaje libre (ej: 'contratos comunicación presidencia desde 2023-2025')",
        key=f"{key_prefix}_free_text",
    )

    if free_text and free_text != st.session_state.get(key_last_text):
        parsed = parse_query(free_text)
        st.session_state[key_year_from] = parsed.year_from or 2023
        st.session_state[key_year_to] = parsed.year_to or st.session_state[key_year_from]
        st.session_state[key_keyword] = parsed.keyword
        st.session_state[key_institution] = (
            parsed.institution_candidates[0] if parsed.institution_candidates else ""
        )
        st.session_state[key_notes] = parsed.notes
        st.session_state[key_guess] = parsed.institution_guess
        st.session_state[key_candidates] = parsed.institution_candidates
        st.session_state[key_last_text] = free_text

    for note in st.session_state.get(key_notes, []):
        st.info(note)

    col1, col2, col3 = st.columns(3)
    with col1:
        year_from = st.number_input(
            "Desde (año)", min_value=2008, max_value=2026, key=key_year_from,
        )
    with col2:
        year_to = st.number_input(
            "Hasta (año)", min_value=2008, max_value=2026, key=key_year_to,
        )
    with col3:
        keyword = st.text_input("Palabra clave", key=key_keyword)

    candidates = st.session_state.get(key_candidates, [])
    if candidates:
        st.caption(
            f"Institución sugerida a partir de tu texto: **{st.session_state.get(key_guess)}** → "
            f"posibles nombres reales: {', '.join(candidates)}. "
            f"Ajusta el campo de abajo si no es la correcta."
        )

    institution = st.text_input(
        "Institución contratante (opcional, nombre o fragmento)",
        key=key_institution,
    )
    supplier = st.text_input(
        "Proveedor (opcional, nombre o fragmento)",
        key=f"{key_prefix}_supplier",
    )

    return int(year_from), int(year_to), keyword, institution, supplier


def render_results_table(fichas: list[Ficha], key_prefix: str):
    if not fichas:
        st.warning("No se encontraron resultados con estos filtros.")
        return

    df = pd.DataFrame([f.to_dict() for f in fichas])
    st.write(f"**{len(df)} procesos encontrados**")

    event = st.dataframe(
        df[["numero_proceso", "estado", "institucion_contratante", "proveedor", "fecha_proceso"]],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}_table",
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        ficha = fichas[selected_rows[0]]

        # Si la ficha viene de una búsqueda en vivo, todavía no tiene
        # estado/monto reales (eso solo viene del detalle completo).
        # Se pide aquí, UNA sola vez, solo para el proceso que el
        # usuario efectivamente quiere ver — no para toda la lista.
        if ficha.estado == "(clic para ver detalle)":
            with st.spinner("Consultando detalle del proceso..."):
                try:
                    record = api_client.get_record(ficha.ocid)
                    detailed = normalize_release(record)
                    if detailed:
                        ficha = detailed
                except RuntimeError as e:
                    st.warning(f"No se pudo cargar el detalle completo: {e}")

        with st.container(border=True):
            st.subheader(f"Ficha del proceso {ficha.numero_proceso}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Número de proceso (OCID):** {ficha.numero_proceso}")
                st.markdown(f"**Estado:** {ficha.estado}")
                st.markdown(f"**Institución contratante:** {ficha.institucion_contratante}")
            with c2:
                st.markdown(f"**Proveedor:** {ficha.proveedor}")
                st.markdown(f"**Fecha del proceso:** {ficha.fecha_proceso}")
                if ficha.monto:
                    st.markdown(f"**Monto:** {ficha.monto}")
            st.markdown(f"**Enlace al portal:** [{ficha.enlace}]({ficha.enlace})")
            st.caption(
                "⚠️ El enlace se genera automáticamente y no se ha verificado contra "
                "el portal en producción — confírmalo antes de citarlo en una nota."
            )


with tab_live:
    st.subheader("Búsqueda en vivo")
    year_from, year_to, keyword, institution, supplier = render_query_box("live")

    if st.button("Buscar en SERCOP", key="live_search_btn"):
        progress = st.progress(0.0, text="Consultando SERCOP...")

        def cb(year, page, total):
            progress.progress(
                min(0.95, page / 30), text=f"Año {year}, página {page} — {total} resultados hasta ahora"
            )

        try:
            raw_results = api_client.search_year_range(
                year_from, year_to, keyword=keyword, buyer=institution,
                supplier=supplier, progress_callback=cb,
            )
        except RuntimeError as e:
            st.error(str(e))
            raw_results = []

        progress.empty()

        # Vista de depuración: muestra el JSON crudo del primer resultado
        # tal como lo devuelve SERCOP. Si algún campo (institución,
        # proveedor, etc.) aparece vacío en la tabla, revisa aquí primero
        # en vez de adivinar — así vemos exactamente qué nombres de campo
        # está usando la API en este caso concreto.
        if raw_results:
            with st.expander("🔧 Depuración: ver respuesta cruda de la API (primer resultado)"):
                st.json(raw_results[0])

        # Los resultados de search_ocds ya vienen con casi todo lo
        # necesario (buyerName, single_provider, date, ocid) — NO se
        # llama a /api/record aquí. Esa llamada se hace después, una
        # sola vez, solo para el proceso que el usuario abra (ver
        # render_results_table). Antes esto llamaba a /record por
        # CADA resultado, que para una búsqueda amplia son cientos de
        # llamadas HTTP innecesarias contra un portal ya lento.
        fichas = [
            f for f in (normalize_search_result(item) for item in raw_results) if f
        ]
        st.session_state["live_fichas"] = fichas

    if "live_fichas" in st.session_state:
        render_results_table(st.session_state["live_fichas"], "live")


with tab_bulk:
    st.subheader("Datos masivos")

    modo = st.radio(
        "¿Cómo quieres traer los datos?",
        [
            "Traer año(s) completo(s) vía API (recomendado — no requiere subir nada)",
            "Subir archivos de descarga masiva que ya tengo",
        ],
        key="bulk_mode",
    )

    if modo.startswith("Traer año"):
        st.caption(
            "Esto descarga TODOS los procesos de los años que elijas usando la "
            "misma API en vivo (sin filtro de palabra clave), y los guarda en "
            "caché local para que puedas filtrar y cruzar términos sin volver a "
            "consultar el servidor cada vez. Para un año completo puede tardar "
            "varios minutos la primera vez — luego usa el caché."
        )
        c1, c2 = st.columns(2)
        with c1:
            bulk_year_from = st.number_input("Desde (año)", min_value=2008, max_value=2026, value=2023, key="bulk_year_from")
        with c2:
            bulk_year_to = st.number_input("Hasta (año)", min_value=2008, max_value=2026, value=int(bulk_year_from), key="bulk_year_to")

        if st.button("Traer datos del período", key="bulk_fetch_btn"):
            progress = st.progress(0.0, text="Descargando vía API...")

            def cb(year, page, total):
                progress.progress(min(0.95, page / 50), text=f"Año {year}, página {page} — {total} procesos hasta ahora")

            try:
                raw_results = api_client.search_year_range(
                    int(bulk_year_from), int(bulk_year_to), progress_callback=cb,
                )
                fichas = [f for f in (normalize_search_result(item) for item in raw_results) if f]
                st.session_state["bulk_fichas"] = fichas
                st.session_state["bulk_all_loaded"] = fichas
            except RuntimeError as e:
                st.error(str(e))
            progress.empty()

        if "bulk_all_loaded" in st.session_state:
            st.success(f"{len(st.session_state['bulk_all_loaded'])} procesos en caché local.")
            filtro_kw = st.text_input("Filtrar por palabra clave (institución, título, OCID)", key="bulk_kw_filter")
            base = st.session_state["bulk_all_loaded"]
            if filtro_kw:
                filtro_lower = filtro_kw.lower()
                base = [
                    f for f in base
                    if filtro_lower in f.institucion_contratante.lower()
                    or filtro_lower in f.numero_proceso.lower()
                ]
            st.session_state["bulk_fichas"] = base

        if "bulk_fichas" in st.session_state:
            render_results_table(st.session_state["bulk_fichas"], "bulk")

        st.stop()

    # --- modo: subir archivos propios ---
    st.warning(
        "⚠️ Si vas a desplegar esta app en Streamlit Community Cloud (no local), "
        "este modo puede fallar con archivos grandes: Cloud da 1GB de RAM fijo y "
        "el archivo completo se recibe en memoria al subirlo, antes de que la app "
        "pueda procesarlo por partes. Para archivos de un año completo, usa el "
        "modo de arriba en Cloud, o corre este modo de subida en local."
    )
    st.caption(
        "Descarga los archivos desde "
        "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/datos-abiertos "
        "(CSV, JSONL.gz o XLSX) y súbelos aquí. Puedes subir varios a la vez."
    )

    uploaded_files = st.file_uploader(
        "Sube uno o más archivos", accept_multiple_files=True,
        type=["csv", "gz", "xlsx", "jsonl"],
    )

    if uploaded_files:
        with st.expander("Vista previa de columnas (verifica antes de procesar)"):
            for f in uploaded_files:
                st.write(f"**{f.name}**")
                try:
                    preview = bulk_loader.get_column_preview(f, f.name)
                    st.dataframe(preview)
                except Exception as e:
                    st.error(f"No se pudo leer {f.name}: {e}")

        year_from, year_to, keyword, institution, supplier = render_query_box("bulk")

        if st.button("Procesar archivos", key="bulk_process_btn"):
            all_fichas = []
            known_names = set()

            # primera pasada: recolectar nombres reales para el fuzzy match
            for f in uploaded_files:
                known_names |= bulk_loader.collect_distinct_values(
                    f, f.name, BUYER_SUPPLIER_COLUMNS
                )

            if institution and known_names:
                matches = rank_institution_names(institution, list(known_names))
                if matches:
                    st.info(
                        "Nombres reales más cercanos a tu institución en este archivo: "
                        + ", ".join(f"{name} ({score:.0f}%)" for name, score in matches)
                    )

            progress = st.progress(0.0, text="Procesando archivos...")
            for i, f in enumerate(uploaded_files):
                for row in bulk_loader.iter_rows(f, f.name):
                    ficha = normalize_bulk_row(row)
                    if not ficha:
                        continue
                    if keyword and keyword.lower() not in str(row).lower():
                        continue
                    if institution and institution.lower() not in ficha.institucion_contratante.lower():
                        continue
                    all_fichas.append(ficha)
                progress.progress((i + 1) / len(uploaded_files))
            progress.empty()

            st.session_state["bulk_fichas"] = all_fichas

        if "bulk_fichas" in st.session_state:
            render_results_table(st.session_state["bulk_fichas"], "bulk")
