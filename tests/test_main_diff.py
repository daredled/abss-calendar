from main import compute_diff, scope_known_matches


def _partido(fecha="2026-07-12", hora="13:00", gimnasio="RECINTO DOS", direccion="DIR X"):
    return {
        "fecha": fecha,
        "hora": hora,
        "gimnasio": gimnasio,
        "direccion": direccion,
        "equipo_local": "MI EQUIPO 45-A",
        "equipo_visita": "OTRO EQUIPO 45-A",
        "categoria": "SERIE 45",
        "cancha": "14",
    }


def test_partido_nuevo_se_detecta_como_nuevo():
    actuales = {"336": _partido()}
    conocidos = {}

    diff = compute_diff(actuales, conocidos)

    assert diff["nuevos"] == ["336"]
    assert diff["actualizados"] == []
    assert diff["sin_cambios"] == []
    assert diff["borrados"] == []


def test_partido_sin_cambios_no_se_marca_para_actualizar():
    partido = _partido()
    actuales = {"336": partido}
    conocidos = {"336": {**partido, "event_id": "evt-1"}}

    diff = compute_diff(actuales, conocidos)

    assert diff["nuevos"] == []
    assert diff["actualizados"] == []
    assert diff["sin_cambios"] == ["336"]
    assert diff["borrados"] == []


def test_cambio_de_horario_se_detecta_como_actualizado():
    original = _partido(hora="13:00")
    modificado = _partido(hora="15:00")
    actuales = {"336": modificado}
    conocidos = {"336": {**original, "event_id": "evt-1"}}

    diff = compute_diff(actuales, conocidos)

    assert diff["actualizados"] == ["336"]
    assert diff["sin_cambios"] == []


def test_cambio_de_dia_se_detecta_como_actualizado():
    original = _partido(fecha="2026-07-12")
    modificado = _partido(fecha="2026-07-19")
    actuales = {"336": modificado}
    conocidos = {"336": {**original, "event_id": "evt-1"}}

    diff = compute_diff(actuales, conocidos)

    assert diff["actualizados"] == ["336"]


def test_cambio_de_gimnasio_se_detecta_como_actualizado():
    original = _partido(gimnasio="RECINTO DOS")
    modificado = _partido(gimnasio="RECINTO TRES")
    actuales = {"336": modificado}
    conocidos = {"336": {**original, "event_id": "evt-1"}}

    diff = compute_diff(actuales, conocidos)

    assert diff["actualizados"] == ["336"]


def test_cambio_de_rival_no_altera_estado_si_no_cambian_campos_clave():
    # El ID de partido se mantiene estable aunque cambie el rival (edge case
    # poco común, pero la lógica de diff solo mira fecha/hora/gimnasio/direccion)
    original = _partido()
    modificado = {**_partido(), "equipo_visita": "OTRO_RIVAL 45-A"}
    actuales = {"336": modificado}
    conocidos = {"336": {**original, "event_id": "evt-1"}}

    diff = compute_diff(actuales, conocidos)

    assert diff["sin_cambios"] == ["336"]
    assert diff["actualizados"] == []


def test_partido_que_desaparece_se_marca_para_borrar():
    conocidos = {"336": {**_partido(), "event_id": "evt-1"}}
    actuales = {}

    diff = compute_diff(actuales, conocidos)

    assert diff["borrados"] == ["336"]
    assert diff["nuevos"] == []


def test_mezcla_de_casos_simultaneos():
    conocidos = {
        "336": {**_partido(hora="13:00"), "event_id": "evt-336"},   # se actualiza
        "337": {**_partido(), "event_id": "evt-337"},               # sin cambios
        "338": {**_partido(), "event_id": "evt-338"},               # se borra
    }
    actuales = {
        "336": _partido(hora="15:00"),
        "337": _partido(),
        "339": _partido(),  # nuevo
    }

    diff = compute_diff(actuales, conocidos)

    assert diff["nuevos"] == ["339"]
    assert diff["actualizados"] == ["336"]
    assert diff["sin_cambios"] == ["337"]
    assert diff["borrados"] == ["338"]


def test_scope_known_matches_excluye_partidos_de_pdfs_sin_cambios():
    # Regresión: un partido que vive en un PDF que no cambió esta corrida
    # no debe quedar disponible para compute_diff, o parecería "borrado"
    # simplemente porque su PDF no se reparseó.
    known_matches = {
        "336": {**_partido(), "event_id": "evt-336", "pdf_filename": "fecha14.pdf"},
        "286": {**_partido(), "event_id": "evt-286", "pdf_filename": "fecha12.pdf"},
    }

    scoped = scope_known_matches(known_matches, changed_filenames={"fecha12.pdf"})

    assert scoped == {"286": known_matches["286"]}


def test_scope_known_matches_excluye_partidos_sin_pdf_filename():
    # Partidos guardados antes de rastrear pdf_filename (migración) quedan
    # afuera del scope hasta que main() los reasocie a un PDF real.
    known_matches = {
        "66": {**_partido(), "event_id": "evt-66"},  # sin pdf_filename
    }

    scoped = scope_known_matches(known_matches, changed_filenames={"fecha1.pdf"})

    assert scoped == {}


def test_partido_en_pdf_sin_cambios_no_se_borra_por_error():
    # Reproduce el bug real: fecha14.pdf (con el partido 336) no cambió esta
    # corrida, así que no se reparsea y no aparece en partidos_actuales. Sin
    # el scoping, compute_diff lo marcaría como "borrado" igual.
    known_matches = {
        "336": {**_partido(), "event_id": "evt-336", "pdf_filename": "fecha14.pdf"},
        "286": {**_partido(hora="10:00"), "event_id": "evt-286", "pdf_filename": "fecha12.pdf"},
    }
    # Solo fecha12.pdf cambió y se reparseó; fecha14.pdf no se tocó.
    partidos_actuales = {"286": _partido(hora="10:00")}

    scoped = scope_known_matches(known_matches, changed_filenames={"fecha12.pdf"})
    diff = compute_diff(partidos_actuales, scoped)

    assert diff["borrados"] == []
    assert diff["sin_cambios"] == ["286"]
