"""
Configuración de pytest para todas las pruebas
"""

import atexit
import os
import shutil
import sys
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from typing import Generator

# Agregar el directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# AISLAMIENTO DE LA BASE DE DATOS (D3)
# ============================================================
# Esto TIENE que ir ANTES de importar `api.database`, porque el engine se crea
# al importar ese módulo y apuntaría a la base de datos real (app.db).
#
# Antes, la suite usaba la BD de producción en varios sitios:
#   * test_database.py usaba el `engine` y `SessionLocal()` del módulo;
#   * el lifespan de FastAPI llama a `create_tables()` en app.db al arrancar el
#     TestClient;
#   * `/health` comprobaba las tablas de app.db.
# Es decir, ejecutar los tests modificaba el fichero de la aplicación. Lo peor
# fue un test que llamaba a `drop_tables()` y llegó a borrar sus tablas.
#
# `api.config` usa `load_dotenv(override=False)`, así que una variable de entorno
# ya definida gana sobre el `.env`: basta con fijarla aquí.
_DIRECTORIO_TESTS = tempfile.mkdtemp(prefix='predicc_tests_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_DIRECTORIO_TESTS, 'test.db')}"


def _limpiar_directorio_temporal():
    """
    Borra el directorio temporal al terminar la sesión de pytest.

    En Windows hay que soltar antes la conexión: si el motor sigue abierto,
    el fichero .db está bloqueado, `shutil.rmtree` falla y —como se le pasa
    `ignore_errors=True`— la suite termina bien pero deja un directorio
    `predicc_tests_*` en %TEMP% por cada ejecución.
    """
    try:
        from api.database import engine
        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_DIRECTORIO_TESTS, ignore_errors=True)


atexit.register(_limpiar_directorio_temporal)

# ============================================================
# SALIDA EN UTF-8
# ============================================================
# Varias pruebas hacen `print("✅ ...")`. Sin captura de pytest (`pytest -s`), la
# salida va a la consola de Windows, que usa cp1252 y no sabe codificar emojis:
# el resultado era `UnicodeEncodeError` y 25 pruebas fallando solo por eso.
# Con captura no ocurría porque pytest captura en UTF-8, de modo que el fallo
# aparecía únicamente al depurar con `-s`. Se fuerza UTF-8 en la salida.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, 'reconfigure'):
        try:
            _flujo.reconfigure(encoding='utf-8')
        except Exception:  # consola que no admite reconfiguración
            pass

from api.database import Base, get_db  # noqa: E402
from api.models import User, Product, Order, Review, Category  # noqa: E402,F401
from api.config import config  # noqa: E402,F401
from main import app  # noqa: E402

@pytest.fixture(scope="function")
def test_db_path():
    """Crear una ruta de base de datos temporal para cada prueba"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    yield db_path
    # Limpiar después de la prueba
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture(scope="function")
def test_engine(test_db_path):
    """Engine de base de datos para pruebas - NUEVO por cada prueba"""
    # ✅ Usar archivo temporal en lugar de memoria
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False}
    )
    # ✅ Crear todas las tablas
    Base.metadata.create_all(bind=engine)
    yield engine
    # ✅ Limpiar después de la prueba
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(test_engine):
    """Sesión de base de datos para cada prueba"""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(autouse=True)
def _reiniciar_limite_de_peticiones():
    """
    Vacía el contador del límite de peticiones antes de cada prueba.

    El limitador vive en el módulo `main`, que es único para toda la sesión de
    pytest, así que sin esto las peticiones de una prueba consumirían el cupo de
    las siguientes y aparecerían 429 difíciles de explicar. Las pruebas del
    propio limitador siguen funcionando porque lo configuran y lo reinician
    ellas mismas.
    """
    try:
        from main import limitador
        if limitador is not None:
            limitador.reiniciar()
    except Exception:
        pass
    yield
    try:
        from main import limitador
        if limitador is not None:
            limitador.reiniciar()
    except Exception:
        pass


@pytest.fixture(scope="function")
def client(db_session):
    """Cliente de pruebas FastAPI"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_user(db_session):
    """Crear usuario de prueba - NUEVO para cada prueba"""
    from api.crud import CRUDUser
    from api.schemas import UserCreate
    
    user_data = UserCreate(
        email="test@example.com",
        username="testuser",
        password="Test123!@#",
        first_name="Test",
        last_name="User"
    )
    user = CRUDUser.create(db_session, user_data)
    db_session.commit()
    return user

@pytest.fixture(scope="function")
def test_product(db_session, test_user):
    """Crear producto de prueba"""
    from api.crud import CRUDProduct
    from api.schemas import ProductCreate
    
    product_data = ProductCreate(
        name="Producto Test",
        description="Descripción de prueba",
        price=99.99,
        stock=10,
        sku="TEST-001",
        category="Electrónicos",
        brand="Test Brand",
        owner_id=test_user.id
    )
    product = CRUDProduct.create(db_session, product_data)
    db_session.commit()
    return product

@pytest.fixture(scope="function")
def test_order(db_session, test_user, test_product):
    """Crear orden de prueba"""
    from api.crud import CRUDOrder
    from api.schemas import OrderCreate, OrderItemCreate
    
    order_items = [
        OrderItemCreate(
            product_id=test_product.id,
            quantity=2,
            unit_price=99.99
        )
    ]
    
    order_data = OrderCreate(
        shipping_address="Calle Test 123",
        items=order_items
    )
    
    order = CRUDOrder.create(db_session, order_data, test_user.id)
    db_session.commit()
    return order

@pytest.fixture(scope="function")
def auth_headers(test_user):
    """Headers de autenticación para pruebas"""
    from api.auth import create_access_token
    
    token_data = {
        "sub": str(test_user.id),
        "email": test_user.email,
        "role": test_user.role.value,
        "user_id": test_user.id
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}