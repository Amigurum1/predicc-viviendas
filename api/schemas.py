"""
Esquemas Pydantic para validación de datos
Define la estructura de datos de entrada y salida de la API
"""

from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID  # ✅ Agregar esta línea

import re

# ✅ CORREGIR: Importar desde api.models
from api.models import UserRole, UserStatus, ProductStatus, OrderStatus

# ============================================
# ESQUEMAS BASE (para reutilizar)
# ============================================

class BaseSchema(BaseModel):
    """Esquema base con configuración común"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

class TimestampSchema(BaseSchema):
    """Esquema con timestamps"""
    created_at: datetime
    updated_at: Optional[datetime] = None

class IDSchema(BaseSchema):
    """Esquema con ID"""
    id: int
    uuid: UUID  # ✅ Ahora acepta UUID

# ============================================
# ESQUEMAS DE USUARIO
# ============================================

# ------------------------------------------------------------
# POLÍTICA DE CONTRASEÑAS
# ------------------------------------------------------------
# Se define UNA vez y se aplica en todos los caminos (registro, cambio de
# contraseña y reseteo). Antes solo la aplicaba el registro: `change-password`
# aceptaba "1" como contraseña nueva.

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 100


def validar_fortaleza_password(password: str) -> str:
    """
    Comprueba la política de contraseñas y devuelve la contraseña.

    Lanza ValueError con un mensaje concreto para que el cliente sepa qué falta.
    """
    if password is None or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f'La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres'
        )
    if not re.search(r'[A-Z]', password):
        raise ValueError('La contraseña debe tener al menos una mayúscula')
    if not re.search(r'[a-z]', password):
        raise ValueError('La contraseña debe tener al menos una minúscula')
    if not re.search(r'[0-9]', password):
        raise ValueError('La contraseña debe tener al menos un número')
    if not re.search(r'[^A-Za-z0-9]', password):
        raise ValueError('La contraseña debe tener al menos un carácter especial')
    return password


def _validar_password_campo(valor: Optional[str]) -> Optional[str]:
    """Validador reutilizable para campos opcionales de contraseña."""
    if valor is None:
        return valor
    return validar_fortaleza_password(valor)


class UserBase(BaseSchema):
    """
    Datos base de usuario.

    OJO: aquí NO está `role` a propósito. Estaba en la base y la heredaban los
    esquemas de ENTRADA, así que cualquiera podía mandar `"role": "admin"` al
    registrarse (o al editar su perfil) y convertirse en administrador. El rol
    solo lo puede cambiar un administrador, a través de `UserUpdate`.
    """
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)

    @validator('username')
    def validate_username(cls, v):
        """Validar que el username solo tenga caracteres permitidos"""
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('El username solo puede contener letras, números y guión bajo')
        return v

class UserCreate(UserBase):
    """Datos para crear usuario (registro público)"""
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @validator('password')
    def validate_password(cls, v):
        return validar_fortaleza_password(v)

class UserUpdate(BaseSchema):
    """
    Datos que un ADMINISTRADOR puede actualizar de un usuario.

    Incluye campos de privilegio (role, status, is_active, is_verified). NO se
    debe usar para que un usuario edite su propio perfil: para eso está
    `UserSelfUpdate`.
    """
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    password: Optional[str] = Field(None, min_length=PASSWORD_MIN_LENGTH,
                                    max_length=PASSWORD_MAX_LENGTH)
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    language: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)
    notifications_enabled: Optional[bool] = None

    @validator('password')
    def validate_password(cls, v):
        return _validar_password_campo(v)


class UserSelfUpdate(BaseSchema):
    """
    Datos que un usuario puede cambiar de SU PROPIO perfil.

    Deliberadamente SIN role, status, is_active ni is_verified: son campos de
    privilegio y permitirlos aquí es una escalada de privilegios (un usuario
    normal se ponía `role: "admin"` y accedía a los endpoints de administrador).
    """
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    password: Optional[str] = Field(None, min_length=PASSWORD_MIN_LENGTH,
                                    max_length=PASSWORD_MAX_LENGTH)
    language: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)
    notifications_enabled: Optional[bool] = None

    @validator('username')
    def validate_username(cls, v):
        if v is None:
            return v
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('El username solo puede contener letras, números y guión bajo')
        return v

    @validator('password')
    def validate_password(cls, v):
        return _validar_password_campo(v)


class UserResponse(UserBase, TimestampSchema, IDSchema):
    """Respuesta de usuario (sin información sensible)"""
    role: UserRole
    status: UserStatus
    is_active: bool
    is_verified: bool
    is_superuser: bool
    last_login: Optional[datetime] = None
    full_name: Optional[str] = None

class UserLogin(BaseSchema):
    """Datos para login"""
    email: EmailStr
    password: str

# ------------------------------------------------------------
# CONTRASEÑAS: cambio y reseteo
# ------------------------------------------------------------
# Estos datos van en el CUERPO de la petición, nunca en la URL. Antes eran
# parámetros sueltos, así que las contraseñas viajaban en el query string y
# quedaban en el log de accesos de uvicorn y en el historial del navegador.

class PasswordChangeRequest(BaseSchema):
    """Cambio de contraseña del usuario autenticado"""
    old_password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH,
                              max_length=PASSWORD_MAX_LENGTH)

    @validator('new_password')
    def validate_new_password(cls, v):
        return validar_fortaleza_password(v)


class PasswordResetRequest(BaseSchema):
    """Solicitud de reseteo de contraseña"""
    email: EmailStr


class PasswordResetConfirm(BaseSchema):
    """Confirmación del reseteo con el token recibido"""
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH,
                              max_length=PASSWORD_MAX_LENGTH)

    @validator('new_password')
    def validate_new_password(cls, v):
        return validar_fortaleza_password(v)

class UserTokenResponse(BaseSchema):
    """Respuesta con tokens JWT"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class UserRefreshToken(BaseSchema):
    """Datos para refrescar token"""
    refresh_token: str

# ============================================
# ESQUEMAS DE PRODUCTO
# ============================================

class ProductBase(BaseSchema):
    """Datos base de producto"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    discount_price: Optional[float] = Field(None, gt=0)
    stock: int = Field(0, ge=0)
    sku: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=100)
    main_image: Optional[str] = Field(None, max_length=500)
    images: Optional[List[str]] = None
    is_featured: bool = False

    @validator('discount_price')
    def validate_discount_price(cls, v, values):
        """Validar que el descuento sea menor que el precio"""
        if v is not None and 'price' in values and v >= values['price']:
            raise ValueError('El precio con descuento debe ser menor que el precio regular')
        return v

class ProductCreate(ProductBase):
    """Datos para crear producto"""
    owner_id: Optional[int] = None  # ✅ CAMBIADO DE int A Optional[int] = None

class ProductUpdate(BaseSchema):
    """Datos para actualizar producto"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    discount_price: Optional[float] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)
    sku: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=100)
    status: Optional[ProductStatus] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    main_image: Optional[str] = Field(None, max_length=500)

class ProductResponse(ProductBase, TimestampSchema, IDSchema):
    """Respuesta de producto"""
    status: ProductStatus
    is_active: bool
    is_featured: bool
    owner_id: int
    views_count: int
    sales_count: int
    rating_avg: float
    rating_count: int
    in_stock: bool
    final_price: float
    owner: Optional[UserResponse] = None

class ProductListResponse(BaseSchema):
    """Respuesta paginada de productos"""
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int

# ============================================
# ESQUEMAS DE ORDEN
# ============================================

class OrderItemBase(BaseSchema):
    """Datos base de ítem de orden"""
    product_id: int
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)
    discount_per_item: Optional[float] = Field(0, ge=0)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase, IDSchema):
    """Respuesta de ítem de orden"""
    total_price: float
    product: Optional[ProductResponse] = None

class OrderBase(BaseSchema):
    """Datos base de orden"""
    shipping_address: str
    billing_address: Optional[str] = None
    payment_method: Optional[str] = Field(None, max_length=50)
    shipping_method: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None

class OrderCreate(OrderBase):
    """Datos para crear orden"""
    items: List[OrderItemCreate]

class OrderUpdate(BaseSchema):
    """Datos para actualizar orden"""
    status: Optional[OrderStatus] = None
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = Field(None, max_length=100)
    shipping_address: Optional[str] = None
    billing_address: Optional[str] = None
    notes: Optional[str] = None

class OrderResponse(OrderBase, TimestampSchema, IDSchema):
    """Respuesta de orden"""
    order_number: str
    status: OrderStatus
    subtotal: float
    tax: float
    shipping_cost: float
    discount_total: float
    total: float
    payment_status: str
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    user_id: int
    items: List[OrderItemResponse]
    user: Optional[UserResponse] = None

# ============================================
# ESQUEMAS DE RESEÑA
# ============================================

class ReviewBase(BaseSchema):
    """Datos base de reseña"""
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    """Datos para crear reseña"""
    product_id: int

class ReviewUpdate(BaseSchema):
    """Datos para actualizar reseña"""
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None

class ReviewResponse(ReviewBase, TimestampSchema, IDSchema):
    """Respuesta de reseña"""
    user_id: int
    product_id: int
    user: Optional[UserResponse] = None
    product: Optional[ProductResponse] = None

# ============================================
# ESQUEMAS DE CATEGORÍA
# ============================================

class CategoryBase(BaseSchema):
    """Datos base de categoría"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    is_active: bool = True

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseSchema):
    """Datos para actualizar categoría"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None

class CategoryResponse(CategoryBase, TimestampSchema, IDSchema):
    """Respuesta de categoría"""
    children: List['CategoryResponse'] = []

# ============================================
# ESQUEMAS DE AUTENTICACIÓN Y COMUNES
# ============================================

class TokenData(BaseSchema):
    """Datos del token JWT"""
    email: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[UserRole] = None

class MessageResponse(BaseSchema):
    """Respuesta simple con mensaje"""
    message: str
    success: bool = True
    data: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseSchema):
    """Respuesta de error"""
    detail: str
    status_code: int
    error_type: Optional[str] = None

class PaginationParams(BaseSchema):
    """Parámetros de paginación"""
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_order: str = Field("asc", pattern="^(asc|desc)$")

class FilterParams(BaseSchema):
    """Parámetros de filtrado"""
    search: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    in_stock: Optional[bool] = None
    rating_min: Optional[float] = Field(None, ge=0, le=5)

# ============================================
# NOTA
# ============================================
# Aquí vivían `FileUploadResponse` y `DashboardMetrics`. Se han retirado por ser
# esquemas muertos: no hay ningún endpoint de subida de archivos ni ninguna ruta
# que devuelva métricas globales del dashboard (el dashboard usa
# /api/predictions/stats/me). Con ellos se ha quitado también la configuración de
# subida de `api/config.py`.

# Exportar todos los esquemas
__all__ = [
    'UserBase', 'UserCreate', 'UserUpdate', 'UserSelfUpdate', 'UserResponse',
    'UserLogin', 'UserTokenResponse', 'UserRefreshToken',
    'PasswordChangeRequest', 'PasswordResetRequest', 'PasswordResetConfirm',
    'validar_fortaleza_password',
    'ProductBase', 'ProductCreate', 'ProductUpdate', 'ProductResponse',
    'ProductListResponse',
    'OrderBase', 'OrderCreate', 'OrderUpdate', 'OrderResponse',
    'OrderItemBase', 'OrderItemCreate', 'OrderItemResponse',
    'ReviewBase', 'ReviewCreate', 'ReviewUpdate', 'ReviewResponse',
    'CategoryBase', 'CategoryCreate', 'CategoryUpdate', 'CategoryResponse',
    'TokenData', 'MessageResponse', 'ErrorResponse',
    'PaginationParams', 'FilterParams'
]

# ============================================
# ESQUEMAS DE PREDICCIÓN
# ============================================
#
# El formulario tiene 9 campos. Los límites NO son arbitrarios: se derivan del
# rango real del dataset de entrenamiento (models_saved/feature_contract.json),
# porque el modelo solo conoce viviendas dentro de esos rangos. Si no se puede
# cargar el contrato se usan límites amplios de seguridad, pero la API avisa en
# /health y en el arranque.

def _rangos_del_modelo():
    """Límites reales de los campos del formulario, desde el contrato."""
    try:
        from api.feature_mapper import get_contract, M2_A_FT2

        crudos = get_contract().get('raw_ranges', {})

        def entero(campo, defecto):
            info = crudos.get(campo)
            if not info:
                return defecto
            return int(info['min']), int(info['max'])

        def metros(campo, defecto):
            info = crudos.get(campo)
            if not info:
                return defecto
            return (
                int(round(info['min'] / M2_A_FT2)),
                int(round(info['max'] / M2_A_FT2)),
            )

        anio_ref = int(get_contract()['reference_year'])
        return {
            'gr_liv_area_m2': metros('GrLivArea', (20, 550)),
            'lot_area_m2': metros('LotArea', (50, 20000)),
            'overall_qual': entero('OverallQual', (1, 10)),
            'year_built': (entero('YearBuilt', (1800, 2010))[0], anio_ref),
            'bedrooms': entero('BedroomAbvGr', (0, 10)),
            'bathrooms': entero('FullBath', (0, 8)),
            'garage_cars': entero('GarageCars', (0, 4)),
        }
    except Exception:  # contrato ausente o ilegible: límites de seguridad
        return {
            'gr_liv_area_m2': (20, 550),
            'lot_area_m2': (50, 20000),
            'overall_qual': (1, 10),
            'year_built': (1800, 2010),
            'bedrooms': (0, 10),
            'bathrooms': (0, 8),
            'garage_cars': (0, 4),
        }


_RANGOS = _rangos_del_modelo()


class PredictionBase(BaseSchema):
    """Datos de entrada de una predicción (9 campos del formulario)"""

    # Ubicación y tipo: valores reales del dataset de Ames
    neighborhood: str = Field(
        ..., min_length=1, max_length=100,
        description="Barrio de Ames (ver GET /api/predictions/options)",
    )
    ms_subclass: int = Field(
        ..., description="Tipo de vivienda según el código MSSubClass",
    )

    # Superficies: la API trabaja en m² y las convierte a ft²
    gr_liv_area_m2: float = Field(
        ..., ge=_RANGOS['gr_liv_area_m2'][0], le=_RANGOS['gr_liv_area_m2'][1],
        description="Superficie habitable en m²",
    )
    lot_area_m2: float = Field(
        ..., ge=_RANGOS['lot_area_m2'][0], le=_RANGOS['lot_area_m2'][1],
        description="Superficie de la parcela en m²",
    )

    # Características de la vivienda
    overall_qual: int = Field(
        ..., ge=_RANGOS['overall_qual'][0], le=_RANGOS['overall_qual'][1],
        description="Calidad general de la vivienda (1-10)",
    )
    year_built: int = Field(
        ..., ge=_RANGOS['year_built'][0], le=_RANGOS['year_built'][1],
        description="Año de construcción",
    )
    bedrooms: int = Field(
        ..., ge=_RANGOS['bedrooms'][0], le=_RANGOS['bedrooms'][1],
        description="Número de dormitorios",
    )
    bathrooms: int = Field(
        ..., ge=_RANGOS['bathrooms'][0], le=_RANGOS['bathrooms'][1],
        description="Número de baños completos",
    )
    garage_cars: int = Field(
        ..., ge=_RANGOS['garage_cars'][0], le=_RANGOS['garage_cars'][1],
        description="Plazas de garaje",
    )

    # Opcionales, solo informativos (ubicación elegida en el mapa)
    latitude: Optional[float] = Field(None, description="Latitud")
    longitude: Optional[float] = Field(None, description="Longitud")
    product_id: Optional[int] = Field(None, description="ID del producto asociado")


class PredictionCreate(PredictionBase):
    """Datos para crear una predicción"""
    pass


class PredictionResponse(PredictionBase, IDSchema, TimestampSchema):
    """Respuesta de predicción"""
    predicted_price: float
    confidence: float
    currency: str = Field("USD", description="Moneda del modelo (Ames, EE. UU.)")
    user_id: int
    product_id: Optional[int] = None
    user: Optional[UserResponse] = None
    product: Optional[ProductResponse] = None


class PredictionHistoryResponse(BaseSchema):
    """Respuesta de historial de predicciones"""
    items: List[PredictionResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PredictionStats(BaseSchema):
    """Estadísticas de predicciones"""
    total_predictions: int
    avg_predicted_price: float
    min_predicted_price: float
    max_predicted_price: float
    avg_confidence: float
    top_neighborhoods: List[Dict[str, Any]]
    by_property_type: List[Dict[str, Any]]