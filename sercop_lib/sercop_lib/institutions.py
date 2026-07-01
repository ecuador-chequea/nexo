"""
Lista semilla de instituciones públicas ecuatorianas, usada por el parser
de consultas en lenguaje libre para reconocer cuándo una parte del texto
se refiere a una entidad contratante (no a una palabra clave).

Esta lista NO pretende ser exhaustiva. Es un punto de partida para el
matching difuso (fuzzy). Cuando el usuario cargue archivos de descarga
masiva o haga búsquedas en vivo, la app puede ampliar este índice con
los nombres reales de "buyer"/"supplier" que va encontrando, que es la
fuente de verdad más confiable porque son los nombres tal como aparecen
en los datos de SERCOP.
"""

# Alias corto -> fragmento(s) que probablemente aparezcan en el nombre
# oficial del comprador en los datos de SERCOP. El matching es difuso,
# así que no hace falta el nombre exacto, pero mientras más cercano,
# mejor la precisión.
INSTITUTION_SEEDS = {
    "presidencia": ["PRESIDENCIA DE LA REPUBLICA", "PRESIDENCIA DE LA REPÚBLICA"],
    "vicepresidencia": ["VICEPRESIDENCIA DE LA REPUBLICA"],
    "secretaria de comunicacion": ["SECRETARIA GENERAL DE COMUNICACION", "SECOM"],
    "senae": ["SERVICIO NACIONAL DE ADUANA"],
    "sercop": ["SERVICIO NACIONAL DE CONTRATACION PUBLICA"],
    "sri": ["SERVICIO DE RENTAS INTERNAS"],
    "ministerio de salud": ["MINISTERIO DE SALUD PUBLICA"],
    "ministerio de educacion": ["MINISTERIO DE EDUCACION"],
    "ministerio de defensa": ["MINISTERIO DE DEFENSA NACIONAL"],
    "ministerio de gobierno": ["MINISTERIO DE GOBIERNO"],
    "ministerio del interior": ["MINISTERIO DEL INTERIOR"],
    "ministerio de finanzas": ["MINISTERIO DE ECONOMIA Y FINANZAS"],
    "ministerio de obras publicas": ["MINISTERIO DE TRANSPORTE Y OBRAS PUBLICAS"],
    "ministerio de agricultura": ["MINISTERIO DE AGRICULTURA"],
    "ministerio de energia": ["MINISTERIO DE ENERGIA"],
    "ministerio de turismo": ["MINISTERIO DE TURISMO"],
    "ministerio de trabajo": ["MINISTERIO DEL TRABAJO"],
    "cancilleria": ["MINISTERIO DE RELACIONES EXTERIORES"],
    "policia nacional": ["POLICIA NACIONAL DEL ECUADOR"],
    "fuerzas armadas": ["FUERZAS ARMADAS", "COMANDO CONJUNTO"],
    "fiscalia": ["FISCALIA GENERAL DEL ESTADO"],
    "consejo de la judicatura": ["CONSEJO DE LA JUDICATURA"],
    "cne": ["CONSEJO NACIONAL ELECTORAL"],
    "iess": ["INSTITUTO ECUATORIANO DE SEGURIDAD SOCIAL"],
    "municipio de quito": ["DISTRITO METROPOLITANO DE QUITO", "MUNICIPIO DEL DISTRITO METROPOLITANO DE QUITO"],
    "municipio de guayaquil": ["MUNICIPALIDAD DE GUAYAQUIL", "M.I. MUNICIPALIDAD DE GUAYAQUIL"],
    "municipio de cuenca": ["MUNICIPALIDAD DE CUENCA", "GAD MUNICIPAL DE CUENCA"],
    "prefectura": ["GOBIERNO PROVINCIAL", "PREFECTURA"],
    "gad": ["GOBIERNO AUTONOMO DESCENTRALIZADO", "GAD MUNICIPAL", "GAD PARROQUIAL"],
    "petroecuador": ["EMPRESA PUBLICA DE HIDROCARBUROS", "PETROECUADOR"],
    "cnt": ["CORPORACION NACIONAL DE TELECOMUNICACIONES"],
    "senescyt": ["SECRETARIA DE EDUCACION SUPERIOR"],
}
