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
DATE_LINE_RE = re.compile(
    r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo),\s*"
    r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})$",
    re.IGNORECASE,
)

GYM_LINE_RE = re.compile(r"^GIMNASIO\s+(?P<gimnasio>.+?)(?:\s{3,}(?P<direccion>\S.*))?$")

# Línea de partido, ej:
# "13:00 MI EQUIPO 45-A OTRO EQUIPO 45-A SERIE 45 ARBITRO UNO ARBITRO DOS (PL) 336 14"
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

# Líneas de encabezado / ruido a ignorar dentro de un bloque de gimnasio
IGNORE_LINE_PREFIXES = (
    "HORA LOCAL VISITA",
    "GRUPO",
    "PROGRAMACIÓN",
    "PROGRAMACION",
    "SUJETA A MODIFICACIÓN",
    "SUJETA A MODIFICACION",
    "Asociación de Basquétbol",
    "Asociacion de Basquetbol",
    "Total de partidos",
)


@dataclass
class Partido:
    id_partido: str
    fecha: str  # YYYY-MM-DD
    hora: str   # HH:MM
    gimnasio: str
    direccion: Optional[str]
    equipo_local: str
    equipo_visita: str
    categoria: str
    cancha: str

    def to_dict(self):
        return asdict(self)


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


def parse_pdf_text(text: str, team_name: str) -> list[Partido]:
    """
    text: contenido de texto ya extraído del PDF (ej. via pdfplumber .extract_text())
    team_name: ej. "MI EQUIPO 45-A"  (nombre + categoría, tal como aparece en el PDF)
    """
    team_name_norm = team_name.strip().upper()

    partidos = []
    current_date: Optional[date] = None
    current_gym: Optional[str] = None
    current_address: Optional[str] = None
    awaiting_address = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # ¿Línea de fecha?
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
        if any(line.upper().startswith(p.upper()) for p in IGNORE_LINE_PREFIXES):
            # Justo después de "HORA LOCAL VISITA..." viene la dirección,
            # y después "GRUPO". Marcamos que la próxima línea "libre" es dirección.
            if line.upper().startswith("HORA LOCAL VISITA"):
                awaiting_address = True
            continue

        # ¿Línea de partido?
        match_m = MATCH_LINE_RE.match(line)
        if match_m:
            awaiting_address = False
            local_full = match_m.group("local")
            visita_full = match_m.group("visita")
            local_nombre, local_cat = _split_team_category(local_full)
            visita_nombre, visita_cat = _split_team_category(visita_full)

            local_completo = f"{local_nombre} {local_cat}".strip()
            visita_completo = f"{visita_nombre} {visita_cat}".strip()

            if team_name_norm not in (local_completo.upper(), visita_completo.upper()):
                continue

            if not current_date:
                # No debería pasar si el PDF viene bien formado
                continue

            partidos.append(
                Partido(
                    id_partido=match_m.group("id_partido"),
                    fecha=current_date.isoformat(),
                    hora=match_m.group("hora"),
                    gimnasio=current_gym or "",
                    direccion=current_address,
                    equipo_local=local_completo,
                    equipo_visita=visita_completo,
                    categoria=f"{match_m.group('serie_label')} {match_m.group('serie_num')}",
                    cancha=match_m.group("cancha"),
                )
            )
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
