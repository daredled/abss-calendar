import os
import sys

# Permite "from parse_pdf import ..." etc. (módulos en src/) y
# "from tests.fixtures import ..." al correr los tests directamente,
# sin depender solo de la config pythonpath de pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
