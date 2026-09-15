"""
Pruebas de regresión del bloque 3: integridad de datos y seguridad.

Cubren hallazgos reales que estaban en el código:

* **C3**: la paginación trataba `skip` como número de página, así que solo
  existía la primera página; y el orden por `created_at` (que empata al segundo)
  no tenía desempate, con lo que las páginas podían repetir o saltarse filas.
* **C4**: `/predictions/stats/me` mostraba los barrios y precios de otros usuarios.
* **C5**: las contraseñas viajaban en el query string.
* **C6**: `change-password` no aplicaba la política de contraseñas (aceptaba "1").
* **C7**: se podía escalar a administrador desde el registro y desde el propio
  perfil, porque `role` estaba en los esquemas de entrada.
"""

import pytest

from api.auth import create_access_token
from api.crud import CRUDUser, CRUDProduct
from api.models import UserRole
from api.schemas import UserCreate, ProductCreate

PASSWORD = 'Test123!@#'


# ============================================================
# Utilidades
# ============================================================

def _registrar_y_loguear(client, email, username, password=PASSWORD):
    client.post('/api/auth/register', json={
        'email': email, 'username': username, 'password': password,
        'first_name': 'Test', 'last_name': 'User'})
    r = client.post('/api/auth/login', data={'username': email, 'password': password})
    return {'Authorization': f"Bearer {r.json()['access_token']}"}


def _crear_admin(db_session, email='admin@example.com'):
    """Crea un administrador directamente en la BD y devuelve sus cabeceras."""
    user = CRUDUser.create(db_session, UserCreate(
        email=email, username=email.split('@')[0], password=PASSWORD,
        first_name='Ad', last_name='Min'))
    user.role = UserRole.ADMIN
    db_session.commit()
    token = create_access_token({
        'sub': str(user.id), 'email': user.email,
        'role': user.role.value, 'user_id': user.id})
    return {'Authorization': f'Bearer {token}'}, user


def _vivienda(**extra):
    base = {
        'neighborhood': 'NAmes', 'ms_subclass': 20,
        'gr_liv_area_m2': 136.0, 'lot_area_m2': 880.0,
        'overall_qual': 6, 'year_built': 1973,
        'bedrooms': 3, 'bathrooms': 2, 'garage_cars': 2,
    }
    base.update(extra)
    return base


# ============================================================
# C3 · PAGINACIÓN Y ORDEN ESTABLE
# ============================================================

class TestPaginacion:
    """La paginación por offset debe recorrer todas las filas sin repetir ni saltar."""

    def test_apply_pagination_usa_skip_como_offset(self):
        """
        Regresión directa: la firma era (query, page, page_size) pero se le
        pasaba (skip, limit), con lo que skip=10 daba offset 90.
        """
        from api.crud import apply_pagination
        from api.database import SessionLocal
        from api import models

        db = SessionLocal()
        try:
            q = apply_pagination(db.query(models.Prediction), 20, 10)
            sql = str(q.statement.compile(compile_kwargs={'literal_binds': True}))
            assert 'OFFSET 20' in sql.upper().replace('\n', ' '), sql
        finally:
            db.close()

    def test_las_paginas_recorren_todas_las_filas(self, client):
        H = _registrar_y_loguear(client, 'pag@example.com', 'paguser')

        for _ in range(25):
            assert client.post('/api/predictions/', headers=H, json=_vivienda()).status_code == 201

        # Se recorre el historial página a página y se comprueba que el
        # resultado es exactamente el mismo que pedir todo de una vez.
        todas = client.get('/api/predictions/history?skip=0&limit=50', headers=H).json()
        ids_completos = [x['id'] for x in todas['items']]
        assert len(ids_completos) == 25

        recogidos = []
        for skip in (0, 10, 20):
            r = client.get(f'/api/predictions/history?skip={skip}&limit=10', headers=H).json()
            pagina = [x['id'] for x in r['items']]
            assert len(pagina) == 10 or skip == 20, f'skip={skip} devolvió {len(pagina)}'
            recogidos.extend(pagina)

        assert recogidos == ids_completos, 'las páginas no cubren el historial en orden'
        assert len(set(recogidos)) == 25, 'hay filas repetidas entre páginas'

    def test_el_orden_es_estable_entre_peticiones(self, client):
        """`created_at` empata al segundo: sin desempate el orden sería arbitrario."""
        H = _registrar_y_loguear(client, 'ord@example.com', 'orduser')
        for _ in range(12):
            client.post('/api/predictions/', headers=H, json=_vivienda())

        ordenes = set()
        for _ in range(5):
            r = client.get('/api/predictions/history?skip=0&limit=12', headers=H).json()
            ordenes.add(tuple(x['id'] for x in r['items']))

        assert len(ordenes) == 1, f'el orden cambió entre peticiones: {ordenes}'

        # Y además debe ser descendente por id (lo más reciente primero)
        unico = ordenes.pop()
        assert list(unico) == sorted(unico, reverse=True)

    def test_paginacion_de_productos(self, client, db_session, test_user):
        for i in range(7):
            CRUDProduct.create(db_session, ProductCreate(
                name=f'Producto {i}', price=100 + i, stock=1, owner_id=test_user.id))
        db_session.commit()

        p1 = client.get('/api/products/?skip=0&limit=3').json()
        p2 = client.get('/api/products/?skip=3&limit=3').json()
        p3 = client.get('/api/products/?skip=6&limit=3').json()

        assert len(p1) == 3 and len(p2) == 3 and len(p3) == 1
        ids = [p['id'] for p in p1] + [p['id'] for p in p2] + [p['id'] for p in p3]
        assert len(set(ids)) == 7, 'la paginación de productos repite o pierde filas'


# ============================================================
# C4 · AISLAMIENTO DE ESTADÍSTICAS
# ============================================================

class TestAislamientoDeEstadisticas:
    def test_stats_me_no_muestra_datos_de_otros(self, client):
        """Regresión: los desgloses no filtraban por usuario."""
        H_a = _registrar_y_loguear(client, 'a4@example.com', 'userA4')
        H_b = _registrar_y_loguear(client, 'b4@example.com', 'userB4')

        client.post('/api/predictions/', headers=H_a, json=_vivienda(neighborhood='NAmes'))
        client.post('/api/predictions/', headers=H_b, json=_vivienda(neighborhood='MeadowV'))

        stats = client.get('/api/predictions/stats/me', headers=H_a).json()
        barrios = [b['neighborhood'] for b in stats['top_neighborhoods']]

        assert stats['total_predictions'] == 1
        assert 'MeadowV' not in barrios, f'fuga de datos entre usuarios: {barrios}'
        assert barrios == ['NAmes']

    def test_stats_globales_solo_para_admin(self, client, db_session):
        H_user = _registrar_y_loguear(client, 'u4@example.com', 'userU4')
        assert client.get('/api/predictions/admin/stats', headers=H_user).status_code == 403

        H_admin, _ = _crear_admin(db_session)
        assert client.get('/api/predictions/admin/stats', headers=H_admin).status_code == 200


# ============================================================
# C7 · NO SE PUEDE ESCALAR PRIVILEGIOS
# ============================================================

class TestEscaladaDePrivilegios:
    def test_el_registro_publico_ignora_el_role(self, client):
        """Regresión: `UserCreate` heredaba `role` de `UserBase`, así que un
        visitante anónimo podía registrarse directamente como admin."""
        r = client.post('/api/auth/register', json={
            'email': 'lobo@example.com', 'username': 'lobo', 'password': PASSWORD,
            'first_name': 'L', 'last_name': 'O', 'role': 'admin'})

        assert r.status_code == 201
        assert r.json()['role'] == 'user', 'el registro público concedió role=admin'

        tok = client.post('/api/auth/login', data={
            'username': 'lobo@example.com', 'password': PASSWORD}).json()['access_token']
        H = {'Authorization': f'Bearer {tok}'}
        assert client.get('/api/predictions/admin/stats', headers=H).status_code == 403

    def test_el_perfil_propio_no_permite_cambiar_el_role(self, client):
        """Regresión: `PUT /auth/me` usaba `UserCreate`, que incluía `role`."""
        H = _registrar_y_loguear(client, 'esc@example.com', 'escuser')

        r = client.put('/api/auth/me', headers=H, json={'role': 'admin'})
        assert client.get('/api/auth/me', headers=H).json()['role'] == 'user'
        # El campo ni siquiera se acepta: se ignora (no está en el esquema)
        assert r.status_code == 200

        assert client.get('/api/predictions/admin/stats', headers=H).status_code == 403

    def test_users_me_tampoco_permite_cambiar_el_role(self, client):
        H = _registrar_y_loguear(client, 'esc2@example.com', 'escuser2')

        client.put('/api/users/me', headers=H, json={'role': 'admin'})
        assert client.get('/api/auth/me', headers=H).json()['role'] == 'user'
        assert client.get('/api/predictions/admin/stats', headers=H).status_code == 403

    def test_un_admin_si_puede_cambiar_roles(self, client, db_session):
        """La restricción es solo para el propio usuario, no para los admin."""
        H_admin, _ = _crear_admin(db_session, 'admin5@example.com')
        H_user = _registrar_y_loguear(client, 'objetivo@example.com', 'objetivo')

        objetivo_id = client.get('/api/auth/me', headers=H_user).json()['id']
        r = client.patch(f'/api/users/{objetivo_id}/role?role=moderator', headers=H_admin)
        assert r.status_code == 200, r.text
        assert r.json()['role'] == 'moderator'

    def test_el_perfil_propio_permite_cambiar_solo_el_nombre(self, client):
        """Regresión: había que reenviar email, username y contraseña completos."""
        H = _registrar_y_loguear(client, 'perfil@example.com', 'perfiluser')

        r = client.put('/api/auth/me', headers=H, json={'first_name': 'Nuevo'})
        assert r.status_code == 200, r.text
        assert r.json()['first_name'] == 'Nuevo'
        assert r.json()['email'] == 'perfil@example.com'

    def test_el_perfil_propio_comprueba_username_unico(self, client):
        _registrar_y_loguear(client, 'ocupado@example.com', 'ocupado')
        H = _registrar_y_loguear(client, 'yo@example.com', 'youser')

        r = client.put('/api/auth/me', headers=H, json={'username': 'ocupado'})
        assert r.status_code == 400
        assert 'uso' in r.text.lower() or 'username' in r.text.lower()


# ============================================================
# C5 · LAS CONTRASEÑAS NO VIAJAN EN LA URL
# ============================================================

class TestContrasenasEnElCuerpo:
    def test_change_password_rechaza_credenciales_en_query_string(self, client):
        H = _registrar_y_loguear(client, 'qs@example.com', 'qsuser')

        # Antes esto funcionaba: la contraseña quedaba en el log de accesos.
        r = client.post(
            f'/api/auth/change-password?old_password={PASSWORD}&new_password=Nueva123!@#',
            headers=H)
        assert r.status_code == 422, 'sigue aceptando credenciales por query string'

        # Por el cuerpo sí funciona
        r = client.post('/api/auth/change-password', headers=H,
                        json={'old_password': PASSWORD, 'new_password': 'Nueva123!@#'})
        assert r.status_code == 200, r.text

    def test_reset_password_rechaza_credenciales_en_query_string(self, client):
        r = client.post('/api/auth/reset-password?token=falso&new_password=Nueva123!@#')
        assert r.status_code == 422

    def test_request_reset_rechaza_email_en_query_string(self, client):
        r = client.post('/api/auth/request-password-reset?email=x@example.com')
        assert r.status_code == 422

    def test_un_solo_camino_funciona_por_cuerpo(self, client):
        """El flujo completo de reseteo, sin SMTP, en desarrollo."""
        _registrar_y_loguear(client, 'reset@example.com', 'resetuser')

        r = client.post('/api/auth/request-password-reset', json={'email': 'reset@example.com'})
        assert r.status_code == 200, r.text
        token = r.json().get('data', {}).get('reset_token')
        assert token, 'en desarrollo debe devolverse el token para poder probar el flujo'

        r = client.post('/api/auth/reset-password',
                        json={'token': token, 'new_password': 'Recuperada123!@#'})
        assert r.status_code == 200, r.text

        r = client.post('/api/auth/login', data={
            'username': 'reset@example.com', 'password': 'Recuperada123!@#'})
        assert r.status_code == 200


# ============================================================
# C6 · POLÍTICA DE CONTRASEÑAS EN TODOS LOS CAMINOS
# ============================================================

class TestPoliticaDeContrasenas:
    @pytest.mark.parametrize('debil, motivo', [
        ('1', 'longitud'),
        ('corta1!', 'longitud'),
        ('sinmayusculas1!', 'mayúscula'),
        ('SINMINUSCULAS1!', 'minúscula'),
        ('SinNumeros!!', 'número'),
        ('SinEspecial123', 'especial'),
    ])
    def test_change_password_rechaza_contrasenas_debiles(self, client, debil, motivo):
        """Regresión: `change-password` aceptaba "1" y el login con "1" funcionaba."""
        H = _registrar_y_loguear(client, 'debil@example.com', 'debiluser')

        r = client.post('/api/auth/change-password', headers=H,
                        json={'old_password': PASSWORD, 'new_password': debil})
        assert r.status_code == 422, f'aceptó una contraseña sin {motivo}: {debil!r}'

        # y la contraseña original sigue funcionando
        assert client.post('/api/auth/login', data={
            'username': 'debil@example.com', 'password': PASSWORD}).status_code == 200

    def test_registro_aplica_la_misma_politica(self, client):
        r = client.post('/api/auth/register', json={
            'email': 'flojo@example.com', 'username': 'flojo',
            'password': 'sinEspecial1'})
        assert r.status_code == 422

    def test_la_politica_es_una_sola_funcion(self):
        """La definición vive en un único sitio y auth delega en ella."""
        from api.schemas import validar_fortaleza_password
        from api.auth import validate_password_strength

        for buena in ('Test123!@#', 'Otra456$%'):
            assert validar_fortaleza_password(buena) == buena
            assert validate_password_strength(buena) is True

        for mala in ('1', 'sinmayusculas1!', 'SINMINUSCULAS1!', 'SinNumero!', 'SinEspecial1'):
            with pytest.raises(ValueError):
                validar_fortaleza_password(mala)
            assert validate_password_strength(mala) is False
