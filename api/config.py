"""
Archivo de configuración para la API
Maneja diferentes entornos (desarrollo, pruebas, producción)
Carga variables de entorno y define configuraciones por defecto
"""

import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, Dict, Any
import logging

# Cargar variables de entorno desde el archivo .env
# Busca .env en el directorio raíz del proyecto
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    """
    Configuración base para la aplicación
    """
    # Configuración general de la aplicación
    APP_NAME: str = os.getenv('APP_NAME', 'Mi API')
    APP_VERSION: str = os.getenv('APP_VERSION', '1.0.0')
    APP_DESCRIPTION: str = os.getenv('APP_DESCRIPTION', 'API para el proyecto')
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')

    # Configuración del servidor
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', 8000))
    WORKERS: int = int(os.getenv('WORKERS', 1))
    RELOAD: bool = os.getenv('RELOAD', 'False').lower() == 'true'

    # Configuración de seguridad
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')
    ALGORITHM: str = os.getenv('ALGORITHM', 'HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', 7))

    # Configuración de CORS
    CORS_ORIGINS: list = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:8000').split(',')
    CORS_ALLOW_CREDENTIALS: bool = os.getenv('CORS_ALLOW_CREDENTIALS', 'True').lower() == 'true'
    CORS_ALLOW_METHODS: list = ['*']
    CORS_ALLOW_HEADERS: list = ['*']

    # Configuración de base de datos
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///./app.db')
    DB_POOL_SIZE: int = int(os.getenv('DB_POOL_SIZE', 5))
    DB_MAX_OVERFLOW: int = int(os.getenv('DB_MAX_OVERFLOW', 10))
    DB_ECHO: bool = os.getenv('DB_ECHO', 'False').lower() == 'true'

    # Configuración de logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', 'app.log')

    # Configuración del límite de peticiones.
    # Lo aplica api/rate_limit.py sobre los endpoints sensibles. Es un limitador
    # en memoria y por proceso: con varios workers o instancias haría falta un
    # almacén compartido (Redis).
    RATE_LIMIT_ENABLED: bool = os.getenv('RATE_LIMIT_ENABLED', 'True').lower() == 'true'
    RATE_LIMIT_REQUESTS: int = int(os.getenv('RATE_LIMIT_REQUESTS', 100))
    RATE_LIMIT_PERIOD: int = int(os.getenv('RATE_LIMIT_PERIOD', 60))  # segundos

    # Configuración de paginación
    DEFAULT_PAGE_SIZE: int = int(os.getenv('DEFAULT_PAGE_SIZE', 20))
    MAX_PAGE_SIZE: int = int(os.getenv('MAX_PAGE_SIZE', 100))

    @classmethod
    def get_database_url(cls) -> str:
        """
        Obtiene la URL de la base de datos con las configuraciones adicionales
        """
        db_url = cls.DATABASE_URL

        # Si es SQLite, añadir parámetros para mejor rendimiento
        if db_url.startswith('sqlite'):
            # Asegurar que el directorio existe
            db_path = db_url.replace('sqlite:///', '')
            if db_path:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            # Añadir parámetros de conexión
            if '?' not in db_url:
                db_url += '?check_same_thread=False'
        else:
            # Para otras bases de datos, añadir parámetros de pool
            if '?' in db_url:
                db_url += '&'
            else:
                db_url += '?'

            # Para PostgreSQL
            if 'postgresql' in db_url or 'postgres' in db_url:
                db_url += f'pool_size={cls.DB_POOL_SIZE}&max_overflow={cls.DB_MAX_OVERFLOW}&pool_pre_ping=true'

        return db_url

    @classmethod
    def get_cors_origins(cls) -> list:
        """
        Procesa y devuelve los orígenes CORS
        """
        if cls.ENVIRONMENT == 'production':
            # En producción, solo permitir orígenes específicos
            return [origin.strip() for origin in cls.CORS_ORIGINS if origin.strip()]
        else:
            # En desarrollo, permitir más orígenes
            return ['*']

    @classmethod
    def get_logging_config(cls) -> Dict[str, Any]:
        """
        Configuración de logging estructurado
        """
        log_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)

        config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': cls.LOG_FORMAT,
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': log_level,
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout'
                }
            },
            'root': {
                'level': log_level,
                'handlers': ['console']
            }
        }

        # Añadir handler de archivo si se especifica
        if cls.LOG_FILE:
            config['handlers']['file'] = {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': log_level,
                'formatter': 'default',
                'filename': cls.LOG_FILE,
                'maxBytes': 10 * 1024 * 1024,  # 10MB
                'backupCount': 5
            }
            config['root']['handlers'].append('file')

        return config

    @classmethod
    def is_development(cls) -> bool:
        """Verifica si estamos en entorno de desarrollo"""
        return cls.ENVIRONMENT == 'development'

    @classmethod
    def is_production(cls) -> bool:
        """Verifica si estamos en entorno de producción"""
        return cls.ENVIRONMENT == 'production'

    @classmethod
    def is_testing(cls) -> bool:
        """Verifica si estamos en entorno de pruebas"""
        return cls.ENVIRONMENT == 'testing'

    # Secretos que no deben usarse NUNCA. Incluye la clave que traía el .env del
    # proyecto: tenía 39 caracteres, así que pasaba el filtro de longitud y la
    # validación no la detectaba.
    SECRETOS_DEBILES = {
        'your-secret-key-here',
        'cambia-esto-por-una-clave-larga-y-aleatoria',
        'mi-clave-super-secreta-para-docker-2024',
        'secret', 'secret-key', 'changeme', 'test', 'password',
    }

    LONGITUD_MINIMA_SECRET_KEY = 32

    @classmethod
    def validate_config(cls, estricto: Optional[bool] = None) -> bool:
        """
        Valida que la configuración sea correcta.

        En producción los problemas son FATALES: se lanza RuntimeError y la
        aplicación no arranca. Arrancar con una SECRET_KEY débil significa que
        cualquiera puede firmar tokens JWT válidos y suplantar a cualquier
        usuario, incluido un administrador.

        En desarrollo solo se avisa por el log, para no molestar.

        Args:
            estricto: si es None, se decide por el entorno (fatal en producción).

        Returns:
            True si la configuración es válida.
        """
        issues = []

        # --- SECRET_KEY ---
        # Se comprueba SIEMPRE (no solo en producción), porque es el secreto que
        # firma los tokens de sesión.
        if cls.SECRET_KEY in cls.SECRETOS_DEBILES:
            issues.append(
                'SECRET_KEY es un valor de ejemplo conocido. Genera uno con: '
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        elif len(cls.SECRET_KEY) < cls.LONGITUD_MINIMA_SECRET_KEY:
            issues.append(
                f'SECRET_KEY es demasiado corta ({len(cls.SECRET_KEY)} caracteres, '
                f'mínimo {cls.LONGITUD_MINIMA_SECRET_KEY})'
            )

        # Validar configuración de base de datos
        if not cls.DATABASE_URL:
            issues.append('DATABASE_URL no está configurada')

        # Validar tasa de límites
        if cls.RATE_LIMIT_REQUESTS <= 0:
            issues.append('RATE_LIMIT_REQUESTS debe ser mayor que 0')
        if cls.RATE_LIMIT_PERIOD <= 0:
            issues.append('RATE_LIMIT_PERIOD debe ser mayor que 0')

        # Validar paginación
        if cls.DEFAULT_PAGE_SIZE > cls.MAX_PAGE_SIZE:
            issues.append('DEFAULT_PAGE_SIZE no puede ser mayor que MAX_PAGE_SIZE')


        if not issues:
            return True

        fatal = cls.is_production() if estricto is None else estricto
        if fatal:
            raise RuntimeError(
                'Configuración inválida:\n  - ' + '\n  - '.join(issues)
            )

        for issue in issues:
            logging.warning(f'[Config Issue] {issue}')
        return False

    @classmethod
    def display_config(cls) -> None:
        """
        Muestra la configuración actual (útil para debug)
        """
        print("=" * 50)
        print("CONFIGURACIÓN ACTUAL")
        print("=" * 50)
        print(f"Environment: {cls.ENVIRONMENT}")
        print(f"App Name: {cls.APP_NAME}")
        print(f"Version: {cls.APP_VERSION}")
        print(f"Debug: {cls.DEBUG}")
        print(f"Host: {cls.HOST}:{cls.PORT}")
        print(f"Database: {cls.DATABASE_URL}")
        print(f"Rate Limit: {cls.RATE_LIMIT_REQUESTS}/{cls.RATE_LIMIT_PERIOD}s "
              f"({'activo' if cls.RATE_LIMIT_ENABLED else 'desactivado'})")
        print("=" * 50)


# Instancia de configuración para uso en la aplicación
config = Config()

# Validar la configuración al importar el módulo.
# En producción un problema es FATAL (ver validate_config): es preferible que la
# aplicación no arranque a que lo haga firmando tokens con una clave de ejemplo.
# En desarrollo solo se registran avisos.
config.validate_config()

# Ejemplo de uso de diferentes configuraciones según entorno
if __name__ == "__main__":
    # Esto solo se ejecuta si se corre directamente este archivo
    config.display_config()

    # Validar configuración
    is_valid = config.validate_config()
    print(f"Configuración válida: {is_valid}")

    # Obtener configuración de logging
    logging_config = config.get_logging_config()
    print(f"Logging configurado: {logging_config['root']['level']}")