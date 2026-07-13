"""
generar_nomina.py

Genera el texto de la nómina de jugadores (listo para compartir por
WhatsApp) para el próximo partido del equipo configurado.

Uso standalone:
    uv run src/generar_nomina.py

También se puede invocar desde main.py con el flag --nomina.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import yaml

from fetch_pdf import discover_pdf_urls, download_pdf
from parse_pdf import MESES, Partido, extract_text_from_pdf_bytes, parse_pdf_text

# config.yaml vive en la raíz del repo, un nivel arriba de src/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

MESES_INV = {numero: nombre for nombre, numero in MESES.items()}
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

CUPOS_NOMINA = 12


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def pick_next_match(partidos: list[Partido], now: datetime) -> Optional[Partido]:
    """Función pura: de una lista de partidos, devuelve el de fecha/hora más
    próxima que todavía no ha ocurrido (>= now). None si no hay ninguno."""
    futuros = [
        p for p in partidos
        if datetime.strptime(f"{p.fecha} {p.hora}", "%Y-%m-%d %H:%M") >= now
    ]
    if not futuros:
        return None
    return min(futuros, key=lambda p: (p.fecha, p.hora))


def find_next_match(config: dict, now: Optional[datetime] = None) -> Optional[Partido]:
    """Descubre todos los PDFs vigentes, junta los partidos del equipo
    configurado, y devuelve el próximo (fecha/hora >= now)."""
    if now is None:
        now = datetime.now()

    partidos_por_id: dict[str, Partido] = {}
    for fecha_num, url in discover_pdf_urls(config["source_url"]):
        pdf = download_pdf(url, fecha_num)
        texto = extract_text_from_pdf_bytes(pdf.content)
        for partido in parse_pdf_text(texto, config["team_name"]):
            partidos_por_id[partido.id_partido] = partido

    return pick_next_match(list(partidos_por_id.values()), now)


def _formatear_fecha_es(fecha_iso: str) -> str:
    """'2026-07-11' -> 'sábado 11 de julio de 2026'"""
    anio, mes, dia = (int(x) for x in fecha_iso.split("-"))
    d = datetime(anio, mes, dia).date()
    dia_semana = DIAS_SEMANA[d.weekday()]
    mes_nombre = MESES_INV[mes]
    return f"{dia_semana} {d.day} de {mes_nombre} de {d.year}"


def generar_nomina(partido: Partido, cupos: int = CUPOS_NOMINA) -> str:
    titulo = f"{partido.equipo_local} vs {partido.equipo_visita}"
    fecha_str = _formatear_fecha_es(partido.fecha)

    inicio_dt = datetime.strptime(partido.hora, "%H:%M")
    citacion_dt = inicio_dt - timedelta(minutes=30)
    citacion_str = citacion_dt.strftime("%H:%M")
    inicio_str = inicio_dt.strftime("%H:%M")

    direccion = partido.gimnasio
    if partido.direccion:
        direccion = f"{direccion}, {partido.direccion}"

    lineas = [
        f"🏀 {titulo}",
        f"📅 {fecha_str}",
        f"🕔 Citación: {citacion_str} hrs",
        f"🕔 Inicio partido: {inicio_str} hrs",
        f"📍 {direccion}",
        "",
        "Nómina:",
    ]
    lineas += [f"{i}.- " for i in range(1, cupos + 1)]
    return "\n".join(lineas)


if __name__ == "__main__":
    config = load_config()
    partido = find_next_match(config)
    if partido is None:
        print("No se encontró ningún partido próximo programado.")
        sys.exit(1)
    print(generar_nomina(partido))
