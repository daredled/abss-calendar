"""
main.py

Orquesta el flujo completo:
  1. Descubre y descarga el/los PDF(s) vigentes.
  2. Compara MD5 contra state.json; si no cambió, no hace nada más.
  3. Parsea los partidos del equipo configurado.
  4. Compara contra el estado anterior (por ID de partido).
  5. Inserta / actualiza / borra eventos en Google Calendar.
  6. Persiste el nuevo estado.

Pensado para correr vía cron cada hora.
"""

import argparse
import json
import logging
import os
import sys

import yaml

from fetch_pdf import get_latest_pdfs
from parse_pdf import extract_text_from_pdf, parse_pdf_text
from sync_calendar import CalendarSync

# Los archivos de configuración/estado viven en la raíz del repo, un nivel
# arriba de src/ (donde vive este archivo).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
TMP_PDF_PATH = os.path.join(BASE_DIR, "_tmp_fecha.pdf")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("abss-sync")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"pdf_hashes": {}, "matches": {}}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


CAMPOS_CLAVE_CAMBIO = ("fecha", "hora", "gimnasio", "direccion")


def compute_diff(partidos_actuales: dict, known_matches: dict,
                  campos_clave=CAMPOS_CLAVE_CAMBIO) -> dict:
    """
    Función pura: no toca red ni disco. Dado el snapshot actual de partidos
    (id_partido -> dict) y el estado conocido previo (id_partido -> dict con
    'event_id'), devuelve qué hay que crear, actualizar y borrar.

    Retorna:
        {
            "nuevos": [id_partido, ...],
            "actualizados": [id_partido, ...],
            "sin_cambios": [id_partido, ...],
            "borrados": [id_partido, ...],
        }
    """
    ids_actuales = set(partidos_actuales.keys())
    ids_conocidos = set(known_matches.keys())

    nuevos = sorted(ids_actuales - ids_conocidos)
    borrados = sorted(ids_conocidos - ids_actuales)

    actualizados = []
    sin_cambios = []
    for id_partido in sorted(ids_actuales & ids_conocidos):
        actual = partidos_actuales[id_partido]
        previo = known_matches[id_partido]
        cambio = any(actual.get(c) != previo.get(c) for c in campos_clave)
        (actualizados if cambio else sin_cambios).append(id_partido)

    return {
        "nuevos": nuevos,
        "actualizados": actualizados,
        "sin_cambios": sin_cambios,
        "borrados": borrados,
    }


def scope_known_matches(known_matches: dict, changed_filenames: set) -> dict:
    """
    Función pura: no toca red ni disco. Filtra known_matches para quedarnos
    solo con los partidos cuyo PDF de origen ('pdf_filename') está entre los
    que se reprocesaron en esta corrida.

    Esto es necesario porque compute_diff() marca como "borrado" cualquier
    id conocido que no aparezca en el snapshot actual; si ese snapshot solo
    cubre los PDFs cambiados, un partido que vive en un PDF sin cambios
    parecería haber desaparecido y se borraría por error. Al excluirlo del
    diff directamente, nunca se lo considera candidato a borrado.

    Partidos sin 'pdf_filename' (guardados antes de rastrear ese dato)
    también quedan afuera hasta que main() los reasocie a un PDF real.
    """
    return {
        id_partido: m for id_partido, m in known_matches.items()
        if m.get("pdf_filename") in changed_filenames
    }


def main():
    config = load_config()
    state = load_state()

    log.info("Buscando PDFs vigentes en %s", config["source_url"])
    lookback = config.get("fechas_lookback", 1)
    pdfs = get_latest_pdfs(config["source_url"], lookback=lookback)

    changed_pdfs = []
    for pdf in pdfs:
        prev_md5 = state["pdf_hashes"].get(pdf.filename)
        if prev_md5 == pdf.md5:
            log.info("%s sin cambios (md5 igual), se omite.", pdf.filename)
            continue
        log.info("%s cambió (md5 nuevo), se procesará.", pdf.filename)
        changed_pdfs.append(pdf)

    if not changed_pdfs:
        log.info("Nada que actualizar. Fin.")
        return

    # Parsear todos los PDFs cambiados y juntar los partidos del equipo.
    # También recordamos de qué PDF vino cada partido: más abajo usamos ese
    # dato para no comparar contra partidos que viven en PDFs sin cambios
    # (si no, como no fueron reparseados, parecerían haber desaparecido).
    partidos_actuales = {}  # id_partido -> dict
    partido_pdf = {}  # id_partido -> filename del PDF de origen
    for pdf in changed_pdfs:
        with open(TMP_PDF_PATH, "wb") as f:
            f.write(pdf.content)
        try:
            texto = extract_text_from_pdf(TMP_PDF_PATH)
        finally:
            if os.path.exists(TMP_PDF_PATH):
                os.remove(TMP_PDF_PATH)

        partidos = parse_pdf_text(texto, config["team_name"])
        log.info("%s: %d partido(s) de %s encontrados.", pdf.filename, len(partidos), config["team_name"])
        for p in partidos:
            partidos_actuales[p.id_partido] = p.to_dict()
            partido_pdf[p.id_partido] = pdf.filename

    if not partidos_actuales:
        log.warning(
            "No se encontraron partidos de '%s' en los PDFs cambiados. "
            "Se actualizan los hashes pero no se toca el calendario.",
            config["team_name"],
        )
        for pdf in changed_pdfs:
            state["pdf_hashes"][pdf.filename] = pdf.md5
        save_state(state)
        return

    sync = CalendarSync(
        credentials_path=CREDENTIALS_PATH,
        token_path=TOKEN_PATH,
        calendar_id=config["google_calendar_id"],
        timezone=config.get("timezone", "America/Santiago"),
    )
    duration = config.get("event_duration_minutes", 80)

    known_matches = state["matches"]

    # Migración: partidos guardados antes de rastrear "pdf_filename" no
    # tienen ese dato. Si vuelven a aparecer en un PDF que se reprocesa,
    # lo completamos ahora para que no se traten como "nuevos" (duplicado)
    # más abajo.
    for id_partido, filename in partido_pdf.items():
        m = known_matches.get(id_partido)
        if m is not None and "pdf_filename" not in m:
            m["pdf_filename"] = filename

    # Solo los partidos cuyo PDF de origen se reprocesó en esta corrida son
    # candidatos a "borrado". Los que viven en PDFs sin cambios quedan fuera
    # del diff y no se tocan.
    changed_filenames = {pdf.filename for pdf in changed_pdfs}
    known_matches_scoped = scope_known_matches(known_matches, changed_filenames)

    diff = compute_diff(partidos_actuales, known_matches_scoped)

    for id_partido in diff["nuevos"]:
        partido = partidos_actuales[id_partido]
        # Antes de crear, nos fijamos si ya existe un evento para este
        # id_partido en el calendario (ej. si state.json se perdió). Si ya
        # existe, lo reutilizamos y lo actualizamos en vez de duplicarlo.
        event_id = sync.find_event_id_by_partido(id_partido)
        if event_id:
            sync.update_event(event_id, partido, duration)
            log.info("Recuperado: partido %s ya tenía evento en el calendario, no se duplicó (%s vs %s, %s %s)",
                      id_partido, partido["equipo_local"], partido["equipo_visita"],
                      partido["fecha"], partido["hora"])
        else:
            event_id = sync.insert_event(partido, duration)
            log.info("Creado: partido %s (%s vs %s, %s %s)",
                      id_partido, partido["equipo_local"], partido["equipo_visita"],
                      partido["fecha"], partido["hora"])
        known_matches[id_partido] = {**partido, "event_id": event_id, "pdf_filename": partido_pdf[id_partido]}

    for id_partido in diff["actualizados"]:
        partido_nuevo = partidos_actuales[id_partido]
        partido_previo = known_matches[id_partido]
        event_id = partido_previo["event_id"]
        sync.update_event(event_id, partido_nuevo, duration)
        known_matches[id_partido] = {**partido_nuevo, "event_id": event_id, "pdf_filename": partido_pdf[id_partido]}
        log.info("Actualizado: partido %s (nuevo horario/lugar: %s %s @ %s)",
                  id_partido, partido_nuevo["fecha"], partido_nuevo["hora"], partido_nuevo["gimnasio"])

    for id_partido in diff["sin_cambios"]:
        # sin cambios, igual refrescamos los datos por si acaso
        partido_nuevo = partidos_actuales[id_partido]
        partido_previo = known_matches[id_partido]
        known_matches[id_partido] = {**partido_nuevo, "event_id": partido_previo["event_id"], "pdf_filename": partido_pdf[id_partido]}

    for id_partido in diff["borrados"]:
        event_id = known_matches[id_partido]["event_id"]
        sync.delete_event(event_id)
        log.info("Borrado: partido %s ya no aparece en la programación vigente.", id_partido)
        del known_matches[id_partido]

    state["matches"] = known_matches
    for pdf in changed_pdfs:
        state["pdf_hashes"][pdf.filename] = pdf.md5

    save_state(state)
    log.info("Sincronización completada.")


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser que muestra la ayuda completa ante errores de parseo."""

    def error(self, message):
        self.print_help(sys.stderr)
        sys.stderr.write(f"\nerror: {message}\n")
        sys.exit(2)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Sincroniza los partidos del equipo configurado con Google Calendar.",
    )
    parser.add_argument(
        "--nomina", action="store_true",
        help="Genera y muestra la nómina del próximo partido, sin sincronizar el calendario.",
    )

    args = parser.parse_args()

    if args.nomina:
        from generar_nomina import find_next_match, generar_nomina

        partido = find_next_match(load_config())
        if partido is None:
            log.info("No se encontró ningún partido próximo programado.")
            sys.exit(1)
        print(generar_nomina(partido))
        sys.exit(0)

    try:
        main()
    except Exception:
        log.exception("Fallo la sincronización, no se modifica el estado.")
        sys.exit(1)
