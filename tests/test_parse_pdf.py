from parse_pdf import parse_pdf_text, _split_team_category, _parse_date_line
from tests.fixtures import FECHA14_TEXTO, FECHA22_TEXTO


def test_equipo_con_un_solo_partido():
    partidos = parse_pdf_text(FECHA14_TEXTO, "MI EQUIPO 45-A")
    assert len(partidos) == 1
    p = partidos[0]
    assert p.id_partido == "336"
    assert p.fecha == "2026-07-12"
    assert p.hora == "13:00"
    assert p.gimnasio == "RECINTO DOS"
    assert p.direccion == "CALLE DOS 200, COMUNA DOS"
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


def test_gimnasio_y_direccion_en_la_misma_linea_se_separan():
    # Formato actual real de ABSS: al extraer con layout=True, el nombre del
    # gimnasio y su dirección quedan en la misma línea, separados por el
    # espacio en blanco de la columna de la tabla (mucho más largo que un
    # espacio simple entre palabras).
    texto = (
        "sábado, 11 de julio de 2026\n"
        "GIMNASIO BRISAS                                 LUCIANO ORTIZ 8450, LA CISTERNA.\n"
        "HORA LOCAL VISITA GRUPO AGRUPACIÓN DE ARBITROS\n"
        "09:00 MI EQUIPO 45-A OTRO EQUIPO 45-A SERIE 45 ARBITRO UNO ARBITRO DOS 3537 15\n"
    )
    partidos = parse_pdf_text(texto, "MI EQUIPO 45-A")
    assert len(partidos) == 1
    assert partidos[0].gimnasio == "BRISAS"
    assert partidos[0].direccion == "LUCIANO ORTIZ 8450, LA CISTERNA"


def test_gimnasio_con_nombre_compuesto_y_direccion_se_separan():
    texto = (
        "sábado, 11 de julio de 2026\n"
        "GIMNASIO PRINCE OF WALES COUNTRY CLUB     LAS ARAÑAS 1901, LA REINA\n"
        "HORA LOCAL VISITA GRUPO AGRUPACIÓN DE ARBITROS\n"
        "09:00 MI EQUIPO 45-A OTRO EQUIPO 45-A SERIE 45 ARBITRO UNO ARBITRO DOS 3537 15\n"
    )
    partidos = parse_pdf_text(texto, "MI EQUIPO 45-A")
    assert partidos[0].gimnasio == "PRINCE OF WALES COUNTRY CLUB"
    assert partidos[0].direccion == "LAS ARAÑAS 1901, LA REINA"


def test_gimnasio_sin_direccion_en_la_misma_linea_no_falla():
    texto = (
        "sábado, 11 de julio de 2026\n"
        "GIMNASIO RECINTO UNO\n"
        "HORA LOCAL VISITA GRUPO AGRUPACIÓN DE ARBITROS\n"
        "09:00 MI EQUIPO 45-A OTRO EQUIPO 45-A SERIE 45 ARBITRO UNO ARBITRO DOS 3537 15\n"
    )
    partidos = parse_pdf_text(texto, "MI EQUIPO 45-A")
    assert partidos[0].gimnasio == "RECINTO UNO"
    assert partidos[0].direccion is None


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


# ---------------------------------------------------------------------------
# Formato nuevo del PDF (jornada 22 en adelante): equipos separados por "VS",
# árbitros en línea aparte, y sin id de partido ni cancha en la fila.
# ---------------------------------------------------------------------------


def test_formato_nuevo_equipo_como_visita():
    partidos = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 45-A", jornada="22")
    assert len(partidos) == 1
    p = partidos[0]
    assert p.id_partido is None
    assert p.cancha is None
    assert p.fecha == "2026-09-12"
    assert p.hora == "18:45"
    assert p.gimnasio == "RECINTO UNO"
    assert p.direccion == "CALLE UNO 100, COMUNA UNO"
    assert p.equipo_local == "CLUB E 45-A"
    assert p.equipo_visita == "MI EQUIPO 45-A"
    assert p.categoria == "SERIE 45"
    assert p.jornada == "22"


def test_formato_nuevo_equipo_como_local_y_segundo_dia():
    partidos = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 50-A", jornada="22")
    assert len(partidos) == 1
    p = partidos[0]
    assert p.fecha == "2026-09-13"  # bloque del domingo
    assert p.hora == "10:20"
    assert p.gimnasio == "RECINTO TRES"
    assert p.direccion == "CALLE TRES 300"  # dirección sin coma
    assert p.equipo_local == "MI EQUIPO 50-A"
    assert p.equipo_visita == "CLUB M 50-A"


def test_formato_nuevo_categoria_exacta_no_hace_match_parcial():
    p45 = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 45-A", jornada="22")
    p60 = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 60-B", jornada="22")
    assert [p.hora for p in p45] == ["18:45"]
    assert [p.hora for p in p60] == ["16:20"]


def test_formato_nuevo_equipo_sin_partidos_devuelve_lista_vacia():
    assert parse_pdf_text(FECHA22_TEXTO, "EQUIPO_QUE_NO_EXISTE 99-Z", jornada="22") == []


def test_formato_nuevo_lee_la_jornada_del_encabezado_si_no_se_pasa():
    partidos = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 45-A")
    assert partidos[0].jornada == "22"


def test_formato_nuevo_clave_es_estable_ante_reprogramacion():
    # Sin id de partido, la clave se deriva de jornada + categoría + equipos,
    # así que un cambio de fecha/hora es el MISMO partido (actualización).
    base = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 45-A", jornada="22")[0]
    reprogramado = FECHA22_TEXTO.replace(
        "18:45    CLUB E 45-A           VS    MI EQUIPO 45-A",
        "20:00    CLUB E 45-A           VS    MI EQUIPO 45-A",
    )
    otro = parse_pdf_text(reprogramado, "MI EQUIPO 45-A", jornada="22")[0]
    assert otro.hora == "20:00"
    assert otro.clave == base.clave
    assert base.clave == "J22|SERIE 45|CLUB E 45-A|MI EQUIPO 45-A"


def test_formato_nuevo_no_confunde_el_pie_actualizado_al_con_una_fecha():
    # El pie "TOTAL: ... Actualizado al: lunes, 7 de septiembre de 2026" trae
    # una fecha embebida que no es la de ningún partido.
    partidos = parse_pdf_text(FECHA22_TEXTO, "MI EQUIPO 50-A", jornada="22")
    assert partidos[0].fecha == "2026-09-13"


def test_parse_date_line_formato_nuevo_mayusculas_y_texto_extra():
    d = _parse_date_line("SÁBADO,  12 DE SEPTIEMBRE DE 2026                14 PARTIDOS")
    assert d is not None
    assert d.isoformat() == "2026-09-12"


def test_parse_date_line_ignora_fecha_del_pie_actualizado():
    # Esta sí matchea el patrón de fecha (por eso el parser la filtra por el
    # prefijo "Actualizado"), pero _parse_date_line en sí no la reconoce
    # porque no empieza con un día de la semana.
    assert _parse_date_line("Actualizado al: lunes, 7 de septiembre de 2026") is None
