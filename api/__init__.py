"""
API para Predicc_viviendas
Módulo principal de la API
"""

__version__ = "1.0.0"
__author__ = "Tu Nombre"

# ✅ Importar config primero
from api.config import config
from api.database import Base, get_db, engine
from api.models import User, Product, Order, Review, Category
from api.schemas import UserCreate, ProductCreate, OrderCreate
from api.crud import CRUDUser, CRUDProduct, CRUDOrder
from api.auth import create_access_token, get_current_user, is_admin

__all__ = [
    'config',
    'Base',
    'get_db',
    'engine',
    'User',
    'Product', 
    'Order',
    'Review',
    'Category',
    'UserCreate',
    'ProductCreate',
    'OrderCreate',
    'CRUDUser',
    'CRUDProduct',
    'CRUDOrder',
    'create_access_token',
    'get_current_user',
    'is_admin',
]