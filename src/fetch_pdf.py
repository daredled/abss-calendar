"""
fetch_pdf.py

Descubre los PDFs de programación publicados en la página de la liga
(https://abss.cl/campeonato/todo.php) y descarga los N más recientes.

La página lista links con el patrón:
    https://abss.cl/documents/programacion/fecha{N}.pdf?v={timestamp}
    Fecha {N} (rango de fechas)

ordenados del más reciente al más antiguo.
"""

import re
import hashlib
import time
from dataclasses import dataclass

import requests

LINK_RE = re.compile(
    r"(https?://abss\.cl/documents/programacion/fecha(\d+)\.pdf\?v=\d+)"
)

# Algunos hosts (o el WAF/CDN delante) cortan la conexión a clientes que se
# identifican como scripts (el User-Agent por defecto de `requests` es
# "python-requests/x.y.z"). Simulamos un navegador para evitar el corte.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def _get_with_retries(url: str, timeout: int = 30):
    """GET con headers de navegador y reintentos simples ante fallas de
    conexión transitorias (el servidor de ABSS a veces corta la conexión)."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    last_error = None
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_error = e
            if intento < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * intento)
    raise last_error


@dataclass
class PdfInfo:
    fecha_num: int
    url: str
    filename: str  # ej. "fecha14.pdf" (sin query string, usado como key en state.json)
    content: bytes
    md5: str


def discover_pdf_urls(source_url: str) -> list[tuple[int, str]]:
    """
    Devuelve lista de (fecha_num, url) ordenada de más reciente a más antigua,
    tal como aparecen en la página.
    """
    resp = _get_with_retries(source_url)

    seen = set()
    resultados = []
    for match in LINK_RE.finditer(resp.text):
        url, fecha_num_str = match.group(1), match.group(2)
        fecha_num = int(fecha_num_str)
        if fecha_num in seen:
            continue
        seen.add(fecha_num)
        resultados.append((fecha_num, url))

    # Por si la página no viniera ya ordenada, forzamos orden descendente por fecha_num
    resultados.sort(key=lambda t: t[0], reverse=True)
    return resultados


def download_pdf(url: str, fecha_num: int) -> PdfInfo:
    resp = _get_with_retries(url)
    content = resp.content
    md5 = hashlib.md5(content).hexdigest()
    return PdfInfo(
        fecha_num=fecha_num,
        url=url,
        filename=f"fecha{fecha_num}.pdf",
        content=content,
        md5=md5,
    )


def get_latest_pdfs(source_url: str, lookback: int = 1) -> list[PdfInfo]:
    """
    Descarga las `lookback` fechas más recientes (por defecto solo la última).
    Útil por si la liga corrige una fecha anterior después de publicar la actual.
    """
    urls = discover_pdf_urls(source_url)[:lookback]
    return [download_pdf(url, fecha_num) for fecha_num, url in urls]


if __name__ == "__main__":
    import sys

    source = sys.argv[1] if len(sys.argv) > 1 else "https://abss.cl/campeonato/todo.php"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    pdfs = get_latest_pdfs(source, lookback=lookback)
    for pdf in pdfs:
        print(f"{pdf.filename}  md5={pdf.md5}  bytes={len(pdf.content)}  url={pdf.url}")
