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
from datetime import date
from dataclasses import dataclass, asdict
from typing import Optional


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

# Línea de partido (formato nuevo, jornada 22 en adelante), ej:
# "18:45    ISB 45-A              VS    LICEO 45-A            SERIE 45"
# Los equipos van separados por "VS" y la fila ya NO trae árbitros, ni id de
# partido, ni cancha (esos datos desaparecieron del PDF).
NEW_MATCH_LINE_RE = re.compile(
    r"^(?P<hora>\d{2}:\d{2})\s+"
    r"(?P<local>.+?\s\d{2}-[A-Z])\s+"
    r"VS\s+"
    r"(?P<visita>.+?\s\d{2}-[A-Z])\s+"
    r"(?P<serie_label>SERIE|COMP)\s*(?P<serie_num>\d+)"
    r"(?:\s.*)?$",
    re.IGNORECASE,
)

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
    id_partido: Optional[str]
    fecha: str  # YYYY-MM-DD
    hora: str   # HH:MM
    gimnasio: str
    direccion: Optional[str]
    equipo_local: str
    equipo_visita: str
    categoria: str
    cancha: Optional[str]
    jornada: Optional[str] = None

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


def _clean_direccion(direccion: Optional[str]) -> Optional[str]:
    """Quita el punto final que el PDF agrega a algunas direcciones (no todas)
    y que no aporta nada al usarlas como ubicación de un evento."""
    if direccion is None:
        return None
    return direccion.rstrip(".")


def _parse_date_line(line: str) -> Optional[date]:
    m = DATE_LINE_RE.match(line.strip())
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
                   current_jornada, *, id_partido, cancha) -> Optional[Partido]:
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
                   jornada: Optional[str] = None) -> list[Partido]:
    """
    text: contenido de texto ya extraído del PDF (ej. via pdfplumber .extract_text())
    team_name: ej. "MI EQUIPO 45-A"  (nombre + categoría, tal como aparece en el PDF)
    jornada: número de jornada del PDF. El formato nuevo no trae id de partido,
        y este dato se usa para derivar una llave estable (ver Partido.clave).
        Si es None se intenta leer del encabezado ("... JORNADA 22").
    """
    team_name_norm = team_name.strip().upper()

    partidos = []
    current_date: Optional[date] = None
    current_gym: Optional[str] = None
    current_address: Optional[str] = None
    current_jornada: Optional[str] = jornada
    awaiting_address = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Comparaciones de encabezado sobre la línea con espacios colapsados:
        # con layout=True las columnas quedan separadas por corridas largas.
        norm_upper = " ".join(line.split()).upper()

        # Número de jornada del encabezado (solo si no vino explícito).
        if jornada is None:
            jm = JORNADA_RE.search(norm_upper)
            if jm:
                current_jornada = jm.group(1)

        # ¿Línea de fecha? La del pie ("... Actualizado al: lunes, 7 de ...")
        # trae una fecha embebida que NO es la de los partidos: la excluimos.
        if "ACTUALIZADO" not in norm_upper:
            d = _parse_date_line(line)
            if d:
                current_date = d
                current_gym = None
                current_address = None
                continue

        # ¿Línea de gimnasio? El PDF trae el nombre del gimnasio y su
        # dirección en columnas separadas; al extraer con layout=True quedan
        # en la misma línea separadas por una corrida larga de espacios
        # (columna distinta), a diferencia del espacio simple entre palabras
        # de un mismo nombre. Si no hay esa corrida larga, puede que la
        # dirección venga en una línea aparte (formato legacy, ver más abajo).
        gym_m = GYM_LINE_RE.match(line)
        if gym_m:
            current_gym = gym_m.group("gimnasio").strip()
            current_address = _clean_direccion(gym_m.group("direccion"))
            awaiting_address = False
            continue

        # Ignorar encabezados conocidos
        if any(norm_upper.startswith(p.upper()) for p in IGNORE_LINE_PREFIXES):
            # Formato legacy: el gimnasio no traía la dirección en su línea y
            # esta venía suelta justo después de "HORA LOCAL VISITA...". Solo
            # armamos esa espera si todavía no tenemos dirección: en el formato
            # actual la dirección ya vino en la línea GIMNASIO y esta línea de
            # encabezado no debe pisarla con la primera fila de partido.
            if norm_upper.startswith("HORA LOCAL VISITA") and current_address is None:
                awaiting_address = True
            continue

        # ¿Línea de partido? Se prueban los dos formatos: el viejo trae id de
        # partido y cancha al final; el nuevo separa los equipos con "VS".
        match_m = MATCH_LINE_RE.match(line)
        if match_m:
            awaiting_address = False
            partido = _build_partido(
                match_m, current_date, current_gym, current_address,
                current_jornada,
                id_partido=match_m.group("id_partido"),
                cancha=match_m.group("cancha"),
            )
            if partido and team_name_norm in (
                partido.equipo_local.upper(), partido.equipo_visita.upper()
            ):
                partidos.append(partido)
            continue

        new_m = NEW_MATCH_LINE_RE.match(line)
        if new_m:
            awaiting_address = False
            partido = _build_partido(
                new_m, current_date, current_gym, current_address,
                current_jornada,
                id_partido=None,
                cancha=None,
            )
            if partido and team_name_norm in (
                partido.equipo_local.upper(), partido.equipo_visita.upper()
            ):
                partidos.append(partido)
            continue

        # Si llegamos aquí y estábamos esperando la dirección, esta línea lo es
        if awaiting_address:
            current_address = _clean_direccion(line)
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
    import sys
    import json

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
