"""
Respaldo web en main(): cuando el PDF de la última jornada viene escaneado,
los partidos se leen de la página de próximos encuentros. Se prueba el flujo
completo de main() con dobles para la red, el PDF y Google Calendar.
"""

from typing import ClassVar

import pytest

import main
from fetch_pdf import PdfInfo
from parse_pdf import Partido
from tests.test_parse_web import PROXIMOS_J25_HTML

CONFIG = {
    "team_name": "LICEO 45-A",
    "source_url": "https://abss.cl/campeonato/todo.php",
    "fechas_lookback": 1,
    "google_calendar_id": "cal",
}

CLAVE_J25 = "J25|SERIE 45|BRISAS 45-A|LICEO 45-A"


def _conocido(clave, jornada, fecha, hora, pdf_filename, **extra):
    local, visita = clave.split("|")[2:]
    return {
        "id_partido": None, "fecha": fecha, "hora": hora,
        "gimnasio": "PALMARES CENTRAL", "direccion": "SANTA LUISA 300, QUILICURA",
        "equipo_local": local, "equipo_visita": visita, "categoria": "SERIE 45",
        "cancha": None, "jornada": jornada, "clave": clave,
        "event_id": f"ev-{jornada}", "pdf_filename": pdf_filename, **extra,
    }


J24 = _conocido("J24|SERIE 45|LICEO 45-A|ALVAMINET 45-A", "24", "2026-10-03", "17:55", "fecha24.pdf")


class FakeSync:
    instancias: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.llamadas = []
        FakeSync.instancias.append(self)

    def find_event_id_by_partido(self, clave):
        return None

    def insert_event(self, partido, duration):
        self.llamadas.append(("insert", partido["clave"], partido["hora"]))
        return "ev-nuevo"

    def update_event(self, event_id, partido, duration):
        self.llamadas.append(("update", event_id, partido["hora"]))

    def delete_event(self, event_id):
        self.llamadas.append(("delete", event_id))


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Arma main() con un estado dado y fecha25.pdf escaneado; devuelve el
    estado guardado (o None si no se guardó) y las llamadas a Calendar."""
    FakeSync.instancias = []
    resultado = {"guardado": None}

    def correr(state, html=PROXIMOS_J25_HTML, pdfs=(25,), web_falla=False):
        def download_page(url):
            if web_falla:
                raise ConnectionError("sin red")
            return html

        monkeypatch.setattr(main, "load_config", lambda: dict(CONFIG))
        monkeypatch.setattr(main, "load_state", lambda: state)
        monkeypatch.setattr(main, "save_state", lambda s: resultado.update(guardado=s))
        monkeypatch.setattr(main, "get_latest_pdfs", lambda url, lookback: [
            PdfInfo(n, f"u{n}", f"fecha{n}.pdf", b"%PDF", f"md5-{n}") for n in pdfs
        ])
        monkeypatch.setattr(main, "extract_text_from_pdf", lambda path: "")
        monkeypatch.setattr(main, "download_page", download_page)
        monkeypatch.setattr(main, "CalendarSync", FakeSync)
        monkeypatch.setattr(main, "TMP_PDF_PATH", str(tmp_path / "tmp.pdf"))
        main.main()
        llamadas = [c for s in FakeSync.instancias for c in s.llamadas]
        return resultado["guardado"], llamadas

    return correr


def test_pdf_escaneado_actualiza_partido_existente_desde_la_web(entorno):
    # Caso real del 14-oct-2026: J25 ya estaba a las 19:15 (PDF con texto del
    # 12-oct) y la versión escaneada lo movió a las 17:55.
    previo = _conocido(CLAVE_J25, "25", "2026-10-17", "19:15", "fecha25.pdf")
    state = {"pdf_hashes": {"fecha25.pdf": "md5-viejo"},
             "matches": {J24["clave"]: dict(J24), CLAVE_J25: previo}}

    guardado, llamadas = entorno(state)

    assert llamadas == [("update", "ev-25", "17:55")]
    assert guardado["matches"][CLAVE_J25]["hora"] == "17:55"
    assert guardado["matches"][CLAVE_J25]["event_id"] == "ev-25"
    assert guardado["matches"][CLAVE_J25]["direccion"] == "SANTA LUISA 300, QUILICURA"
    # El hash del PDF escaneado no se guarda: se reintenta con el PDF.
    assert guardado["pdf_hashes"]["fecha25.pdf"] == "md5-viejo"
    assert J24["clave"] in guardado["matches"]


def test_pdf_escaneado_crea_partido_nuevo_desde_la_web(entorno):
    state = {"pdf_hashes": {}, "matches": {J24["clave"]: dict(J24)}}

    guardado, llamadas = entorno(state)

    assert llamadas == [("insert", CLAVE_J25, "17:55")]
    m = guardado["matches"][CLAVE_J25]
    assert m["event_id"] == "ev-nuevo"
    assert m["pdf_filename"] == "fecha25.pdf"
    assert "fecha25.pdf" not in guardado["pdf_hashes"]


def test_respaldo_sin_cambios_no_conecta_con_google(entorno):
    previo = _conocido(CLAVE_J25, "25", "2026-10-17", "17:55", "fecha25.pdf")
    state = {"pdf_hashes": {}, "matches": {CLAVE_J25: previo}}

    _, llamadas = entorno(state)

    assert llamadas == []
    assert FakeSync.instancias == []


def test_respaldo_nunca_borra_partidos_que_no_aparecen_en_la_web(entorno):
    # Otro partido conocido de la misma jornada que la página no muestra
    # (ej. ya se jugó): no debe borrarse.
    otro = _conocido("J25|SERIE 45|LICEO 45-A|ISB 45-A", "25", "2026-10-15", "21:30", "fecha25.pdf")
    state = {"pdf_hashes": {}, "matches": {otro["clave"]: otro}}

    guardado, llamadas = entorno(state)

    assert ("delete", "ev-25") not in llamadas
    assert otro["clave"] in guardado["matches"]


def test_web_desactualizada_no_duplica_jornada_anterior(entorno):
    # La página todavía muestra el partido de la J24 (3-oct): con la llave de
    # la J25 se duplicaría, así que se descarta.
    html = PROXIMOS_J25_HTML.replace("17 de Octubre", "3 de Octubre")
    state = {"pdf_hashes": {}, "matches": {J24["clave"]: dict(J24)}}

    guardado, llamadas = entorno(state, html=html)

    assert llamadas == []
    assert guardado is None


def test_respaldo_solo_para_la_ultima_jornada(entorno):
    # Con lookback 2 y ambos PDFs escaneados, solo la jornada 25 (la última)
    # usa la página: los partidos que muestra no son de la 24.
    state = {"pdf_hashes": {}, "matches": {}}

    guardado, llamadas = entorno(state, pdfs=(25, 24))

    assert llamadas == [("insert", CLAVE_J25, "17:55")]
    assert all(m["jornada"] == "25" for m in guardado["matches"].values())


def test_falla_de_la_web_no_toca_nada(entorno):
    state = {"pdf_hashes": {}, "matches": {J24["clave"]: dict(J24)}}

    guardado, llamadas = entorno(state, web_falla=True)

    assert llamadas == []
    assert guardado is None


def test_descartar_web_desactualizada():
    p = Partido(None, "2026-10-03", "17:55", "X", None, "A 45-A", "B 45-A", "SERIE 45", None, "25")
    validos, descartados = main.descartar_web_desactualizada([p], {J24["clave"]: J24}, "25")
    assert validos == [] and descartados == [p]

    p.fecha = "2026-10-17"
    validos, descartados = main.descartar_web_desactualizada([p], {J24["clave"]: J24}, "25")
    assert validos == [p] and descartados == []


def test_direcciones_conocidas_usa_la_mas_reciente():
    viejo = {"fecha": "2026-08-01", "gimnasio": "G", "direccion": "VIEJA"}
    nuevo = {"fecha": "2026-09-01", "gimnasio": "G", "direccion": "NUEVA"}
    sin_dir = {"fecha": "2026-10-01", "gimnasio": "G", "direccion": None}
    assert main.direcciones_conocidas({"b": nuevo, "a": viejo, "c": sin_dir}) == {"G": "NUEVA"}
