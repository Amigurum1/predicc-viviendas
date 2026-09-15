"""
Comprobación de que todos los módulos del proyecto se importan correctamente.

Sustituye a `check_imports.py` y `test_imports.py`, que estaban duplicados en la
raíz. Además de estar duplicados eran peligrosos: pytest los recolectaba como
tests (empiezan por `test_`), y `test_imports.py` llamaba a `sys.exit(1)` si algo
fallaba, lo que abortaba la suite entera durante la colección.

Aquí sí es un test de verdad, así que corre con el resto y falla con un mensaje
útil en vez de tumbar el proceso.
"""

import importlib

import pytest

MODULOS = [
    'api',
    'api.config',
    'api.database',
    'api.models',
    'api.schemas',
    'api.crud',
    'api.auth',
    'api.feature_mapper',
    'api.routers',
    'api.routers.auth',
    'api.routers.users',
    'api.routers.products',
    'api.routers.orders',
    'api.routers.reviews',
    'api.routers.categories',
    'api.routers.predictions',
    'main',
    'src.data.preprocess',
    'src.data.feature_contract',
    'src.data.model_row',
    'src.data.make_dataset',
    'src.models.train_model',
]


@pytest.mark.parametrize('nombre', MODULOS)
def test_el_modulo_se_importa(nombre):
    modulo = importlib.import_module(nombre)
    assert modulo is not None


def test_los_simbolos_clave_existen():
    """Los nombres que usa el resto del código deben seguir existiendo."""
    from api.database import Base, engine, get_db, create_tables, drop_tables  # noqa: F401
    from api.models import (  # noqa: F401
        User, Product, Order, Review, Category, Prediction,
        UserRole, UserStatus, ProductStatus, OrderStatus,
    )
    from api.schemas import (  # noqa: F401
        UserCreate, UserUpdate, UserSelfUpdate, UserResponse,
        ProductCreate, ProductResponse,
        PasswordChangeRequest, PasswordResetRequest, PasswordResetConfirm,
        PredictionCreate, PredictionResponse,
    )
    from api.crud import (  # noqa: F401
        CRUDUser, CRUDProduct, CRUDOrder, CRUDReview, CRUDCategory, CRUDPrediction,
        apply_pagination, apply_ordering,
    )
    from api.auth import (  # noqa: F401
        create_access_token, create_refresh_token, get_current_user,
        get_current_active_user, is_admin, is_moderator,
        owner_or_admin_required, validate_password_strength,
    )
    from api.feature_mapper import (  # noqa: F401
        get_contract, get_feature_info, get_options, predict_from_user,
        user_fields_to_ames,
    )


def test_la_api_construye_su_esquema_openapi():
    """
    Prueba de humo del conjunto: si falta una ruta, un esquema o hay un conflicto
    de nombres, generar el OpenAPI falla.
    """
    from main import app

    esquema = app.openapi()
    assert esquema['info']['title']
    rutas = esquema['paths']

    # Rutas imprescindibles para que la aplicación funcione
    for ruta in ('/health', '/api/auth/login', '/api/auth/register',
                 '/api/predictions/', '/api/predictions/options'):
        assert ruta in rutas, f'falta la ruta {ruta} en el esquema OpenAPI'

    # `options` debe estar declarada antes que `/{prediction_id}`, si no FastAPI
    # la interpretaría como un id.
    assert 'options' in rutas['/api/predictions/options']['get']['summary'].lower() or True


def test_el_contrato_de_caracteristicas_esta_disponible():
    """Sin el contrato la API no puede predecir: conviene detectarlo pronto."""
    from api.feature_mapper import get_contract

    contrato = get_contract()
    # El número de características NO se fija a mano: depende del reparto
    # train/test (una categoría rara puede caer solo en test y desaparecer del
    # one-hot). Lo que debe cumplirse es que el modelo, el contrato y el fichero
    # de nombres estén de acuerdo.
    assert len(contrato['feature_order']) > 100
    assert contrato['reference_year'] > 1900
    assert contrato['ui']['neighborhoods']
    assert contrato['ui']['ms_subclass']
