"""
Límite de peticiones en memoria.

POR QUÉ EXISTE
--------------
La configuración declaraba `RATE_LIMIT_ENABLED=True` desde el principio, pero no
había ninguna implementación: la aplicación no limitaba nada y el ajuste era
una promesa vacía. Esto lo cumple.

ALCANCE Y LIMITACIONES (importantes)
------------------------------------
Es un limitador **por proceso y en memoria**:

* Con varios workers de uvicorn, cada uno lleva su propia cuenta, así que el
  límite efectivo se multiplica por el número de workers.
* No sirve para un despliegue con varias instancias.

Para eso haría falta un almacén compartido (Redis). El proyecto ya tenía
configuración de Redis y se ha retirado por no usarse; si algún día se despliega
en serio, este es el sitio donde debería entrar.

La IP del cliente se toma de `request.client.host`. Detrás de un proxy inverso
eso sería la IP del proxy; usar `X-Forwarded-For` sin validarlo permitiría
falsear el límite, así que no se hace: si se despliega detrás de un proxy de
confianza, hay que configurarlo explícitamente.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Rutas sujetas a límite: las sensibles a fuerza bruta y las caras de calcular.
#
# Se limita por MÉTODO y ruta, no por prefijo. Un prefijo como
# '/api/predictions/' limitaría también `/options` y `/history`, que son de solo
# lectura y los consume el propio frontend al cargar el dashboard; limitarlos
# provocaría errores 429 en uso normal.
RUTAS_LIMITADAS = (
    # Autenticación: protege contra fuerza bruta
    ('POST', '/api/auth/login'),
    ('POST', '/api/auth/register'),
    ('POST', '/api/auth/refresh'),
    ('POST', '/api/auth/change-password'),
    ('POST', '/api/auth/request-password-reset'),
    ('POST', '/api/auth/reset-password'),
    # Predicción: cada llamada ejecuta 200 árboles
    ('POST', '/api/predictions'),
    ('POST', '/api/predictions/batch'),
)

# Las mismas rutas normalizadas (sin barra final) para comparar de forma robusta
# y que `/api/predictions` y `/api/predictions/` cuenten como la misma.
_RUTAS_NORMALIZADAS = frozenset(
    (metodo, ruta.rstrip('/') or '/') for metodo, ruta in RUTAS_LIMITADAS
)

# Número máximo de claves (IP + ruta) que se recuerdan. Evita que un ataque con
# muchísimas IPs distintas haga crecer el diccionario sin control.
MAX_CLAVES = 10_000


class LimitadorEnMemoria:
    """
    Ventana deslizante por clave.

    Guarda las marcas de tiempo de las peticiones recientes de cada clave y
    rechaza las que superan `max_peticiones` dentro de `periodo` segundos.
    """

    def __init__(self, max_peticiones: int, periodo: int, max_claves: int = MAX_CLAVES):
        if max_peticiones < 1:
            raise ValueError('max_peticiones debe ser >= 1')
        if periodo < 1:
            raise ValueError('periodo debe ser >= 1 segundo')

        self.max_peticiones = max_peticiones
        self.periodo = periodo
        self.max_claves = max_claves

        self._registros: Dict[str, Deque[float]] = defaultdict(deque)
        # Los endpoints de FastAPI son síncronos y pueden atender peticiones en
        # hilos distintos, así que el estado compartido necesita un cerrojo.
        self._cerrojo = threading.Lock()

    def permitir(self, clave: str) -> Tuple[bool, int]:
        """
        Registra una petición y decide si se permite.

        Returns:
            (permitido, segundos_de_espera). Si se permite, la espera es 0.
        """
        ahora = time.monotonic()
        limite_inferior = ahora - self.periodo

        with self._cerrojo:
            marcas = self._registros[clave]

            # Descartar las peticiones que ya están fuera de la ventana
            while marcas and marcas[0] <= limite_inferior:
                marcas.popleft()

            if len(marcas) >= self.max_peticiones:
                espera = max(1, int(marcas[0] + self.periodo - ahora) + 1)
                return False, espera

            marcas.append(ahora)
            self._limpiar_si_procede(ahora)
            return True, 0

    def _limpiar_si_procede(self, ahora: float) -> None:
        """Elimina las claves inactivas si el diccionario se ha hecho grande."""
        if len(self._registros) <= self.max_claves:
            return
        limite_inferior = ahora - self.periodo
        inactivas = [c for c, m in self._registros.items() if not m or m[-1] <= limite_inferior]
        for clave in inactivas:
            del self._registros[clave]
        if len(self._registros) > self.max_claves:
            logger.warning(
                '⚠️ El limitador de peticiones tiene %d claves activas; considera '
                'usar un almacén compartido (Redis)',
                len(self._registros),
            )

    def reiniciar(self) -> None:
        """Vacía el estado (para las pruebas)."""
        with self._cerrojo:
            self._registros.clear()


def ruta_limitada(metodo: str, path: str) -> Optional[str]:
    """
    Devuelve la clave de ruta si esa petición está sujeta a límite.

    Se normaliza la barra final para que `/api/predictions` y
    `/api/predictions/` no se puedan usar para esquivar el límite.

    Args:
        metodo: método HTTP (POST, GET...).
        path: camino de la petición.

    Returns:
        La clave de agrupación (`METODO ruta`) o None si no está limitada.
    """
    normalizado = path.rstrip('/') or '/'
    metodo_normalizado = (metodo or '').upper()

    if (metodo_normalizado, normalizado) in _RUTAS_NORMALIZADAS:
        return f'{metodo_normalizado} {normalizado}'
    return None


def _cliente(request: Request) -> str:
    """Identificador del cliente para agrupar peticiones."""
    if request.client and request.client.host:
        return request.client.host
    return 'desconocido'


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware que aplica el limitador a las rutas sensibles.

    Devuelve 429 con `Retry-After` cuando se supera el límite.
    """

    def __init__(self, app, limitador: LimitadorEnMemoria):
        super().__init__(app)
        self.limitador = limitador

    async def dispatch(self, request: Request, call_next):
        ruta = ruta_limitada(request.method, request.url.path)

        if ruta is None:
            return await call_next(request)

        permitido, espera = self.limitador.permitir(f'{_cliente(request)}|{ruta}')

        if not permitido:
            logger.warning(
                '🚫 Límite de peticiones superado: %s %s desde %s (%d/%ds)',
                request.method, request.url.path, _cliente(request),
                self.limitador.max_peticiones, self.limitador.periodo,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    'detail': (
                        'Demasiadas peticiones. Espera unos segundos e inténtalo '
                        'de nuevo.'
                    ),
                    'message': 'Límite de peticiones superado',
                    'retry_after': espera,
                },
                headers={'Retry-After': str(espera)},
            )

        return await call_next(request)
