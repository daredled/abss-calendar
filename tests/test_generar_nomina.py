from datetime import datetime
from unittest.mock import patch

from parse_pdf import Partido
from generar_nomina import (
    pick_next_match,
    find_next_match,
    generar_nomina,
    _formatear_fecha_es,
)
from tests.fixtures import FECHA14_TEXTO


def _partido(id_partido="1", fecha="2026-07-12", hora="13:00", direccion="DIR X"):
    return Partido(
        id_partido=id_partido,
        fecha=fecha,
        hora=hora,
        gimnasio="RECINTO DOS",
        direccion=direccion,
        equipo_local="MI EQUIPO 45-A",
        equipo_visita="OTRO EQUIPO 45-A",
        categoria="SERIE 45",
        cancha="14",
    )


def test_pick_next_match_elige_el_mas_proximo_entre_varios_futuros():
    ahora = datetime(2026, 7, 1)
    lejano = _partido(id_partido="1", fecha="2026-07-20", hora="10:00")
    cercano = _partido(id_partido="2", fecha="2026-07-05", hora="10:00")

    resultado = pick_next_match([lejano, cercano], ahora)

    assert resultado.id_partido == "2"


def test_pick_next_match_ignora_partidos_pasados():
    ahora = datetime(2026, 7, 12, 13, 0)
    pasado = _partido(id_partido="1", fecha="2026-07-12", hora="12:00")
    futuro = _partido(id_partido="2", fecha="2026-07-12", hora="14:00")

    resultado = pick_next_match([pasado, futuro], ahora)

    assert resultado.id_partido == "2"


def test_pick_next_match_devuelve_none_si_todos_son_pasados():
    ahora = datetime(2026, 8, 1)
    pasado = _partido(fecha="2026-07-12", hora="12:00")

    assert pick_next_match([pasado], ahora) is None


def test_pick_next_match_devuelve_none_si_no_hay_partidos():
    assert pick_next_match([], datetime(2026, 7, 1)) is None


def test_formatear_fecha_es_coincide_con_el_fixture_real():
    # FECHA14_TEXTO trae "sábado, 11 de julio de 2026" para esta misma fecha
    assert _formatear_fecha_es("2026-07-11") == "sábado 11 de julio de 2026"
    assert _formatear_fecha_es("2026-07-12") == "domingo 12 de julio de 2026"


def test_generar_nomina_arma_el_texto_esperado():
    partido = _partido(direccion="CALLE DOS 200, COMUNA DOS.")

    texto = generar_nomina(partido)
    lineas = texto.splitlines()

    assert lineas[0] == "🏀 MI EQUIPO 45-A vs OTRO EQUIPO 45-A"
    assert lineas[1] == "📅 domingo 12 de julio de 2026"
    assert lineas[2] == "🕔 Citación: 12:30 hrs"
    assert lineas[3] == "🕔 Inicio partido: 13:00 hrs"
    assert lineas[4] == "📍 RECINTO DOS, CALLE DOS 200, COMUNA DOS."
    assert lineas[5] == ""
    assert lineas[6] == "Nómina:"
    assert lineas[7:] == [f"{i}.- " for i in range(1, 13)]


def test_generar_nomina_sin_direccion_usa_solo_el_gimnasio():
    partido = _partido(direccion=None)

    texto = generar_nomina(partido)

    assert texto.splitlines()[4] == "📍 RECINTO DOS"


def test_generar_nomina_citacion_es_30_minutos_antes_del_inicio():
    partido = _partido(hora="09:15")

    texto = generar_nomina(partido)
    lineas = texto.splitlines()

    assert lineas[2] == "🕔 Citación: 08:45 hrs"
    assert lineas[3] == "🕔 Inicio partido: 09:15 hrs"


def test_find_next_match_encuentra_el_partido_del_equipo_en_los_pdfs_vigentes():
    with patch("generar_nomina.discover_pdf_urls", return_value=[(14, "https://fake/fecha14.pdf")]), \
         patch("generar_nomina.download_pdf") as mock_download, \
         patch("generar_nomina.extract_text_from_pdf_bytes", return_value=FECHA14_TEXTO):
        mock_download.return_value.content = b"fake-pdf-bytes"

        config = {"source_url": "https://abss.cl/campeonato/todo.php", "team_name": "MI EQUIPO 45-A"}

        # El partido de MI EQUIPO 45-A en el fixture es domingo 12-07-2026 13:00
        antes = find_next_match(config, now=datetime(2026, 7, 12, 12, 0))
        despues = find_next_match(config, now=datetime(2026, 7, 12, 14, 0))

    assert antes is not None
    assert antes.id_partido == "336"
    assert despues is None
