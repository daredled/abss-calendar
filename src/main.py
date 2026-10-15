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
from datetime import date

import yaml

from fetch_pdf import download_page, get_latest_pdfs
from parse_pdf import extract_text_from_pdf, parse_pdf_text
from parse_web import parse_proximos_html
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

# Página con los próximos encuentros en texto: respaldo cuando el PDF de la
# última jornada viene escaneado (ver parse_web.py).
DEFAULT_WEB_URL = "https://abss.cl/campeonato/"


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


def direcciones_conocidas(known_matches: dict) -> dict:
    """
    Función pura: gimnasio -> dirección, tomada del partido más reciente de
    cada gimnasio en el estado. La página de respaldo no trae direcciones.
    """
    direcciones = {}
    for m in sorted(known_matches.values(), key=lambda m: m.get("fecha") or ""):
        if m.get("gimnasio") and m.get("direccion"):
            direcciones[m["gimnasio"]] = m["direccion"]
    return direcciones


def descartar_web_desactualizada(partidos_web: list, known_matches: dict,
                                 jornada: str) -> tuple[list, list]:
    """
    Función pura: separa los partidos leídos de la página de respaldo en
    (válidos, descartados).

    La página no dice a qué jornada corresponde: se asume que es la del PDF
    escaneado, pero si la página todavía no se actualizó mostraría partidos
    de la jornada anterior, que con la llave de la nueva se duplicarían en el
    calendario. Por eso se descarta todo partido que no sea posterior a los
    partidos conocidos de otras jornadas.
    """
    ultima_fecha_previa = max(
        (m["fecha"] for m in known_matches.values()
         if m.get("fecha") and m.get("jornada") != jornada),
        default="",
    )
    validos, descartados = [], []
    for p in partidos_web:
        (validos if p.fecha > ultima_fecha_previa else descartados).append(p)
    return validos, descartados


def leer_respaldo_web(config: dict, jornada: str, known_matches: dict) -> list:
    """Partidos del equipo según la página de próximos encuentros, asumiendo
    que son de `jornada`. Nunca levanta excepción: si algo falla, lo registra
    y devuelve [] (el calendario queda como estaba)."""
    url = config.get("web_url", DEFAULT_WEB_URL)
    try:
        html = download_page(url)
    except Exception:
        log.exception("No se pudo descargar la página de respaldo %s.", url)
        return []

    partidos = parse_proximos_html(
        html, config["team_name"], jornada=jornada, hoy=date.today(),
        direcciones_conocidas=direcciones_conocidas(known_matches),
    )
    validos, descartados = descartar_web_desactualizada(partidos, known_matches, jornada)
    for p in descartados:
        log.warning(
            "Respaldo web: se descarta %s vs %s del %s; no es posterior a los "
            "partidos de jornadas anteriores, la página parece desactualizada.",
            p.equipo_local, p.equipo_visita, p.fecha,
        )
    log.info("Respaldo web (%s): %d partido(s) de %s para la jornada %s.",
             url, len(validos), config["team_name"], jornada)
    return validos


def main():
    config = load_config()
    state = load_state()

    log.info("Buscando PDFs vigentes en %s", config["source_url"])
    lookback = config.get("fechas_lookback", 1)
    pdfs = get_latest_pdfs(config["source_url"], lookback=lookback)

    # Nombres completos de rivales de partidos ya sincronizados: el PDF nuevo
    # a veces trunca nombres largos con "…" y así se pueden completar.
    equipos_conocidos = {
        e for m in state["matches"].values()
        for e in (m.get("equipo_local"), m.get("equipo_visita")) if e
    }

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
    #
    # La llave de cada partido es `clave` (ver parse_pdf.Partido): el id del
    # PDF en el formato viejo, o una llave sintética jornada+categoría+equipos
    # en el nuevo (jornada 22 en adelante), que dejó de traer id de partido.
    partidos_actuales = {}  # clave -> dict
    partido_pdf = {}  # clave -> filename del PDF de origen
    pdfs_parseados = []  # PDFs de los que sí se pudo extraer texto
    pdfs_sin_texto = []  # PDFs escaneados: se intenta el respaldo web
    for pdf in changed_pdfs:
        with open(TMP_PDF_PATH, "wb") as f:
            f.write(pdf.content)
        try:
            texto = extract_text_from_pdf(TMP_PDF_PATH)
        finally:
            if os.path.exists(TMP_PDF_PATH):
                os.remove(TMP_PDF_PATH)

        if not texto.strip():
            log.warning(
                "%s no tiene capa de texto (PDF escaneado / solo imagen). "
                "No se puede parsear: NO se guarda su hash, para reintentar "
                "en la próxima corrida.",
                pdf.filename,
            )
            pdfs_sin_texto.append(pdf)
            continue

        pdfs_parseados.append(pdf)
        partidos = parse_pdf_text(
            texto, config["team_name"], jornada=str(pdf.fecha_num),
            equipos_conocidos=equipos_conocidos,
        )
        log.info("%s: %d partido(s) de %s encontrados.", pdf.filename, len(partidos), config["team_name"])
        for p in partidos:
            partidos_actuales[p.clave] = p.to_dict()
            partido_pdf[p.clave] = pdf.filename

    # Respaldo para PDFs escaneados: la página de próximos encuentros. Solo
    # sirve para la última jornada publicada (la página no muestra las
    # anteriores) y solo crea/actualiza: un partido que no aparece puede
    # haberse jugado ya, así que nunca se borra nada a partir de ella. El
    # hash del PDF tampoco se guarda, para volver a intentar con el PDF en la
    # próxima corrida (por si lo republican con texto).
    claves_web = set()
    ultima_jornada = max(p.fecha_num for p in pdfs)
    for pdf in pdfs_sin_texto:
        if pdf.fecha_num != ultima_jornada:
            log.warning("%s no es la última jornada: la página de próximos "
                        "encuentros no sirve de respaldo, se omite.", pdf.filename)
            continue
        for p in leer_respaldo_web(config, str(pdf.fecha_num), state["matches"]):
            partidos_actuales[p.clave] = p.to_dict()
            partido_pdf[p.clave] = pdf.filename
            claves_web.add(p.clave)

    if not pdfs_parseados and not claves_web:
        log.warning("Ninguno de los PDFs cambiados se pudo parsear. Fin.")
        return

    if not partidos_actuales:
        log.info(
            "No se encontraron partidos de '%s' en los PDFs parseados. "
            "Se actualizan los hashes (para no reparsearlos) pero no se toca "
            "el calendario.",
            config["team_name"],
        )
        for pdf in pdfs_parseados:
            state["pdf_hashes"][pdf.filename] = pdf.md5
        save_state(state)
        return

    duration = config.get("event_duration_minutes", 80)

    known_matches = state["matches"]

    # Migración: partidos guardados antes de rastrear "pdf_filename" no
    # tienen ese dato. Si vuelven a aparecer en un PDF que se reprocesa,
    # lo completamos ahora para que no se traten como "nuevos" (duplicado)
    # más abajo.
    for clave, filename in partido_pdf.items():
        m = known_matches.get(clave)
        if m is not None and "pdf_filename" not in m:
            m["pdf_filename"] = filename

    # Solo los partidos cuyo PDF de origen se reprocesó en esta corrida son
    # candidatos a "borrado". Los que viven en PDFs sin cambios (o que no se
    # pudieron parsear) quedan fuera del diff y no se tocan.
    changed_filenames = {pdf.filename for pdf in pdfs_parseados}
    known_matches_scoped = scope_known_matches(known_matches, changed_filenames)
    # Los del respaldo web se comparan contra lo conocido (para actualizar en
    # vez de duplicar), pero como siempre están en partidos_actuales nunca
    # pueden salir como "borrados".
    known_matches_scoped.update(
        {c: known_matches[c] for c in claves_web if c in known_matches}
    )

    diff = compute_diff(partidos_actuales, known_matches_scoped)

    # Solo se conecta a Google si hay algo que cambiar: el respaldo web se
    # relee en cada corrida mientras el PDF siga escaneado.
    if diff["nuevos"] or diff["actualizados"] or diff["borrados"]:
        sync = CalendarSync(
            credentials_path=CREDENTIALS_PATH,
            token_path=TOKEN_PATH,
            calendar_id=config["google_calendar_id"],
            timezone=config.get("timezone", "America/Santiago"),
        )

    for clave in diff["nuevos"]:
        partido = partidos_actuales[clave]
        # Antes de crear, nos fijamos si ya existe un evento para este
        # partido en el calendario (ej. si state.json se perdió). Si ya
        # existe, lo reutilizamos y lo actualizamos en vez de duplicarlo.
        event_id = sync.find_event_id_by_partido(clave)
        if event_id:
            sync.update_event(event_id, partido, duration)
            log.info("Recuperado: partido %s ya tenía evento en el calendario, no se duplicó (%s vs %s, %s %s)",
                      clave, partido["equipo_local"], partido["equipo_visita"],
                      partido["fecha"], partido["hora"])
        else:
            event_id = sync.insert_event(partido, duration)
            log.info("Creado: partido %s (%s vs %s, %s %s)",
                      clave, partido["equipo_local"], partido["equipo_visita"],
                      partido["fecha"], partido["hora"])
        known_matches[clave] = {**partido, "event_id": event_id, "pdf_filename": partido_pdf[clave]}

    for clave in diff["actualizados"]:
        partido_nuevo = partidos_actuales[clave]
        partido_previo = known_matches[clave]
        event_id = partido_previo["event_id"]
        sync.update_event(event_id, partido_nuevo, duration)
        known_matches[clave] = {**partido_nuevo, "event_id": event_id, "pdf_filename": partido_pdf[clave]}
        log.info("Actualizado: partido %s (nuevo horario/lugar: %s %s @ %s)",
                  clave, partido_nuevo["fecha"], partido_nuevo["hora"], partido_nuevo["gimnasio"])

    for clave in diff["sin_cambios"]:
        # sin cambios, igual refrescamos los datos por si acaso
        partido_nuevo = partidos_actuales[clave]
        partido_previo = known_matches[clave]
        known_matches[clave] = {**partido_nuevo, "event_id": partido_previo["event_id"], "pdf_filename": partido_pdf[clave]}

    for clave in diff["borrados"]:
        event_id = known_matches[clave]["event_id"]
        sync.delete_event(event_id)
        log.info("Borrado: partido %s ya no aparece en la programación vigente.", clave)
        del known_matches[clave]

    state["matches"] = known_matches
    for pdf in pdfs_parseados:
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
