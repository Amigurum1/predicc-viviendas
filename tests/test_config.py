"""
Pruebas para el módulo de configuración
"""

import pytest
import os
from api.config import config

def test_config_loaded():
    """Verificar que la configuración se carga correctamente"""
    assert config.APP_NAME is not None
    assert config.APP_VERSION is not None

def test_config_environment():
    """Verificar que el entorno está configurado"""
    assert config.ENVIRONMENT in ["development", "testing", "production"]

def test_config_database_url():
    """Verificar que la URL de base de datos es válida"""
    db_url = config.get_database_url()
    assert db_url is not None
    assert isinstance(db_url, str)

def test_config_secret_key_siempre_comprobada(monkeypatch):
    """
    La SECRET_KEY se valida en TODOS los entornos, no solo en producción.

    Regresión: la comprobación solo miraba el valor de ejemplo
    'your-secret-key-here', así que la clave real del proyecto
    ('mi-clave-super-secreta-para-docker-2024', 39 caracteres) pasaba el filtro
    de longitud y no se detectaba nunca.

    La prueba NO lee la SECRET_KEY real: en un clon recién hecho no hay `.env`
    y rige el valor por defecto, que es débil, así que mirar el entorno daba un
    fallo falso según la máquina. Aquí se fijan las claves a mano.
    """
    from api.config import Config

    # La clave que provocó la regresión: es larga, así que el filtro de
    # longitud por sí solo no la detectaba.
    debil_larga = 'mi-clave-super-secreta-para-docker-2024'
    assert len(debil_larga) >= Config.LONGITUD_MINIMA_SECRET_KEY
    assert debil_larga in Config.SECRETOS_DEBILES

    # Una clave de valor por defecto tampoco pasa el mínimo de longitud
    assert len('your-secret-key-here') < Config.LONGITUD_MINIMA_SECRET_KEY

    # Sin ser producción (estricto=False) sigue siendo un problema: se avisa
    monkeypatch.setattr(Config, 'SECRET_KEY', debil_larga)
    assert Config.validate_config(estricto=False) is False

    # En modo estricto impide el arranque
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        Config.validate_config(estricto=True)

    # Demasiado corta: también es un problema
    monkeypatch.setattr(Config, 'SECRET_KEY', 'corta')
    with pytest.raises(RuntimeError, match='demasiado corta'):
        Config.validate_config(estricto=True)

    # La longitud mínima exacta (y no listada) sí es válida
    monkeypatch.setattr(Config, 'SECRET_KEY', 'x' * Config.LONGITUD_MINIMA_SECRET_KEY)
    assert Config.validate_config(estricto=True) is True


def test_config_rechaza_secretos_debiles():
    """El validador debe detectar los secretos de ejemplo como fatales."""
    from api.config import Config

    for debil in ('your-secret-key-here', 'mi-clave-super-secreta-para-docker-2024'):
        assert debil in Config.SECRETOS_DEBILES

    # En modo estricto, una clave débil debe impedir el arranque
    original = Config.SECRET_KEY
    try:
        Config.SECRET_KEY = 'your-secret-key-here'
        with pytest.raises(RuntimeError, match='SECRET_KEY'):
            Config.validate_config(estricto=True)
    finally:
        Config.SECRET_KEY = original


def test_config_ya_no_tiene_configuracion_muerta():
    """
    Redis, SMTP, OpenAI, AWS, Sentry y la subida de archivos se han retirado: eran
    configuración declarada que ningún código usaba.
    """
    for atributo in ('REDIS_URL', 'SMTP_HOST', 'OPENAI_API_KEY',
                     'AWS_ACCESS_KEY_ID', 'SENTRY_DSN',
                     'UPLOAD_DIR', 'MAX_UPLOAD_SIZE', 'ALLOWED_EXTENSIONS'):
        assert not hasattr(config, atributo), f'{atributo} sigue en la configuración'

    # El ayudante que dependía de esa configuración tampoco debe existir
    assert not hasattr(config, 'get_allowed_extensions')

def test_config_cors_origins():
    """Verificar que los orígenes CORS están configurados correctamente"""
    origins = config.get_cors_origins()
    assert isinstance(origins, list)
    if config.is_production():
        assert "*" not in origins

def test_config_rate_limit():
    """Verificar configuración de rate limiting"""
    assert config.RATE_LIMIT_REQUESTS > 0
    assert config.RATE_LIMIT_PERIOD > 0

def test_config_pagination():
    """Verificar configuración de paginación"""
    assert config.DEFAULT_PAGE_SIZE > 0
    assert config.MAX_PAGE_SIZE > config.DEFAULT_PAGE_SIZE