"""
Fixtures compartidas por los tests.

FECHA14_TEXTO es un texto de ejemplo con el mismo formato que un PDF real
de programación de ABSS (mismos encabezados, columnas y estructura de
bloques por gimnasio/fecha), pero con equipos, árbitros, gimnasios y
direcciones ficticios. Se usa como caso de prueba de referencia para el
parser.
"""

import os

_FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))
_PROGRAMACION_EJEMPLO_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo.txt")

with open(_PROGRAMACION_EJEMPLO_PATH, encoding="utf-8") as _f:
    FECHA14_TEXTO = _f.read()
