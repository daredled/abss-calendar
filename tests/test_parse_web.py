"""
Tests del respaldo web (parse_web.py) con el HTML real de la sección
"PRÓXIMOS ENCUENTROS" de https://abss.cl/campeonato/ del 14-oct-2026, cuando
la ABSS publicó la jornada 25 como PDF escaneado (solo imagen). Son los
mismos 28 partidos de ese PDF.
"""

import os
from datetime import date

from parse_web import _inferir_fecha, parse_proximos_html

_HTML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "proximos_encuentros_j25.html"
)
with open(_HTML_PATH, encoding="utf-8") as f:
    PROXIMOS_J25_HTML = f.read()

HOY = date(2026, 10, 14)


def test_partido_del_equipo_se_lee_completo():
    partidos = parse_proximos_html(
        PROXIMOS_J25_HTML, "LICEO 45-A", jornada="25", hoy=HOY,
        direcciones_conocidas={"PALMARES CENTRAL": "SANTA LUISA 300, QUILICURA"},
    )
    assert len(partidos) == 1
    p = partidos[0]
    assert p.fecha == "2026-10-17"
    assert p.hora == "17:55"
    assert p.gimnasio == "PALMARES CENTRAL"  # sin el prefijo "GIMNASIO", como en el PDF
    assert p.direccion == "SANTA LUISA 300, QUILICURA"
    assert p.equipo_local == "BRISAS 45-A"
    assert p.equipo_visita == "LICEO 45-A"
    assert p.categoria == "SERIE 45"
    assert p.id_partido is None
    assert p.cancha is None
    # Misma llave que sale del PDF con texto de esa jornada.
    assert p.clave == "J25|SERIE 45|BRISAS 45-A|LICEO 45-A"


def test_gimnasio_sin_direccion_conocida_queda_none():
    partidos = parse_proximos_html(PROXIMOS_J25_HTML, "LICEO 45-A", jornada="25", hoy=HOY)
    assert partidos[0].direccion is None


def test_equipo_que_no_juega_no_devuelve_nada():
    assert parse_proximos_html(PROXIMOS_J25_HTML, "NO EXISTE 45-A", jornada="25", hoy=HOY) == []


def test_lee_las_28_tarjetas():
    # Se busca el local de cada tarjeta y se cuentan llaves distintas.
    locales = [
        "V.ESCUELA 35-A", "J.RAMSAY 50-A", "MADECO 60-A", "ALVAMINET 45-A",
        "MADECO 50-A", "BOSTON 35-A", "PALMARES 40-A", "LICEO 60-B",
        "BRISAS 45-A", "ISB 40-A", "P.ALTO 50-A", "S.CEPPI 50-A",
        "AMIGORENA 60-B", "S.CENTRAL 45-A", "BRISAS 40-A", "AMIGORENA 35-A",
        "PANTERA 35-A", "S.CEPPI 60-A", "S.CENTRAL 40-A", "BRISAS 70-A",
        "S.CENTRAL 50-A", "AUDAX 50-A", "S.CEPPI 45-A", "BUFALO 45-A",
        "BRISAS 70-B", "IMANTO 35-A", "PANTERA 40-A", "DOMANI 35-A",
    ]
    claves = {
        p.clave
        for local in locales
        for p in parse_proximos_html(PROXIMOS_J25_HTML, local, jornada="25", hoy=HOY)
    }
    assert len(claves) == 28


def test_partido_entre_series_usa_categoria_del_local_como_el_pdf():
    # La página lo muestra como "SERIE 40", pero en el PDF es "G3 40 + 45"
    # (sin "Serie N") y el parser del PDF toma la categoría del local.
    partidos = parse_proximos_html(PROXIMOS_J25_HTML, "S.CEPPI 40-A", jornada="25", hoy=HOY)
    assert len(partidos) == 1
    assert partidos[0].equipo_local == "S.CEPPI 45-A"
    assert partidos[0].categoria == "SERIE 45"

    partidos = parse_proximos_html(PROXIMOS_J25_HTML, "U.LA GRANJA 45-A", jornada="25", hoy=HOY)
    assert partidos[0].equipo_local == "PANTERA 40-A"
    assert partidos[0].categoria == "SERIE 40"


def test_tarjeta_incompleta_se_omite():
    html = PROXIMOS_J25_HTML.replace("17:55", "a confirmar", 2)
    partidos = parse_proximos_html(html, "LICEO 45-A", jornada="25", hoy=HOY)
    assert partidos == []


def test_inferir_fecha_usa_el_anio_mas_cercano():
    assert _inferir_fecha(17, 10, date(2026, 10, 14)) == date(2026, 10, 17)
    assert _inferir_fecha(10, 1, date(2026, 12, 20)) == date(2027, 1, 10)
    assert _inferir_fecha(20, 12, date(2027, 1, 5)) == date(2026, 12, 20)
