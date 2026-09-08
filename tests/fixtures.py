"""
Fixtures compartidas por los tests.

FECHA14_TEXTO es un texto de ejemplo con el mismo formato que un PDF real
de programación de ABSS *hasta la jornada 21* (mismos encabezados, columnas
y estructura de bloques por gimnasio/fecha), pero con equipos, árbitros,
gimnasios y direcciones ficticios.

FECHA22_TEXTO es lo mismo para el formato nuevo (jornada 22 en adelante):
equipos separados por "VS", árbitros en su propia línea y sin id de partido
ni cancha en la fila.

Ambos se usan como casos de prueba de referencia para el parser.
"""

import os

_FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))
_PROGRAMACION_EJEMPLO_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo.txt")
_PROGRAMACION_EJEMPLO_V2_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo_v2.txt")

with open(_PROGRAMACION_EJEMPLO_PATH, encoding="utf-8") as _f:
    FECHA14_TEXTO = _f.read()

with open(_PROGRAMACION_EJEMPLO_V2_PATH, encoding="utf-8") as _f:
    FECHA22_TEXTO = _f.read()
