"""
parse_pdf.py

Descarga (o recibe) el texto extraído de un PDF de programación de ABSS
y devuelve la lista de partidos de un equipo configurado.

Uso típico:
    partidos = parse_pdf_text(texto_extraido, team_name="MI EQUIPO 45-A")

Para producción, `extract_text_from_pdf(path)` usa pdfplumber sobre el
archivo descargado.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# "sábado, 11 de julio de 2026" -> date(2026, 7, 11)
# El formato nuevo (jornada 22 en adelante) trae el día en mayúsculas y con
# texto extra al final ("SÁBADO,  12 DE SEPTIEMBRE DE 2026    14 PARTIDOS"),
# así que toleramos cualquier cosa después del año.
DATE_LINE_RE = re.compile(
    r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo),\s*"
    r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})"
    r"(?:\s.*)?$",
    re.IGNORECASE,
)

GYM_LINE_RE = re.compile(r"^GIMNASIO\s+(?P<gimnasio>.+?)(?:\s{3,}(?P<direccion>\S.*))?$")

# Número de jornada en el encabezado del formato nuevo:
# "PROGRAMACIÓN                      JORNADA            22"
JORNADA_RE = re.compile(r"\bJORNADA\s+(\d+)\b")

# Línea de partido (formato viejo, hasta jornada 21), ej:
# "13:00 MI EQUIPO 45-A OTRO EQUIPO 45-A SERIE 45 ARBITRO UNO ARBITRO DOS (PL) 336 14"
# Trae árbitros, id de partido y cancha al final de la fila.
MATCH_LINE_RE = re.compile(
    r"^(?P<hora>\d{2}:\d{2})\s+"
    r"(?P<local>.+?\s\d{2}-[A-Z])\s+"
    r"(?P<visita>.+?\s\d{2}-[A-Z])\s+"
    r"(?P<serie_label>SERIE|COMP)\s*(?P<serie_num>\d+)"
    r"(?:\s*G\d+)?\s+"
    r".+?\s+"  # árbitros: contenido variable, no nos interesa el detalle
    r"(?P<id_partido>\d+)\s+"
    r"(?P<cancha>\d+)$"
)

# Línea de partido (formato nuevo, jornada 22 en adelante). El PDF real pasó a
# una grilla de DOS columnas por página (dos gimnasios/partidos por fila
# física), así que dos partidos suelen terminar concatenados en una misma
# línea de texto extraído, ej:
#   "15:15 MADECO 50-A J.RAMSAY 50-A Serie 50 G2 (8vo_16avo) 15:15 LICEO 60-A BRISAS 60-A Serie 60 G2 (6to_10mo)"
# Ya no trae "VS" entre equipos (se tolera igual, por si aparece), ni
# árbitros/id/cancha en la fila. Sin anclas de inicio/fin: se usa con
# finditer() para encontrar todas las ocurrencias de la fila (una por
# columna) en lugar de un solo match por línea.
NEW_MATCH_LINE_RE = re.compile(
    r"(?P<hora>\d{2}:\d{2})\s+"
    r"(?P<local>.+?\s\d{2}-[A-Z])\s+"
    r"(?:VS\s+)?"
    r"(?P<visita>.+?\s\d{2}-[A-Z])\s+"
    r"(?P<serie_label>SERIE|COMP)\s*(?P<serie_num>\d+)",
    re.IGNORECASE,
)

# Línea de gimnasio del formato nuevo, ej (dos columnas concatenadas):
#   "▣ GIMNASIO ESC.LO FRANCO Árbitros:      ▣ GIMNASIO ESC.REPUBLICA DEL Árbitros:"
# El nombre del gimnasio va seguido de la etiqueta "Árbitros:"; la dirección
# ya NO viene en esta línea (ver NEW_ADDRESS_LINE_RE). finditer() saca los
# gimnasios de ambas columnas, en orden.
NEW_GYM_LINE_RE = re.compile(
    r"▣\s*GIMNASIO\s+(?P<gimnasio>.+?)\s+Árbitros:",
    re.IGNORECASE,
)

# Línea de dirección del formato nuevo, ej (dos columnas concatenadas):
#   "● CIUDAD DE MEXICO 1589, LA PINTANA. SÁNCHEZ ● SAN NICOLAS 681, SAN MIGUEL. SÁNCHEZ"
# Cada dirección viene precedida de "●"; a veces trae texto residual pegado
# al final (apellido de árbitro que se desbordó desde la columna vecina) que
# no logramos separar de forma confiable, así que puede quedar en el texto.
# Un gimnasio ya mencionado antes en el PDF no repite su dirección (se
# reutiliza la última conocida, ver `known_addresses_new` en parse_pdf_text).
NEW_ADDRESS_LINE_RE = re.compile(r"●\s*(?P<direccion>.+?)(?=\s*●|$)")

# Líneas de encabezado / ruido a ignorar dentro de un bloque de gimnasio.
# La comparación se hace sobre la línea con espacios colapsados a uno solo.
IGNORE_LINE_PREFIXES = (
    "HORA LOCAL VISITA",
    "GRUPO",
    "PROGRAMACIÓN",
    "PROGRAMACION",
    "SUJETA A MODIFICACIÓN",
    "SUJETA A MODIFICACION",
    "Asociación de Basquétbol",
    "Asociacion de Basquetbol",
    "Asociación de Básquetbol",
    "Agrupación de árbitros",
    "Agrupacion de arbitros",
    "Total de partidos",
    "TOTAL:",
    "TOTAL ",
    "www.abss.cl",
)


@dataclass
class Partido:
    # id_partido y cancha vienen None en el formato nuevo del PDF (jornada 22
    # en adelante), que dejó de publicarlos.
    id_partido: str | None
    fecha: str  # YYYY-MM-DD
    hora: str   # HH:MM
    gimnasio: str
    direccion: str | None
    equipo_local: str
    equipo_visita: str
    categoria: str
    cancha: str | None
    jornada: str | None = None

    @property
    def clave(self) -> str:
        """Llave estable para seguir el partido entre corridas.

        El formato viejo del PDF traía un 'id_partido' único y estable; el
        formato nuevo (jornada 22 en adelante) ya no lo trae, así que
        derivamos una llave sintética a partir de jornada + categoría +
        equipos. Es única (un enfrentamiento por categoría por jornada) y se
        mantiene estable aunque cambien fecha/hora/gimnasio: una
        reprogramación es una *actualización* del mismo partido, no uno nuevo.
        """
        if self.id_partido:
            return str(self.id_partido)
        jornada = self.jornada or "SJ"
        return f"J{jornada}|{self.categoria}|{self.equipo_local}|{self.equipo_visita}"

    def to_dict(self):
        d = asdict(self)
        d["clave"] = self.clave
        return d


def _clean_direccion(direccion: str | None) -> str | None:
    """Quita el punto final que el PDF agrega a algunas direcciones (no todas)
    y que no aporta nada al usarlas como ubicación de un evento."""
    if direccion is None:
        return None
    return direccion.rstrip(".")


def _undouble_token(token: str, stride: int) -> str:
    """Revierte el "negrita falsa" del PDF nuevo: cada carácter del título y
    de los encabezados de fecha viene dibujado `stride` veces superpuesto,
    así que pdfplumber lo extrae literalmente repetido (ej. "SSÁÁBBAADDOO,,"
    en vez de "SÁBADO,"). Solo colapsamos si el token se puede dividir en
    grupos de `stride` caracteres IDÉNTICOS entre sí: así "1133" (día 13
    duplicado) da "13", pero un "11" o "22" genuino (no duplicado) no se
    toca porque no hay contexto que indique que ESE token está duplicado."""
    n = len(token)
    if stride < 2 or n == 0 or n % stride != 0:
        return token
    grupos = [token[i:i + stride] for i in range(0, n, stride)]
    if all(len(set(g)) == 1 for g in grupos):
        return token[0::stride]
    return token


def _undouble_line(line: str, stride: int) -> str:
    return " ".join(_undouble_token(tok, stride) for tok in line.split())


def _parse_date_line(line: str) -> date | None:
    stripped = line.strip()
    m = DATE_LINE_RE.match(stripped)
    if not m:
        # Formato nuevo: el encabezado de fecha viene con cada carácter
        # duplicado (ver _undouble_token).
        m = DATE_LINE_RE.match(_undouble_line(stripped, 2))
    if not m:
        return None
    dia, mes_nombre, anio = m.groups()
    mes = MESES.get(mes_nombre.lower())
    if not mes:
        return None
    return date(int(anio), mes, int(dia))


def _split_team_category(team_with_cat: str):
    """
    'MI EQUIPO 45-A' -> ('MI EQUIPO', '45-A')
    'U.CLUB EJEMPLO 45-A' -> ('U.CLUB EJEMPLO', '45-A')
    """
    m = re.match(r"^(?P<nombre>.+)\s(?P<cat>\d{2}-[A-Z])$", team_with_cat.strip())
    if not m:
        return team_with_cat.strip(), ""
    return m.group("nombre").strip(), m.group("cat").strip()


def _build_partido(m, current_date, current_gym, current_address,
                   current_jornada, *, id_partido, cancha) -> Partido | None:
    """Construye un Partido a partir de un match de MATCH_LINE_RE o
    NEW_MATCH_LINE_RE (comparten los grupos hora/local/visita/serie_*)."""
    if not current_date:
        # No debería pasar si el PDF viene bien formado
        return None

    local_nombre, local_cat = _split_team_category(m.group("local"))
    visita_nombre, visita_cat = _split_team_category(m.group("visita"))

    return Partido(
        id_partido=id_partido,
        fecha=current_date.isoformat(),
        hora=m.group("hora"),
        gimnasio=current_gym or "",
        direccion=current_address,
        equipo_local=f"{local_nombre} {local_cat}".strip(),
        equipo_visita=f"{visita_nombre} {visita_cat}".strip(),
        categoria=f"{m.group('serie_label').upper()} {m.group('serie_num')}",
        cancha=cancha,
        jornada=current_jornada,
    )


def parse_pdf_text(text: str, team_name: str,
                   jornada: str | None = None) -> list[Partido]:
    """
    text: contenido de texto ya extraído del PDF (ej. via pdfplumber .extract_text())
    team_name: ej. "MI EQUIPO 45-A"  (nombre + categoría, tal como aparece en el PDF)
    jornada: número de jornada del PDF. El formato nuevo no trae id de partido,
        y este dato se usa para derivar una llave estable (ver Partido.clave).
        Si es None se intenta leer del encabezado ("... JORNADA 22").
    """
    team_name_norm = team_name.strip().upper()

    partidos = []
    current_date: date | None = None
    current_jornada: str | None = jornada
    awaiting_address = False

    # Gimnasio "actual" de cada columna, por posición (índice 0, 1, ...). El
    # formato viejo (hasta jornada 21) es de una sola columna, así que esta
    # lista nunca pasa de largo 1; el formato nuevo (jornada 22 en adelante)
    # viene en grilla de dos columnas por página y dos partidos/gimnasios
    # suelen terminar concatenados en una misma línea de texto extraído (ver
    # NEW_MATCH_LINE_RE), así que el primero encontrado en la línea es de la
    # columna 0, el segundo de la columna 1, etc.
    current_gyms: list[str] = []
    # Dirección conocida por NOMBRE de gimnasio (no por columna): un mismo
    # gimnasio reaparece en varias filas/columnas y el PDF solo imprime su
    # dirección la primera vez, así que hay que recordarla.
    known_addresses: dict[str, str] = {}

    def gimnasio_y_direccion(columna: int):
        if not current_gyms:
            return None, None
        gym = current_gyms[columna] if columna < len(current_gyms) else current_gyms[-1]
        return gym, known_addresses.get(gym)

    def agregar_partidos(matches, id_partido_de, cancha_de):
        for i, m in enumerate(matches):
            gym, direccion = gimnasio_y_direccion(i)
            partido = _build_partido(
                m, current_date, gym, direccion, current_jornada,
                id_partido=id_partido_de(m), cancha=cancha_de(m),
            )
            if partido and team_name_norm in (
                partido.equipo_local.upper(), partido.equipo_visita.upper()
            ):
                partidos.append(partido)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Comparaciones de encabezado sobre la línea con espacios colapsados:
        # con layout=True las columnas quedan separadas por corridas largas.
        norm_upper = " ".join(line.split()).upper()

        # Número de jornada del encabezado (solo si no vino explícito). En el
        # formato nuevo el título viene con cada carácter triplicado (falsa
        # negrita), ver _undouble_token.
        if jornada is None and current_jornada is None:
            jm = JORNADA_RE.search(norm_upper) or JORNADA_RE.search(_undouble_line(norm_upper, 3))
            if jm:
                current_jornada = jm.group(1)

        # ¿Línea de fecha? La del pie ("... Actualizado al: lunes, 7 de ...")
        # trae una fecha embebida que NO es la de los partidos: la excluimos.
        if "ACTUALIZADO" not in norm_upper:
            d = _parse_date_line(line)
            if d:
                current_date = d
                current_gyms = []
                awaiting_address = False
                continue

        # ¿Línea de gimnasio, formato viejo? Trae nombre y dirección en la
        # misma línea, separados por una corrida larga de espacios (columna
        # distinta al extraer con layout=True). Si no hay esa corrida larga,
        # puede que la dirección venga en una línea aparte (formato legacy,
        # ver más abajo).
        gym_m = GYM_LINE_RE.match(line)
        if gym_m:
            gimnasio = gym_m.group("gimnasio").strip()
            current_gyms = [gimnasio]
            direccion = _clean_direccion(gym_m.group("direccion"))
            if direccion:
                known_addresses[gimnasio] = direccion
            awaiting_address = False
            continue

        # ¿Línea de gimnasio(s), formato nuevo? "▣ GIMNASIO X Árbitros: ▣
        # GIMNASIO Y Árbitros:" (una o dos ocurrencias, según cuántas
        # columnas traiga esa fila). La dirección no viene aquí.
        new_gym_matches = list(NEW_GYM_LINE_RE.finditer(line))
        if new_gym_matches:
            current_gyms = [gm.group("gimnasio").strip() for gm in new_gym_matches]
            continue

        # ¿Línea de dirección, formato nuevo? "● dirección ● dirección". Se
        # asocia por posición con el gimnasio de esa misma columna: si esa
        # columna no trae dirección en esta fila (gimnasio ya mencionado
        # antes), se conserva la última conocida.
        new_address_matches = list(NEW_ADDRESS_LINE_RE.finditer(line))
        if new_address_matches:
            for i, am in enumerate(new_address_matches):
                if i < len(current_gyms):
                    known_addresses[current_gyms[i]] = _clean_direccion(
                        am.group("direccion").strip()
                    )
            continue

        # Ignorar encabezados conocidos
        if any(norm_upper.startswith(p.upper()) for p in IGNORE_LINE_PREFIXES):
            # Formato legacy: el gimnasio no traía la dirección en su línea y
            # esta venía suelta justo después de "HORA LOCAL VISITA...". Solo
            # armamos esa espera si todavía no tenemos dirección: en el formato
            # actual la dirección ya vino en la línea GIMNASIO y esta línea de
            # encabezado no debe pisarla con la primera fila de partido.
            if norm_upper.startswith("HORA LOCAL VISITA") and not (
                current_gyms and known_addresses.get(current_gyms[0])
            ):
                awaiting_address = True
            continue

        # ¿Línea de partido, formato viejo? Trae id de partido y cancha al
        # final de la fila; se prueba primero porque su ancla de cierre
        # (`\d+\s+\d+$`) es más estricta y así no se confunde con el nuevo.
        match_m = MATCH_LINE_RE.match(line)
        if match_m:
            awaiting_address = False
            agregar_partidos(
                [match_m],
                id_partido_de=lambda m: m.group("id_partido"),
                cancha_de=lambda m: m.group("cancha"),
            )
            continue

        # ¿Línea de partido(s), formato nuevo? Puede traer más de un partido
        # concatenado (uno por columna); finditer() los saca todos en orden y
        # cada uno se asocia con el gimnasio de su misma columna.
        new_matches = list(NEW_MATCH_LINE_RE.finditer(line))
        if new_matches:
            awaiting_address = False
            agregar_partidos(new_matches, id_partido_de=lambda m: None, cancha_de=lambda m: None)
            continue

        # Si llegamos aquí y estábamos esperando la dirección, esta línea lo es
        if awaiting_address and current_gyms:
            known_addresses[current_gyms[0]] = _clean_direccion(line)
            awaiting_address = False
            continue

    return partidos


def extract_text_from_pdf(path: str) -> str:
    """Extrae texto de un PDF local usando pdfplumber (uso en producción).

    Usa layout=True para preservar la posición horizontal del texto: la
    línea "GIMNASIO ..." trae el nombre del gimnasio y su dirección en
    columnas separadas por un espacio grande, y GYM_LINE_RE necesita ese
    espacio para distinguir dónde termina el nombre y empieza la dirección.
    """
    import pdfplumber

    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text(layout=True) or "")
    return "\n".join(text_parts)


def extract_text_from_pdf_bytes(content: bytes) -> str:
    """Igual que extract_text_from_pdf, pero desde bytes ya en memoria (sin
    necesidad de escribir un archivo temporal por PDF)."""
    import io

    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text(layout=True) or "")
    return "\n".join(text_parts)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        print("Uso: python parse_pdf.py <archivo.txt|archivo.pdf> <NOMBRE_EQUIPO>")
        sys.exit(1)

    path = sys.argv[1]
    team = sys.argv[2]

    if path.lower().endswith(".pdf"):
        contenido = extract_text_from_pdf(path)
    else:
        with open(path, encoding="utf-8") as f:
            contenido = f.read()

    resultado = parse_pdf_text(contenido, team)
    print(json.dumps([p.to_dict() for p in resultado], indent=2, ensure_ascii=False))
