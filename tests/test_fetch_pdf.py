from unittest.mock import patch, MagicMock

import requests
from fetch_pdf import (
    discover_pdf_urls,
    download_pdf,
    get_latest_pdfs,
    LINK_RE,
    _get_with_retries,
    MAX_RETRIES,
)


SAMPLE_HTML = """
<ul>
<li><a href="https://abss.cl/documents/programacion/fecha14.pdf?v=1783373824" target="_blank">Fecha 14 (11 y 12 de Julio)</a></li>
<li><a href="https://abss.cl/documents/programacion/fecha13.pdf?v=1783300000" target="_blank">Fecha 13 (02 al 05 de Julio)</a></li>
<li><a href="https://abss.cl/documents/programacion/fecha1.pdf?v=1780000000" target="_blank">Fecha 01 (20 y 21 de Marzo)</a></li>
</ul>
"""


def _mock_response(text=None, content=None, status=200):
    resp = MagicMock()
    resp.text = text
    resp.content = content
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


def test_link_regex_extrae_url_y_numero_de_fecha():
    matches = list(LINK_RE.finditer(SAMPLE_HTML))
    assert len(matches) == 3
    assert matches[0].group(2) == "14"
    assert "fecha14.pdf" in matches[0].group(1)


def test_discover_pdf_urls_ordena_de_mas_reciente_a_mas_antigua():
    with patch("fetch_pdf._get_with_retries", return_value=_mock_response(text=SAMPLE_HTML)):
        urls = discover_pdf_urls("https://abss.cl/campeonato/todo.php")

    fecha_nums = [num for num, _ in urls]
    assert fecha_nums == [14, 13, 1]


def test_discover_pdf_urls_sin_duplicados():
    html_con_duplicado = SAMPLE_HTML + (
        '<a href="https://abss.cl/documents/programacion/fecha14.pdf?v=999">dup</a>'
    )
    with patch("fetch_pdf._get_with_retries", return_value=_mock_response(text=html_con_duplicado)):
        urls = discover_pdf_urls("https://abss.cl/campeonato/todo.php")

    fecha_nums = [num for num, _ in urls]
    assert fecha_nums.count(14) == 1


def test_download_pdf_calcula_md5_correctamente():
    contenido_fake = b"contenido de prueba del pdf"
    import hashlib
    md5_esperado = hashlib.md5(contenido_fake).hexdigest()

    with patch("fetch_pdf._get_with_retries", return_value=_mock_response(content=contenido_fake)):
        info = download_pdf("https://abss.cl/documents/programacion/fecha14.pdf?v=123", 14)

    assert info.md5 == md5_esperado
    assert info.filename == "fecha14.pdf"
    assert info.fecha_num == 14


def test_get_latest_pdfs_respeta_lookback():
    contenido_fake = b"x"

    def side_effect(url, timeout=30):
        if "todo.php" in url:
            return _mock_response(text=SAMPLE_HTML)
        return _mock_response(content=contenido_fake)

    with patch("fetch_pdf._get_with_retries", side_effect=side_effect):
        pdfs = get_latest_pdfs("https://abss.cl/campeonato/todo.php", lookback=2)

    assert len(pdfs) == 2
    assert [p.fecha_num for p in pdfs] == [14, 13]


def test_get_with_retries_usa_headers_de_navegador():
    with patch("fetch_pdf.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = _mock_response(text="ok")
        mock_session_cls.return_value = mock_session

        _get_with_retries("https://abss.cl/campeonato/todo.php")

        mock_session.headers.update.assert_called_once()
        headers_usados = mock_session.headers.update.call_args[0][0]
        assert "User-Agent" in headers_usados
        assert "python-requests" not in headers_usados["User-Agent"]


def test_get_with_retries_reintenta_ante_error_de_conexion():
    with patch("fetch_pdf.requests.Session") as mock_session_cls, \
         patch("fetch_pdf.time.sleep") as mock_sleep:
        mock_session = MagicMock()
        # Falla las primeras veces, luego responde bien
        mock_session.get.side_effect = [
            requests.exceptions.ConnectionError("Remote end closed connection"),
            requests.exceptions.ConnectionError("Remote end closed connection"),
            _mock_response(text="ok"),
        ]
        mock_session_cls.return_value = mock_session

        resp = _get_with_retries("https://abss.cl/campeonato/todo.php")

        assert resp.text == "ok"
        assert mock_session.get.call_count == 3
        assert mock_sleep.call_count == 2  # espera entre reintentos, no después del éxito


def test_get_with_retries_propaga_error_tras_agotar_reintentos():
    with patch("fetch_pdf.requests.Session") as mock_session_cls, \
         patch("fetch_pdf.time.sleep"):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("caído")
        mock_session_cls.return_value = mock_session

        try:
            _get_with_retries("https://abss.cl/campeonato/todo.php")
            assert False, "debería haber lanzado ConnectionError"
        except requests.exceptions.ConnectionError:
            pass

        assert mock_session.get.call_count == MAX_RETRIES
