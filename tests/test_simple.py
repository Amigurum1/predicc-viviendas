"""
Pruebas simples para verificar el funcionamiento básico
"""

import pytest
import sys
import os

# Agregar el directorio padre al path para poder importar los módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_pytest_works():
    """Prueba básica que siempre pasa"""
    assert 1 + 1 == 2
    print("\n✅ pytest funciona correctamente")

def test_import_config():
    """Verificar que se puede importar config"""
    from api.config import config
    assert config.APP_NAME is not None
    print(f"\n✅ Configuración cargada: {config.APP_NAME}")

def test_import_database():
    """Verificar que se puede importar database"""
    from api.database import get_db
    assert get_db is not None
    print("\n✅ Database importado correctamente")

def test_import_models():
    """Verificar que se pueden importar los modelos"""
    from api.models import User, Product, Order
    assert User is not None
    assert Product is not None
    assert Order is not None
    print("\n✅ Modelos importados correctamente")

def test_import_schemas():
    """Verificar que se pueden importar los schemas"""
    from api.schemas import UserCreate, ProductCreate
    assert UserCreate is not None
    assert ProductCreate is not None
    print("\n✅ Schemas importados correctamente")

def test_import_crud():
    """Verificar que se puede importar CRUD"""
    from api.crud import CRUDUser, CRUDProduct
    assert CRUDUser is not None
    assert CRUDProduct is not None
    print("\n✅ CRUD importado correctamente")

def test_import_auth():
    """Verificar que se puede importar auth"""
    from api.auth import create_access_token, get_current_user
    assert create_access_token is not None
    assert get_current_user is not None
    print("\n✅ Auth importado correctamente")

def test_all_imports():
    """Prueba de todas las importaciones juntas"""
    try:
        from api.config import config
        from api.database import get_db
        from api.models import User, Product
        from api.schemas import UserCreate
        from api.crud import CRUDUser
        from api.auth import create_access_token
        
        print("\n✅ Todas las importaciones funcionan correctamente")
        assert True
    except Exception as e:
        print(f"\n❌ Error en importaciones: {e}")
        assert False

if __name__ == "__main__":
    # Esto permite ejecutar el archivo directamente
    pytest.main([__file__, "-v"])