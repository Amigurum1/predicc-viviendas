"""
Comprobaciones de coherencia del frontend.

No sustituyen a una prueba en navegador, pero detectan la clase de fallo que se
coló en este proyecto: JavaScript que busca un elemento que no existe en el HTML
(`#prediction-section`) y campos antiguos que se quedan por ahí tras un cambio de
contrato (los distritos de Lima, `square_meters`, la moneda en soles).
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
HTML = FRONTEND / 'index.html'
FICHEROS_JS = ('script.js', 'dashboard.js', 'map.js')

# Los 9 campos del formulario, que deben existir en el HTML y en el payload
CAMPOS_DEL_FORMULARIO = (
    'neighborhood', 'ms_subclass', 'gr_liv_area_m2', 'lot_area_m2',
    'overall_qual', 'year_built', 'bedrooms', 'bathrooms', 'garage_cars',
)


@pytest.fixture(scope='module')
def html():
    return HTML.read_text(encoding='utf-8')


def _js(nombre):
    return (FRONTEND / nombre).read_text(encoding='utf-8')


def test_el_frontend_existe():
    assert HTML.exists(), 'no se encuentra frontend/index.html'
    for nombre in FICHEROS_JS:
        assert (FRONTEND / nombre).exists(), f'falta frontend/{nombre}'


def test_los_ids_que_usa_el_js_existen_en_el_html(html):
    """
    Regresión: `script.js` buscaba `#prediction-section`, que no existe.
    """
    ids_html = set(re.findall(r'id="([^"]+)"', html))
    faltantes = []

    for nombre in FICHEROS_JS:
        referenciados = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", _js(nombre)))
        faltantes += [(nombre, i) for i in sorted(referenciados) if i not in ids_html]

    assert not faltantes, f'IDs que el JS busca y no existen en el HTML: {faltantes}'


def test_el_formulario_tiene_los_nueve_campos(html):
    for campo in CAMPOS_DEL_FORMULARIO:
        assert f'id="{campo}"' in html, f'falta el campo {campo} en el formulario'


def test_el_formulario_ya_no_tiene_los_campos_antiguos(html):
    """Los campos del contrato antiguo (Lima, m² sueltos, checkbox) no deben volver."""
    for viejo in ('square_meters', 'years_old', 'distance_to_center',
                  'has_parking', 'has_garden', 'has_pool', 'property_type'):
        assert f'id="{viejo}"' not in html, f'{viejo} sigue en el formulario'


def test_la_moneda_es_dolares(html):
    """El modelo es de Ames (EE. UU.): mostrar soles sería una etiqueta falsa."""
    assert 'S/ ' not in html, 'queda algún precio etiquetado en soles en el HTML'
    for nombre in FICHEROS_JS:
        assert 'S/ ' not in _js(nombre), f'queda algún precio en soles en {nombre}'


def test_no_quedan_referencias_a_distritos_de_lima(html):
    for distrito in ('Miraflores', 'San Isidro', 'Barranco', 'La Molina'):
        assert distrito not in html, f'{distrito} sigue en la interfaz'


def test_los_ayudantes_compartidos_estan_definidos():
    """
    `dashboard.js` y `map.js` usan `formatearPrecio` y `escapeHtml`, que se
    definen en `script.js` (que se carga antes). Si desaparecen, esas llamadas
    fallan en tiempo de ejecución.
    """
    script = _js('script.js')
    for ayudante in ('formatearPrecio', 'escapeHtml', 'manejarSesionExpirada'):
        assert f'function {ayudante}' in script, f'falta la función {ayudante} en script.js'


def test_los_datos_de_la_api_se_escapan_antes_de_inyectarlos():
    """
    `district`/`neighborhood` llegan de la API y se insertan con innerHTML: hay
    que escaparlos para no permitir XSS almacenado (el token vive en
    localStorage).
    """
    script = _js('script.js')
    assert 'escapeHtml(' in script, 'no se escapa el contenido que se inyecta'

    # Las interpolaciones de barrio del historial y del resultado deben escaparse
    assert 'escapeHtml(item.neighborhood' in script
    assert 'escapeHtml(data.neighborhood' in script


def test_los_ficheros_js_estan_enlazados_en_orden(html):
    """script.js define los ayudantes que usan los otros dos: va primero."""
    orden = [m for m in re.findall(r'<script src="([^"]+)"', html) if not m.startswith('http')]
    assert orden[:3] == ['script.js', 'dashboard.js', 'map.js'], orden


def test_chart_js_local_ya_no_existe(html):
    """Era un fichero muerto que duplicaba dashboard.js y no era la librería real."""
    assert not (FRONTEND / 'chart.js').exists()
    assert not re.search(r'src=["\'](?:\./)?chart\.js["\']', html)


def test_no_hay_listeners_de_navegacion_duplicados():
    """
    Regresión: dashboard.js y map.js añadían sus propios listeners sobre las
    pestañas, además del central de script.js, así que cada sección se cargaba
    dos veces por clic.
    """
    for nombre in ('dashboard.js', 'map.js'):
        js = _js(nombre)
        assert "data-section=\"dashboard\"]')" not in js or 'addEventListener' not in js, (
            f'{nombre} vuelve a registrar un listener de navegación'
        )


# ============================================================
# F1 · Mensajes de error legibles
# ============================================================

def test_los_errores_de_la_api_se_traducen_a_mensajes_legibles():
    """
    Regresión: `new Error(error.detail)` con `detail` en forma de lista de
    objetos producía el mensaje "[object Object]". La API devuelve los errores de
    validación (422) así, uno por campo.
    """
    script = _js('script.js')

    assert 'function mensajeDeError' in script, 'falta el traductor de errores'
    assert 'new Error(error.detail' not in script, (
        'queda algún sitio que pase `detail` en crudo a un Error'
    )
    for esperado in ('Error en el login', 'Error en el registro', 'Error en la predicción'):
        assert f"mensajeDeError(error.detail, '{esperado}')" in script, (
            f'el error "{esperado}" no usa el traductor'
        )


def test_el_traductor_cubre_las_dos_formas_de_error():
    """
    Se comprueba el comportamiento real del traductor ejecutándolo con Node:
    la API devuelve `detail` como cadena (400/401) o como lista (422).
    """
    import json
    import shutil
    import subprocess

    if not shutil.which('node'):
        pytest.skip('Node.js no está disponible para ejecutar la comprobación')

    script = _js('script.js')
    # Se extraen la tabla de etiquetas y la función, que es lo que necesita Node
    inicio = script.index('const ETIQUETAS_DE_CAMPO')
    resto = script[inicio:]
    fin = resto.index('\n}\n', resto.index('function mensajeDeError')) + 3
    funcion = resto[:fin]

    casos = [
        # (entrada, esperado)
        ("'Email o contraseña incorrectos'", 'Email o contraseña incorrectos'),
        ('null', 'por defecto'),
        ('[]', 'por defecto'),
        # 422 típico de Pydantic con un validador propio
        (json.dumps([{
            'loc': ['body', 'password'],
            'msg': 'Value error, La contraseña debe tener al menos una mayúscula',
            'type': 'value_error',
        }]), 'Contraseña: La contraseña debe tener al menos una mayúscula'),
        # 422 de un campo con restricción (sin validador propio)
        (json.dumps([{
            'loc': ['body', 'overall_qual'],
            'msg': 'Input should be less than or equal to 10',
            'type': 'less_than_equal',
        }]), 'Calidad general: Input should be less than or equal to 10'),
        # Varios errores a la vez
        (json.dumps([
            {'loc': ['body', 'email'], 'msg': 'value is not a valid email address'},
            {'loc': ['body', 'username'], 'msg': 'String should have at least 3 characters'},
        ]), 'Email: value is not a valid email address · Usuario: String should have at least 3 characters'),
    ]

    programa = (
        funcion
        + '\nconst casos = ' + json.dumps(casos) + ';\n'
        + 'const salida = casos.map(([entrada, esperado]) => {\n'
        + '  const valor = eval(entrada);\n'
        + "  const obtenido = mensajeDeError(valor, 'por defecto');\n"
        + '  return { esperado, obtenido, ok: esperado === obtenido };\n'
        + '});\n'
        + 'console.log(JSON.stringify(salida));\n'
    )

    resultado = subprocess.run(
        ['node', '-e', programa], capture_output=True, encoding='utf-8', timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
    comprobaciones = json.loads(resultado.stdout)

    fallos = [c for c in comprobaciones if not c['ok']]
    assert not fallos, f'mensajes mal traducidos: {fallos}'


def test_el_error_real_del_api_se_convierte_en_un_mensaje_legible(client):
    """
    Prueba de integración del bug F1: se pide al API un error de validación de
    verdad y se pasa su respuesta por el traductor del frontend, ejecutándolo con
    Node.

    Antes, el usuario que se equivocaba con la contraseña veía literalmente
    "[object Object]", porque `detail` es una lista y se pasaba entera a
    `new Error(...)`.
    """
    import json
    import shutil
    import subprocess

    if not shutil.which('node'):
        pytest.skip('Node.js no está disponible para ejecutar la comprobación')

    # 1. Error de validación REAL del API.
    # Se usa una contraseña de 8 caracteres que cumple la longitud pero no el
    # resto de la política, para que salte el validador propio (cuyo mensaje
    # Pydantic prefija con "Value error, ", y el traductor debe limpiar).
    respuesta = client.post('/api/auth/register', json={
        'email': 'novalido@example.com', 'username': 'novalido',
        'password': 'debil123',  # sin mayúscula y sin carácter especial
    })
    assert respuesta.status_code == 422, respuesta.text
    detail = respuesta.json()['detail']
    assert isinstance(detail, list) and detail, 'el API debería devolver una lista'

    # 2. Se pasa esa respuesta real por el traductor del frontend
    script = _js('script.js')
    inicio = script.index('const ETIQUETAS_DE_CAMPO')
    resto = script[inicio:]
    fin = resto.index('\n}\n', resto.index('function mensajeDeError')) + 3
    funcion = resto[:fin]

    programa = (
        funcion
        + '\nconst detail = ' + json.dumps(detail) + ';\n'
        + "console.log(mensajeDeError(detail, 'Error en el registro'));\n"
    )
    resultado = subprocess.run(['node', '-e', programa],
                               capture_output=True, encoding='utf-8', timeout=30)
    assert resultado.returncode == 0, resultado.stderr

    mensaje = resultado.stdout.strip()
    print(f'\n  mensaje que vería el usuario: {mensaje}')
    assert mensaje, 'el traductor devolvió un mensaje vacío'
    assert '[object Object]' not in mensaje, f'sigue saliendo el mensaje ilegible: {mensaje}'
    assert 'Contraseña' in mensaje, f'debería indicar el campo: {mensaje}'
    assert 'Value error' not in mensaje, f'no debería filtrar el prefijo de Pydantic: {mensaje}'
    assert 'mayúscula' in mensaje or 'carácter especial' in mensaje, (
        f'debería explicar qué falta: {mensaje}'
    )


# ============================================================
# F2 · Navegación en móvil
# ============================================================

def test_existe_el_boton_del_menu_movil(html):
    """
    Regresión: el CSS ocultaba el sidebar por debajo de 768 px y estilaba
    `.menu-toggle`, pero ese elemento no existía en el HTML, así que en un móvil
    la aplicación se quedaba sin navegación.
    """
    assert 'class="menu-toggle"' in html, 'falta el botón del menú móvil'
    assert 'id="menu-toggle"' in html
    assert 'aria-controls="sidebar"' in html
    assert 'aria-expanded="false"' in html, 'el botón debe anunciar su estado'


def test_el_css_del_menu_movil_y_el_js_encajan(html):
    css = (FRONTEND / 'styles.css').read_text(encoding='utf-8')
    script = _js('script.js')

    # El CSS esconde el sidebar y lo muestra con .open
    assert '.sidebar.open' in css, 'el CSS no contempla el sidebar abierto'
    assert '.menu-toggle' in css

    # El JS aplica exactamente esa clase
    assert "classList.add('open')" in script
    assert "classList.remove('open')" in script
    assert 'function configurarMenuMovil' in script

    # Y se llama al inicializar
    assert 'configurarMenuMovil()' in script


def test_el_menu_se_puede_cerrar_de_varias_formas():
    script = _js('script.js')
    # Tocar el fondo, pulsar Escape y elegir una sección
    assert 'sidebar-backdrop' in script, 'no se cierra al tocar fuera'
    assert "'Escape'" in script, 'no se cierra con la tecla Escape'
    assert "querySelectorAll('.nav-item')" in script, 'no se cierra al elegir sección'


def test_el_fondo_del_menu_existe_y_empieza_oculto(html):
    assert 'id="sidebar-backdrop"' in html
    assert 'id="sidebar-backdrop" hidden' in html, 'el fondo debe empezar oculto'


def test_el_apilamiento_del_menu_movil_es_correcto():
    """
    Comprobación de z-index, que no se ve en el código pero rompe la interfaz:
    el fondo debe quedar POR DEBAJO del sidebar (si no, lo taparía y el menú no
    se podría pulsar) y por debajo del botón, que debe seguir accesible.

    Es el fallo que tuvo la primera versión de este cambio: el fondo tenía
    z-index 150 y el sidebar 100.
    """
    import re

    css = (FRONTEND / 'styles.css').read_text(encoding='utf-8')

    def z_index(selector):
        patron = re.escape(selector) + r'\s*\{[^}]*?z-index:\s*(\d+)'
        coincidencia = re.search(patron, css, re.S)
        assert coincidencia, f'no se encontró z-index para {selector}'
        return int(coincidencia.group(1))

    z_sidebar = z_index('.sidebar')
    z_fondo = z_index('.sidebar-backdrop')
    z_boton = z_index('.menu-toggle')

    assert z_fondo < z_sidebar, (
        f'el fondo (z-index {z_fondo}) taparía el sidebar (z-index {z_sidebar})'
    )
    assert z_sidebar < z_boton, (
        f'el botón (z-index {z_boton}) quedaría tapado por el sidebar ({z_sidebar})'
    )


# ============================================================
# Idiomas y contenido
# ============================================================

def test_los_textos_estan_en_espanol(html):
    """No deben quedar textos de plantilla en inglés en la interfaz."""
    for texto in ('Submit', 'Login', 'Sign up', 'Password', 'Username'):
        assert f'>{texto}<' not in html, f'queda el texto en inglés "{texto}"'
