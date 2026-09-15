"""
Modelos de base de datos (SQLAlchemy ORM)
Define la estructura de todas las tablas
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, Enum, Index, Uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

# ✅ CORREGIR: Importar Base desde database
from api.database import Base

# ============================================
# ENUMS (para campos con valores fijos)
# ============================================

class UserRole(str, enum.Enum):
    """Roles de usuario"""
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"
    GUEST = "guest"

class UserStatus(str, enum.Enum):
    """Estados de usuario"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"

class ProductStatus(str, enum.Enum):
    """Estados de producto"""
    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    PENDING = "pending"

class OrderStatus(str, enum.Enum):
    """Estados de orden"""
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

# ============================================
# MODELOS PRINCIPALES
# ============================================

class User(Base):
    """Modelo de Usuario"""
    __tablename__ = "users"

    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Autenticación
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Información personal
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    avatar_url = Column(String(500))
    
    # Configuración
    role = Column(Enum(UserRole), default=UserRole.USER)
    # Los usuarios nacen ACTIVE. Antes el valor por defecto era PENDING, a la
    # espera de una verificación de email que nunca se enviaba (no hay SMTP), así
    # que el estado no significaba nada en la práctica.
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    is_active = Column(Boolean, default=True)
    # Campo reservado: no hay flujo de verificación implementado, así que hoy
    # siempre es False. Se conserva la columna por si se añade más adelante.
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    
    # Preferencias
    language = Column(String(10), default="es")
    timezone = Column(String(50), default="America/Lima")
    notifications_enabled = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relaciones
    products = relationship("Product", back_populates="owner", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")

    
    # Índices
    __table_args__ = (
        Index('ix_users_email_status', 'email', 'status'),
        Index('ix_users_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"

    @property
    def full_name(self):
        """Nombre completo del usuario"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.username

class Product(Base):
    """Modelo de Producto"""
    __tablename__ = "products"

    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Datos del producto
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    price = Column(Float, nullable=False)
    discount_price = Column(Float)
    stock = Column(Integer, default=0)
    
    # Detalles
    sku = Column(String(50), unique=True, index=True)
    category = Column(String(100), index=True)
    brand = Column(String(100))
    
    # Imágenes
    main_image = Column(String(500))
    images = Column(Text)  # JSON con múltiples imágenes
    
    # Estado
    status = Column(Enum(ProductStatus), default=ProductStatus.PENDING)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    
    # Métricas
    views_count = Column(Integer, default=0)
    sales_count = Column(Integer, default=0)
    rating_avg = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Claves foráneas
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relaciones
    owner = relationship("User", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="product", cascade="all, delete-orphan")

    
    # Índices
    __table_args__ = (
        Index('ix_products_category_status', 'category', 'status'),
        Index('ix_products_price_rating', 'price', 'rating_avg'),
    )

    def __repr__(self):
        return f"<Product {self.name} (${self.price})>"

    @property
    def final_price(self):
        """Precio final (con descuento aplicado)"""
        if self.discount_price and self.discount_price < self.price:
            return self.discount_price
        return self.price

    @property
    def in_stock(self):
        """Verifica si hay stock disponible"""
        return self.stock > 0

class Order(Base):
    """Modelo de Orden"""
    __tablename__ = "orders"

    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Datos de la orden
    order_number = Column(String(50), unique=True, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    
    # Totales
    subtotal = Column(Float, nullable=False)
    tax = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    discount_total = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
    
    # Direcciones
    shipping_address = Column(Text, nullable=False)
    billing_address = Column(Text)
    
    # Información de pago
    payment_method = Column(String(50))
    payment_status = Column(String(50), default="pending")
    payment_id = Column(String(100))
    
    # Información de envío
    shipping_method = Column(String(50))
    tracking_number = Column(String(100))
    estimated_delivery = Column(DateTime(timezone=True))
    
    # Notas
    notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    shipped_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    
    # Claves foráneas
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relaciones
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    
    # Índices
    __table_args__ = (
        Index('ix_orders_order_number', 'order_number', 'status'),  # Único índice manual
        Index('ix_orders_user_status', 'user_id', 'status'),
        Index('ix_orders_created_at', 'created_at'),
    )  # ← ¡AGREGAR ESTE PARÉNTESIS DE CIERRE!

    def __repr__(self):
        return f"<Order {self.order_number} - ${self.total}>"

class OrderItem(Base):
    """Modelo de Ítem de Orden"""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    
    # Datos del ítem
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount_per_item = Column(Float, default=0.0)
    total_price = Column(Float, nullable=False)
    
    # Claves foráneas
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    # Relaciones
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<OrderItem {self.product_id} x{self.quantity}>"

class Review(Base):
    """Modelo de Reseña/Calificación"""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    
    # Contenido
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text)
    
    # Claves foráneas
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    # Relaciones
    user = relationship("User", back_populates="reviews")
    product = relationship("Product", back_populates="reviews")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Índices
    __table_args__ = (
        Index('ix_reviews_product_rating', 'product_id', 'rating'),
        Index('ix_reviews_user_product', 'user_id', 'product_id', unique=True),
    )

    def __repr__(self):
        return f"<Review {self.rating}⭐ para producto {self.product_id}>"


class Prediction(Base):
    """Modelo de Predicción de precios"""
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Datos de entrada (los 9 campos del formulario, en unidades del usuario:
    # m² para superficies). Los campos reales del dataset de Ames se reconstruyen
    # con models_saved/feature_contract.json.
    neighborhood = Column(String(100), nullable=False)   # barrio de Ames
    ms_subclass = Column(Integer, nullable=False)        # tipo de vivienda
    gr_liv_area_m2 = Column(Float, nullable=False)       # superficie habitable
    lot_area_m2 = Column(Float, nullable=False)          # superficie de parcela
    overall_qual = Column(Integer, nullable=False)       # calidad general 1-10
    year_built = Column(Integer, nullable=False)         # año de construcción
    bedrooms = Column(Integer, nullable=False)
    bathrooms = Column(Integer, nullable=False)          # baños completos
    garage_cars = Column(Integer, nullable=False)        # plazas de garaje

    # Resultado
    predicted_price = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)

    # Ubicación elegida en el mapa (opcional, solo informativa)
    latitude = Column(Float)
    longitude = Column(Float)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)

    user = relationship("User", back_populates="predictions")
    product = relationship("Product", back_populates="predictions")

    def __repr__(self):
        return (
            f"<Prediction ${self.predicted_price:,.2f} for {self.bedrooms}bd "
            f"{self.gr_liv_area_m2}m2 in {self.neighborhood}>"
        )


# Agregar relación en User (modelo existente)
# Buscar la sección de relaciones en User y agregar:
# predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")

# Agregar relación en Product (modelo existente)
# Buscar la sección de relaciones en Product y agregar:
# predictions = relationship("Prediction", back_populates="product", cascade="all, delete-orphan")


class Category(Base):
    """Modelo de Categoría (ejemplo adicional)"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("categories.id"))
    icon = Column(String(50))
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relación jerárquica
    parent = relationship("Category", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Category {self.name}>"

# Exportar todos los modelos
__all__ = [
    'User',
    'Product', 
    'Order',
    'OrderItem',
    'Review',
    'Category',
    'UserRole',
    'UserStatus',
    'ProductStatus',
    'OrderStatus',
]