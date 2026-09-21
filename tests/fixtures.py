"""
Fixtures compartidas por los tests.

FECHA14_TEXTO es un texto de ejemplo con el mismo formato que un PDF real
de programación de ABSS *hasta la jornada 21* (mismos encabezados, columnas
y estructura de bloques por gimnasio/fecha), pero con equipos, árbitros,
gimnasios y direcciones ficticios.

FECHA22_TEXTO representaba lo que se pensó inicialmente que era el formato
nuevo (jornada 22 en adelante): equipos separados por "VS", una sola columna
por página. Se mantiene como caso de prueba (formato "VS" + gimnasio con
dirección inline, ambos tolerados por el parser), pero **no refleja el PDF
real**: ver FECHA22_V3_TEXTO.

FECHA22_V3_TEXTO sí refleja el formato real de ABSS a partir de jornada 22:
la página viene en grilla de dos columnas (dos gimnasios/partidos por fila
física, que al extraer el texto quedan concatenados en una misma línea), el
nombre del gimnasio va como "▣ GIMNASIO X Árbitros:" y su dirección en una
línea aparte con "●" (que solo se repite la primera vez que aparece ese
gimnasio), sin "VS" entre equipos, y el título/fecha vienen con cada
carácter duplicado o triplicado (falsa negrita del PDF).

Todos se usan como casos de prueba de referencia para el parser.
"""

import os

_FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))
_PROGRAMACION_EJEMPLO_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo.txt")
_PROGRAMACION_EJEMPLO_V2_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo_v2.txt")
_PROGRAMACION_EJEMPLO_V3_PATH = os.path.join(_FIXTURES_DIR, "data", "programacion_ejemplo_v3.txt")

with open(_PROGRAMACION_EJEMPLO_PATH, encoding="utf-8") as _f:
    FECHA14_TEXTO = _f.read()

with open(_PROGRAMACION_EJEMPLO_V2_PATH, encoding="utf-8") as _f:
    FECHA22_TEXTO = _f.read()

with open(_PROGRAMACION_EJEMPLO_V3_PATH, encoding="utf-8") as _f:
    FECHA22_V3_TEXTO = _f.read()
