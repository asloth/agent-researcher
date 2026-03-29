import sys
import os

# Agregamos la ruta base para poder importar herramientas del cliente si fuera necesario
sys.path.append(os.path.dirname(__file__))

# Herramientas estrictamente locales
def calculadora_sumar(a: float, b: float) -> float:
    """Suma dos números."""
    return a + b

def calculadora_restar(a: float, b: float) -> float:
    """Resta el número B al número A."""
    return a - b

local_tools = [calculadora_sumar, calculadora_restar]
