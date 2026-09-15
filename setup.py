"""
Metadatos del paquete.

Nota: este proyecto se usa como aplicación (se arranca con uvicorn o Docker), no
como librería instalable, así que el empaquetado es informativo. Aun así, los
metadatos estaban mal y conviene que sean ciertos:

* `python_requires=">=3.8"` era falso: las dependencias fijadas en
  requirements.txt (numpy 1.26.4, scikit-learn 1.5.0, pandas 2.2.2) NO soportan
  Python 3.8. El proyecto está probado con 3.12.
* `find_packages()` incluía `tests` en el paquete distribuido.
* Faltaba `install_requires`, así que instalar el paquete no traía nada.
"""

from pathlib import Path

from setuptools import find_packages, setup

RAIZ = Path(__file__).parent


def _dependencias_de_runtime():
    """
    Lee las dependencias de requirements.txt.

    Se lee el fichero en vez de repetir la lista para que no puedan divergir: si
    se añade una dependencia, basta con hacerlo en un sitio.
    """
    lineas = (RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    return [
        linea.strip()
        for linea in lineas
        if linea.strip() and not linea.strip().startswith('#')
    ]


setup(
    name='predicc_viviendas',
    version='1.0.0',
    description=(
        'Predictor de precios de viviendas con Machine Learning (Ames Housing): '
        'API REST con FastAPI, autenticación JWT e interfaz web.'
    ),
    # `tests` no forma parte del paquete distribuido
    packages=find_packages(exclude=('tests', 'tests.*', 'notebooks', 'scripts')),
    python_requires='>=3.12',
    install_requires=_dependencias_de_runtime(),
)
