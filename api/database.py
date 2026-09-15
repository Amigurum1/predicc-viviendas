"""
Configuración de la base de datos
Maneja la conexión, sesiones y utilidades para SQLAlchemy
"""

from sqlalchemy import create_engine, text, inspect
# ✅ CORREGIR: Importar declarative_base desde sqlalchemy.orm
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator, List
import logging

from api.config import config

# Configurar logger
logger = logging.getLogger(__name__)

# Obtener la URL de la base de datos desde la configuración
DATABASE_URL = config.get_database_url()

# Configurar el engine de SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=config.DB_ECHO,
)

# Crear fábrica de sesiones
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ✅ CORREGIR: Usar declarative_base desde sqlalchemy.orm
Base = declarative_base()

# Función para obtener sesión de base de datos
def get_db() -> Generator[Session, None, None]:
    """
    Dependencia de FastAPI para obtener una sesión de base de datos.
    Se cierra automáticamente al finalizar la petición.
    """
    db = SessionLocal()
    try:
        logger.debug("Sesión de base de datos creada")
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de base de datos: {e}")
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("Sesión de base de datos cerrada")

# Función para crear las tablas
def create_tables():
    """Crea todas las tablas en la base de datos"""
    logger.info("Creando tablas en la base de datos...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tablas creadas exitosamente")

def entornos_donde_se_puede_borrar(entorno: str) -> bool:
    """
    ¿Está permitido borrar tablas en este entorno?

    Función pura y aislada a propósito: así se puede probar la protección sin
    riesgo de borrar nada.
    """
    return entorno in ('development', 'testing')


# Función para eliminar todas las tablas
def drop_tables(confirm: bool = False):
    """
    Elimina TODAS las tablas de la base de datos.

    ⚠️ OPERACIÓN DESTRUCTIVA. Y peligrosa de una forma poco evidente: el engine
    de este módulo apunta a la base de datos REAL (`sqlite:///./app.db`), no a
    una de pruebas. La base de datos de los tests se inyecta aparte, con
    `app.dependency_overrides[get_db]`. Por eso una llamada accidental desde un
    test (o desde cualquier script) borra los usuarios, los productos y todo el
    historial de la aplicación.

    Por eso ahora exige `confirm=True` explícito: sin él no toca nada, ni
    siquiera comprueba el entorno. Además sigue restringido a desarrollo/pruebas.

    Args:
        confirm: hay que pasar True de forma deliberada.

    Raises:
        RuntimeError: si no se pasa `confirm=True`.
        Exception: si el entorno no es desarrollo ni pruebas.
    """
    if not confirm:
        raise RuntimeError(
            "drop_tables() es destructivo y requiere confirm=True. El engine de "
            "este módulo apunta a la base de datos real (app.db), no a la de "
            "pruebas: una llamada accidental borra usuarios, productos e historial."
        )

    if not entornos_donde_se_puede_borrar(config.ENVIRONMENT):
        raise Exception(
            f"No se pueden eliminar tablas en el entorno '{config.ENVIRONMENT}'"
        )

    logger.warning("⚠️ Eliminando TODAS las tablas de %s", config.get_database_url())
    Base.metadata.drop_all(bind=engine)
    logger.warning("Tablas eliminadas")

# Función para verificar la conexión
def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ Conexión a base de datos exitosa")
            return True
    except Exception as e:
        logger.error(f"❌ Error conectando a la base de datos: {e}")
        return False

# Función para verificar que las tablas existen de verdad
def get_missing_tables() -> List[str]:
    """
    Devuelve las tablas declaradas en los modelos que todavía no existen en la BD.

    Es importante distinguir "hay conexión" de "las tablas están creadas": se puede
    conectar correctamente y no tener ninguna tabla (por ejemplo si create_all()
    falló al compilar algún tipo), y entonces la API responde 500 en cada consulta.
    """
    try:
        existentes = set(inspect(engine).get_table_names())
    except Exception as e:
        logger.error(f"❌ No se pudieron inspeccionar las tablas: {e}")
        return sorted(Base.metadata.tables.keys())

    return sorted(set(Base.metadata.tables.keys()) - existentes)

# Exportar lo necesario
__all__ = [
    'engine',
    'SessionLocal',
    'Base',
    'get_db',
    'create_tables',
    'drop_tables',
    'entornos_donde_se_puede_borrar',
    'test_connection',
    'get_missing_tables',
]