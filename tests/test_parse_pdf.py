from parse_pdf import parse_pdf_text, _split_team_category, _parse_date_line
from tests.fixtures import FECHA14_TEXTO


def test_equipo_con_un_solo_partido():
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 45-A")
    assert len(partidos) == 1
    p = partidos[0]
    assert p.id_partido == "336"
    assert p.fecha == "2026-07-12"
    assert p.hora == "13:00"
    assert p.gimnasio == "RECINTO DOS"
    assert p.direccion == "CALLE DOS 200, COMUNA DOS."
    assert p.equipo_local == "MI EQUIPO 45-A"
    assert p.equipo_visita == "OTRO EQUIPO 45-A"
    assert p.categoria == "SERIE 45"
    assert p.cancha == "14"


def test_equipo_como_local_se_detecta():
    # MI EQUIPO 60-B aparece como LOCAL en la fila del domingo (partido 542)
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 60-B")
    assert len(partidos) == 1
    assert partidos[0].id_partido == "542"
    assert partidos[0].equipo_local == "MI EQUIPO 60-B"
    assert partidos[0].equipo_visita == "EQUIPO RIVAL 60-A"


def test_equipo_como_visita_tambien_se_detecta():
    # MI EQUIPO 50-C aparece como VISITA en la fila del domingo (partido 487)
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 50-C")
    assert len(partidos) == 1
    assert partidos[0].id_partido == "487"
    assert partidos[0].equipo_visita == "MI EQUIPO 50-C"
    assert partidos[0].equipo_local == "EQUIPO RIVAL 50-A"


def test_categoria_exacta_no_hace_match_parcial():
    # "MI EQUIPO" tiene partidos en 45-A, 50-A, 50-C, 60-A, 60-B, 70-A.
    # Pedir "MI EQUIPO 60-A" no debe traer el de "MI EQUIPO 60-B" ni viceversa.
    partidos_60a = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 60-A")
    partidos_60b = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 60-B")
    assert {p.id_partido for p in partidos_60a} == {"544"}
    assert {p.id_partido for p in partidos_60b} == {"542"}


def test_equipo_con_varios_partidos_en_distintos_gimnasios_y_fechas():
    # MI EQUIPO tiene partidos repartidos en varias categorías/fechas/gimnasios;
    # tomamos "MI EQUIPO 50-A" para validar que solo trae el suyo (443) y no
    # arrastra datos del bloque anterior.
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 50-A")
    assert len(partidos) == 1
    assert partidos[0].id_partido == "443"
    assert partidos[0].fecha == "2026-07-12"
    assert partidos[0].gimnasio == "RECINTO UNO"


def test_equipo_sin_partidos_devuelve_lista_vacia():
    partidos = parse_pdf_text(FECHA14_TEXTO, "EQUIPO_QUE_NO_EXISTE 99-Z")
    assert partidos == []


def test_direccion_sin_coma_tambien_se_captura():
    # GIMNASIO RECINTO CINCO tiene dirección sin coma ("CALLE CINCO 500"),
    # a diferencia de las demás que vienen como "CALLE NUM, COMUNA."
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 60-B")
    assert partidos[0].gimnasio == "RECINTO CINCO"
    assert partidos[0].direccion == "CALLE CINCO 500"


def test_split_team_category_con_nombre_compuesto():
    nombre, cat = _split_team_category("U.CLUB EJEMPLO 45-A")
    assert nombre == "U.CLUB EJEMPLO"
    assert cat == "45-A"


def test_split_team_category_con_nombre_simple():
    nombre, cat = _split_team_category("EQUIPO 45-A")
    assert nombre == "EQUIPO"
    assert cat == "45-A"


def test_split_team_category_sin_categoria_devuelve_nombre_completo():
    nombre, cat = _split_team_category("ALGO_RARO")
    assert nombre == "ALGO_RARO"
    assert cat == ""


def test_parse_date_line_sabado():
    d = _parse_date_line("sábado, 11 de julio de 2026")
    assert d is not None
    assert d.isoformat() == "2026-07-11"


def test_parse_date_line_domingo():
    d = _parse_date_line("domingo, 12 de julio de 2026")
    assert d.isoformat() == "2026-07-12"


def test_parse_date_line_linea_invalida_devuelve_none():
    assert _parse_date_line("HORA LOCAL VISITA AGRUPACIÓN DE ARBITROS") is None
    assert _parse_date_line("GIMNASIO RECINTO DOS") is None


def test_busqueda_es_insensible_a_mayusculas():
    partidos_mayus = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 45-A")
    partidos_minus = parse_pdf_text(FECHA14_TEXTO, "mi equipo 45-a")
    assert {p.id_partido for p in partidos_mayus} == {p.id_partido for p in partidos_minus}
