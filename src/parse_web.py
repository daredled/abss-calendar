"""
parse_web.py

Respaldo para cuando el PDF de programación viene escaneado (solo imagen,
sin capa de texto): lee los partidos de la sección "PRÓXIMOS ENCUENTROS" de
la página de la liga (https://abss.cl/campeonato/), que los publica como
texto en tarjetas, una por partido:

    <div class="bg-white p-4 shadow rounded-md">
        <span ...>SERIE 45</span>
        ...
        <a class="bg-gray-200 rounded py-1">BRISAS <br> 45-A</a>
        <a class="bg-gray-200 rounded py-1">LICEO <br> 45-A</a>
        ...
        <div class="text-center">
            <a ...>17 de Octubre</a> <br>
            <a ...>GIMNASIO PALMARES CENTRAL</a> <br>
            <a ...>17:55</a>
        </div>
    </div>

A diferencia del PDF, la página NO trae número de jornada, año, dirección
del gimnasio ni el grupo exacto de los partidos entre series ("G3 40 + 45"
sale como "SERIE 40"): quien llama entrega la jornada y las direcciones
conocidas, el año se deduce de la fecha actual y la categoría se calcula
igual que en el PDF (ver _categoria_web), para que la llave del partido
(Partido.clave) coincida con la que saldría del PDF con texto.

Además muestra solo los partidos *próximos*: que un partido no aparezca no
significa que se haya cancelado (puede que ya se haya jugado), así que esta
fuente nunca debe usarse para borrar eventos.
"""

import html
import re
from datetime import date

from parse_pdf import MESES, Partido, _split_team_category

CARD_SPLIT = '<div class="bg-white p-4 shadow rounded-md">'
SERIE_RE = re.compile(r"<span[^>]*>(.*?)</span>", re.DOTALL)
EQUIPO_RE = re.compile(r'<a class="bg-gray-200 rounded py-1">(.*?)</a>', re.DOTALL)
INFO_RE = re.compile(r'<div class="text-center">(.*?)</div>', re.DOTALL)
INFO_ITEM_RE = re.compile(r"<a[^>]*>(.*?)</a>", re.DOTALL)

# "17 de Octubre"
DIA_MES_RE = re.compile(r"^(\d{1,2})\s+de\s+([a-záéíóúñ]+)$", re.IGNORECASE)
HORA_RE = re.compile(r"^\d{2}:\d{2}$")


def _texto(fragmento: str) -> str:
    """Texto plano de un fragmento HTML, con espacios colapsados."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def _inferir_fecha(dia: int, mes: int, hoy: date) -> date:
    """La tarjeta dice "17 de Octubre" sin año: se usa el año (actual, anterior
    o siguiente) que deja la fecha más cerca de hoy, para que un partido de
    enero visto en diciembre caiga en el año siguiente."""
    candidatas = []
    for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
        try:
            candidatas.append(date(anio, mes, dia))
        except ValueError:  # 29 de febrero en año no bisiesto
            continue
    return min(candidatas, key=lambda d: abs((d - hoy).days))


def _categoria_web(serie: str, local: str, visita: str) -> str:
    """Categoría igual a la que saldría del PDF (ver parse_pdf._categoria).
    En un partido entre series distintas el PDF no trae "Serie N" (solo
    "G3 40 + 45") y la categoría sale de la del equipo local, mientras que la
    página muestra una serie que no siempre es esa ("S.CEPPI 45-A vs S.CEPPI
    40-A" aparece como "SERIE 40")."""
    num_local = _split_team_category(local)[1][:2]
    num_visita = _split_team_category(visita)[1][:2]
    if num_local and num_visita and num_local != num_visita:
        return f"SERIE {num_local}"
    return serie.upper()


def parse_proximos_html(text: str, team_name: str, jornada: str, hoy: date,
                        direcciones_conocidas: dict | None = None) -> list[Partido]:
    """
    text: HTML de https://abss.cl/campeonato/ (basta con la sección de
        próximos encuentros).
    team_name: ej. "MI EQUIPO 45-A".
    jornada: número de jornada a la que corresponden los partidos (la página
        no lo trae; ver Partido.clave).
    hoy: fecha de referencia para deducir el año.
    direcciones_conocidas: gimnasio -> dirección, de partidos anteriores (la
        página no trae direcciones).

    Las tarjetas que no se entienden se omiten.
    """
    team_name_norm = team_name.strip().upper()
    direcciones_conocidas = direcciones_conocidas or {}

    partidos = []
    for card in text.split(CARD_SPLIT)[1:]:
        serie_m = SERIE_RE.search(card)
        equipos = [_texto(e) for e in EQUIPO_RE.findall(card)]
        info_m = INFO_RE.search(card)
        if not serie_m or len(equipos) != 2 or not info_m:
            continue
        info = [_texto(i) for i in INFO_ITEM_RE.findall(info_m.group(1))]
        if len(info) != 3:
            continue
        dia_mes, gimnasio, hora = info

        fecha_m = DIA_MES_RE.match(dia_mes)
        mes = MESES.get(fecha_m.group(2).lower()) if fecha_m else None
        if not mes or not HORA_RE.match(hora):
            continue

        local, visita = equipos
        if team_name_norm not in (local.upper(), visita.upper()):
            continue

        # "GIMNASIO PALMARES CENTRAL" -> "PALMARES CENTRAL", como en el PDF
        gimnasio = re.sub(r"^GIMNASIO\s+", "", gimnasio, flags=re.IGNORECASE)
        partidos.append(Partido(
            id_partido=None,
            fecha=_inferir_fecha(int(fecha_m.group(1)), mes, hoy).isoformat(),
            hora=hora,
            gimnasio=gimnasio,
            direccion=direcciones_conocidas.get(gimnasio),
            equipo_local=local,
            equipo_visita=visita,
            categoria=_categoria_web(_texto(serie_m.group(1)), local, visita),
            cancha=None,
            jornada=jornada,
        ))
    return partidos
