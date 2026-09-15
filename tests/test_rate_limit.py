"""
Pruebas del límite de peticiones (C10).

La configuración declaraba `RATE_LIMIT_ENABLED=True` desde el principio, pero no
había ninguna implementación: la aplicación no limitaba nada. Estas pruebas
comprueban que el limitador funciona y que no estorba en el resto de rutas.
"""

import pytest

from api.rate_limit import LimitadorEnMemoria, ruta_limitada


# ============================================================
# Unitarias del limitador
# ============================================================

class TestLimitadorEnMemoria:

    def test_permite_hasta_el_limite_y_luego_bloquea(self):
        limitador = LimitadorEnMemoria(max_peticiones=3, periodo=60)

        assert [limitador.permitir('ip|ruta')[0] for _ in range(3)] == [True] * 3

        permitido, espera = limitador.permitir('ip|ruta')
        assert permitido is False
        assert espera >= 1, 'debe indicar cuántos segundos esperar'

    def test_la_ventana_se_desliza(self):
        """Pasado el periodo, vuelve a permitir."""
        limitador = LimitadorEnMemoria(max_peticiones=1, periodo=1)

        assert limitador.permitir('ip|ruta')[0] is True
        assert limitador.permitir('ip|ruta')[0] is False

        import time
        time.sleep(1.1)

        assert limitador.permitir('ip|ruta')[0] is True

    def test_las_claves_son_independientes(self):
        """El límite es por IP y ruta: una IP no consume el cupo de otra."""
        limitador = LimitadorEnMemoria(max_peticiones=2, periodo=60)

        assert limitador.permitir('ip1|/api/auth/login')[0] is True
        assert limitador.permitir('ip1|/api/auth/login')[0] is True
        assert limitador.permitir('ip1|/api/auth/login')[0] is False

        # Otra IP sí puede
        assert limitador.permitir('ip2|/api/auth/login')[0] is True
        # Y la misma IP en otra ruta también
        assert limitador.permitir('ip1|/api/predictions/')[0] is True

    def test_reiniciar(self):
        limitador = LimitadorEnMemoria(max_peticiones=1, periodo=60)
        limitador.permitir('ip|ruta')
        assert limitador.permitir('ip|ruta')[0] is False
        limitador.reiniciar()
        assert limitador.permitir('ip|ruta')[0] is True

    def test_valores_invalidos(self):
        with pytest.raises(ValueError):
            LimitadorEnMemoria(max_peticiones=0, periodo=60)
        with pytest.raises(ValueError):
            LimitadorEnMemoria(max_peticiones=10, periodo=0)


class TestRutasLimitadas:

    @pytest.mark.parametrize('metodo,ruta', [
        ('POST', '/api/auth/login'),
        ('POST', '/api/auth/register'),
        ('POST', '/api/auth/refresh'),
        ('POST', '/api/auth/change-password'),
        ('POST', '/api/auth/request-password-reset'),
        ('POST', '/api/auth/reset-password'),
        ('POST', '/api/predictions'),
        ('POST', '/api/predictions/'),
        ('POST', '/api/predictions/batch'),
    ])
    def test_las_rutas_sensibles_estan_limitadas(self, metodo, ruta):
        assert ruta_limitada(metodo, ruta) is not None, f'{metodo} {ruta} debería estar limitada'

    @pytest.mark.parametrize('metodo,ruta', [
        ('GET', '/health'),
        ('GET', '/'),
        ('GET', '/docs'),
        ('GET', '/api/products/'),
        ('GET', '/api/predictions/options'),   # solo lectura y público
        ('GET', '/api/predictions/history'),   # solo lectura, lo usa el dashboard
        ('GET', '/api/predictions/stats/me'),
        ('DELETE', '/api/predictions/1'),
    ])
    def test_las_rutas_normales_no_estan_limitadas(self, metodo, ruta):
        assert ruta_limitada(metodo, ruta) is None, f'{metodo} {ruta} no debería estar limitada'

    def test_la_barra_final_no_esquiva_el_limite(self):
        """`/api/predictions` y `/api/predictions/` son la misma ruta."""
        con_barra = ruta_limitada('POST', '/api/predictions/')
        sin_barra = ruta_limitada('POST', '/api/predictions')
        assert con_barra is not None and sin_barra is not None
        assert con_barra == sin_barra


# ============================================================
# Integración con la aplicación
# ============================================================

class TestLimiteEnLaAplicacion:

    def test_la_aplicacion_devuelve_429_al_superar_el_limite(self, client):
        """
        Se sustituye el limitador del middleware por uno muy restrictivo para no
        tener que hacer 100 peticiones.
        """
        from main import app, limitador
        from api.rate_limit import RateLimitMiddleware

        if limitador is None:
            pytest.skip('El límite de peticiones está desactivado en este entorno')

        estado_original = (limitador.max_peticiones, limitador.periodo)
        limitador.max_peticiones = 2
        limitador.periodo = 60
        limitador.reiniciar()
        try:
            codigos = [
                client.post('/api/auth/login',
                            data={'username': 'x@example.com', 'password': 'loquesea'}).status_code
                for _ in range(4)
            ]
            assert codigos[:2] == [401, 401], codigos
            assert codigos[2] == 429, f'no se aplicó el límite: {codigos}'

            # La respuesta debe decir cuánto esperar
            respuesta = client.post('/api/auth/login',
                                    data={'username': 'x@example.com', 'password': 'loquesea'})
            assert respuesta.status_code == 429
            assert 'Retry-After' in respuesta.headers
            assert int(respuesta.headers['Retry-After']) >= 1
        finally:
            limitador.max_peticiones, limitador.periodo = estado_original
            limitador.reiniciar()

    def test_las_rutas_normales_no_se_ven_afectadas(self, client):
        """Aunque el limitador esté al mínimo, /health y las opciones funcionan."""
        from main import limitador

        if limitador is None:
            pytest.skip('El límite de peticiones está desactivado en este entorno')

        estado_original = (limitador.max_peticiones, limitador.periodo)
        limitador.max_peticiones = 1
        limitador.periodo = 60
        limitador.reiniciar()
        try:
            for _ in range(5):
                assert client.get('/health').status_code == 200
            for _ in range(5):
                assert client.get('/api/predictions/options').status_code == 200
        finally:
            limitador.max_peticiones, limitador.periodo = estado_original
            limitador.reiniciar()
