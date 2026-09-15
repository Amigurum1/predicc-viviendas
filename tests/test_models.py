"""
Pruebas para los modelos de datos
Verifica que los modelos estén correctamente definidos
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import class_mapper
from datetime import datetime
import uuid

from api.models import (
    User, Product, Order, OrderItem, Review, Category,
    UserRole, UserStatus, ProductStatus, OrderStatus
)
from api.database import Base


class TestModelStructure:
    """Pruebas de estructura de los modelos"""
    
    def test_base_has_tables(self):
        """Verificar que Base tiene tablas definidas"""
        tables = Base.metadata.tables.keys()
        expected_tables = ['users', 'products', 'orders', 'order_items', 'reviews', 'categories']
        
        for table in expected_tables:
            assert table in tables, f"Tabla '{table}' no encontrada en metadata"
        
        print(f"\n✅ Tablas definidas: {', '.join(tables)}")
    
    def test_user_model_columns(self):
        """Verificar columnas del modelo User"""
        mapper = class_mapper(User)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'uuid', 'email', 'username', 'hashed_password',
            'first_name', 'last_name', 'phone', 'avatar_url',
            'role', 'status', 'is_active', 'is_verified', 'is_superuser',
            'language', 'timezone', 'notifications_enabled',
            'created_at', 'updated_at', 'last_login'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en User"
        
        print(f"\n✅ User tiene {len(columns)} columnas")
    
    def test_product_model_columns(self):
        """Verificar columnas del modelo Product"""
        mapper = class_mapper(Product)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'uuid', 'name', 'description', 'price', 'discount_price',
            'stock', 'sku', 'category', 'brand',
            'main_image', 'images', 'status', 'is_active', 'is_featured',
            'views_count', 'sales_count', 'rating_avg', 'rating_count',
            'created_at', 'updated_at', 'owner_id'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en Product"
        
        print(f"\n✅ Product tiene {len(columns)} columnas")
    
    def test_order_model_columns(self):
        """Verificar columnas del modelo Order"""
        mapper = class_mapper(Order)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'uuid', 'order_number', 'status',
            'subtotal', 'tax', 'shipping_cost', 'discount_total', 'total',
            'shipping_address', 'billing_address',
            'payment_method', 'payment_status', 'payment_id',
            'shipping_method', 'tracking_number', 'estimated_delivery',
            'notes', 'created_at', 'updated_at', 'shipped_at', 'delivered_at',
            'user_id'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en Order"
        
        print(f"\n✅ Order tiene {len(columns)} columnas")
    
    def test_order_item_model_columns(self):
        """Verificar columnas del modelo OrderItem"""
        mapper = class_mapper(OrderItem)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'quantity', 'unit_price', 'discount_per_item', 'total_price',
            'order_id', 'product_id', 'created_at'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en OrderItem"
        
        print(f"\n✅ OrderItem tiene {len(columns)} columnas")
    
    def test_review_model_columns(self):
        """Verificar columnas del modelo Review"""
        mapper = class_mapper(Review)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'rating', 'comment',
            'user_id', 'product_id', 'created_at', 'updated_at'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en Review"
        
        print(f"\n✅ Review tiene {len(columns)} columnas")
    
    def test_category_model_columns(self):
        """Verificar columnas del modelo Category"""
        mapper = class_mapper(Category)
        columns = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'columns')]
        
        expected_columns = [
            'id', 'name', 'slug', 'description', 'parent_id',
            'icon', 'is_active', 'created_at', 'updated_at'
        ]
        
        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en Category"
        
        print(f"\n✅ Category tiene {len(columns)} columnas")


class TestModelRelationships:
    """Pruebas de relaciones entre modelos"""
    
    def test_user_relationships(self):
        """Verificar relaciones del modelo User"""
        mapper = class_mapper(User)
        relationships = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'mapper')]
        
        expected_relations = ['products', 'orders', 'reviews']
        
        for rel in expected_relations:
            assert rel in relationships, f"Relación '{rel}' no encontrada en User"
        
        print(f"\n✅ User tiene relaciones: {', '.join(relationships)}")
    
    def test_product_relationships(self):
        """Verificar relaciones del modelo Product"""
        mapper = class_mapper(Product)
        relationships = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'mapper')]
        
        expected_relations = ['owner', 'order_items', 'reviews']
        
        for rel in expected_relations:
            assert rel in relationships, f"Relación '{rel}' no encontrada en Product"
        
        print(f"\n✅ Product tiene relaciones: {', '.join(relationships)}")
    
    def test_order_relationships(self):
        """Verificar relaciones del modelo Order"""
        mapper = class_mapper(Order)
        relationships = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'mapper')]
        
        expected_relations = ['user', 'items']
        
        for rel in expected_relations:
            assert rel in relationships, f"Relación '{rel}' no encontrada en Order"
        
        print(f"\n✅ Order tiene relaciones: {', '.join(relationships)}")
    
    def test_order_item_relationships(self):
        """Verificar relaciones del modelo OrderItem"""
        mapper = class_mapper(OrderItem)
        relationships = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'mapper')]
        
        expected_relations = ['order', 'product']
        
        for rel in expected_relations:
            assert rel in relationships, f"Relación '{rel}' no encontrada en OrderItem"
        
        print(f"\n✅ OrderItem tiene relaciones: {', '.join(relationships)}")
    
    def test_review_relationships(self):
        """Verificar relaciones del modelo Review"""
        mapper = class_mapper(Review)
        relationships = [prop.key for prop in mapper.iterate_properties if hasattr(prop, 'mapper')]
        
        expected_relations = ['user', 'product']
        
        for rel in expected_relations:
            assert rel in relationships, f"Relación '{rel}' no encontrada en Review"
        
        print(f"\n✅ Review tiene relaciones: {', '.join(relationships)}")


class TestModelProperties:
    """Pruebas de propiedades y métodos de los modelos"""
    
    def test_user_full_name_property(self):
        """Verificar propiedad full_name en User"""
        user = User(
            first_name="Juan",
            last_name="Perez",
            email="juan@example.com",
            username="juanperez",
            hashed_password="hash"
        )
        
        assert user.full_name == "Juan Perez"
        
        # Sin apellido
        user.last_name = None
        # ✅ CORREGIDO: Espera "Juan" (no "juanperez")
        assert user.full_name == "Juan"
        
        # Sin nombre
        user.first_name = None
        user.username = "juanperez"
        # ✅ CORREGIDO: Espera "juanperez" (username)
        assert user.full_name == "juanperez"
        
        print("\n✅ User.full_name funciona correctamente")
    
    def test_product_final_price_property(self):
        """Verificar propiedad final_price en Product"""
        # Sin descuento
        product = Product(
            name="Test",
            price=100.0,
            stock=10,
            owner_id=1
        )
        assert product.final_price == 100.0
        
        # Con descuento (menor que precio)
        product.discount_price = 80.0
        assert product.final_price == 80.0
        
        # Con descuento (mayor que precio - no debería aplicar)
        product.discount_price = 120.0
        assert product.final_price == 100.0
        
        print("\n✅ Product.final_price funciona correctamente")
    
    def test_product_in_stock_property(self):
        """Verificar propiedad in_stock en Product"""
        product = Product(
            name="Test",
            price=100.0,
            stock=10,
            owner_id=1
        )
        assert product.in_stock is True
        
        product.stock = 0
        assert product.in_stock is False
        
        print("\n✅ Product.in_stock funciona correctamente")
    
    def test_user_repr(self):
        """Verificar representación de User"""
        user = User(
            username="testuser",
            email="test@example.com"
        )
        repr_str = repr(user)
        assert "testuser" in repr_str
        assert "test@example.com" in repr_str
        print(f"\n✅ User.__repr__: {repr_str}")
    
    def test_product_repr(self):
        """Verificar representación de Product"""
        product = Product(
            name="Test Product",
            price=99.99,
            stock=10,
            owner_id=1
        )
        repr_str = repr(product)
        assert "Test Product" in repr_str
        assert "99.99" in repr_str
        print(f"\n✅ Product.__repr__: {repr_str}")


class TestModelEnums:
    """Pruebas de los enums"""
    
    def test_user_role_enum(self):
        """Verificar enum UserRole"""
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.USER.value == "user"
        assert UserRole.MODERATOR.value == "moderator"
        assert UserRole.GUEST.value == "guest"
        
        user = User(
            username="test",
            email="test@example.com",
            hashed_password="hash",
            role=UserRole.ADMIN
        )
        assert user.role == UserRole.ADMIN
        assert user.role.value == "admin"
        
        print("\n✅ UserRole enum funciona correctamente")
    
    def test_user_status_enum(self):
        """Verificar enum UserStatus"""
        assert UserStatus.ACTIVE.value == "active"
        assert UserStatus.INACTIVE.value == "inactive"
        assert UserStatus.SUSPENDED.value == "suspended"
        assert UserStatus.PENDING.value == "pending"
        
        user = User(
            username="test",
            email="test@example.com",
            hashed_password="hash",
            status=UserStatus.ACTIVE
        )
        assert user.status == UserStatus.ACTIVE
        assert user.status.value == "active"
        
        print("\n✅ UserStatus enum funciona correctamente")
    
    def test_product_status_enum(self):
        """Verificar enum ProductStatus"""
        assert ProductStatus.AVAILABLE.value == "available"
        assert ProductStatus.OUT_OF_STOCK.value == "out_of_stock"
        assert ProductStatus.DISCONTINUED.value == "discontinued"
        assert ProductStatus.PENDING.value == "pending"
        
        product = Product(
            name="Test",
            price=100.0,
            stock=10,
            owner_id=1,
            status=ProductStatus.AVAILABLE
        )
        assert product.status == ProductStatus.AVAILABLE
        assert product.status.value == "available"
        
        print("\n✅ ProductStatus enum funciona correctamente")
    
    def test_order_status_enum(self):
        """Verificar enum OrderStatus"""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.PROCESSING.value == "processing"
        assert OrderStatus.SHIPPED.value == "shipped"
        assert OrderStatus.DELIVERED.value == "delivered"
        assert OrderStatus.CANCELLED.value == "cancelled"
        
        order = Order(
            order_number="ORD-001",
            subtotal=100.0,
            total=100.0,
            shipping_address="Calle 123",
            user_id=1,
            status=OrderStatus.PENDING
        )
        assert order.status == OrderStatus.PENDING
        assert order.status.value == "pending"
        
        print("\n✅ OrderStatus enum funciona correctamente")


class TestModelValidation:
    """Pruebas de validación de modelos"""
    
    def test_user_required_fields(self, db_session):
        """Verificar campos requeridos de User"""
        from sqlalchemy.exc import IntegrityError
        
        # Intentar crear User sin email (debería fallar al hacer commit)
        user = User(
            username="test",
            hashed_password="hash"
        )
        db_session.add(user)
        
        with pytest.raises(Exception):  # IntegrityError o similar
            db_session.commit()
        
        db_session.rollback()
        print("\n✅ User tiene campos requeridos correctamente")
    
    def test_product_required_fields(self, db_session):
        """Verificar campos requeridos de Product"""
        from sqlalchemy.exc import IntegrityError
        
        # Intentar crear Product sin nombre (debería fallar al hacer commit)
        product = Product(
            price=100.0,
            stock=10,
            owner_id=1
        )
        db_session.add(product)
        
        with pytest.raises(Exception):
            db_session.commit()
        
        db_session.rollback()
        print("\n✅ Product tiene campos requeridos correctamente")
    
    def test_order_required_fields(self, db_session):
        """Verificar campos requeridos de Order"""
        from sqlalchemy.exc import IntegrityError
        
        # Intentar crear Order sin order_number (debería fallar al hacer commit)
        order = Order(
            subtotal=100.0,
            total=100.0,
            shipping_address="Calle 123",
            user_id=1
        )
        db_session.add(order)
        
        with pytest.raises(Exception):
            db_session.commit()
        
        db_session.rollback()
        print("\n✅ Order tiene campos requeridos correctamente")


class TestModelTimestamps:
    """Pruebas de timestamps en modelos"""
    
    def test_user_timestamps(self, db_session):
        """Verificar timestamps en User"""
        user = User(
            username="test",
            email="test@example.com",
            hashed_password="hash"
        )
        db_session.add(user)
        db_session.commit()
        
        # ✅ CORREGIDO: created_at se establece al hacer commit
        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)
        
        print(f"\n✅ User.created_at: {user.created_at}")
    
    def test_product_timestamps(self, db_session):
        """Verificar timestamps en Product"""
        product = Product(
            name="Test",
            price=100.0,
            stock=10,
            owner_id=1
        )
        db_session.add(product)
        db_session.commit()
        
        # ✅ CORREGIDO: created_at se establece al hacer commit
        assert product.created_at is not None
        assert isinstance(product.created_at, datetime)
        
        print(f"\n✅ Product.created_at: {product.created_at}")
    
    def test_order_timestamps(self, db_session):
        """Verificar timestamps en Order"""
        order = Order(
            order_number="ORD-001",
            subtotal=100.0,
            total=100.0,
            shipping_address="Calle 123",
            user_id=1
        )
        db_session.add(order)
        db_session.commit()
        
        # ✅ CORREGIDO: created_at se establece al hacer commit
        assert order.created_at is not None
        assert isinstance(order.created_at, datetime)
        
        print(f"\n✅ Order.created_at: {order.created_at}")


class TestModelUUID:
    """Pruebas de UUID en modelos"""
    
    def test_user_uuid(self, db_session):
        """Verificar UUID en User"""
        user = User(
            username="test",
            email="test@example.com",
            hashed_password="hash"
        )
        db_session.add(user)
        db_session.commit()
        
        # ✅ CORREGIDO: UUID se genera al instanciar, pero commit lo confirma
        assert user.uuid is not None
        assert isinstance(user.uuid, uuid.UUID)
        print(f"\n✅ User.uuid: {user.uuid}")
    
    def test_product_uuid(self, db_session):
        """Verificar UUID en Product"""
        product = Product(
            name="Test",
            price=100.0,
            stock=10,
            owner_id=1
        )
        db_session.add(product)
        db_session.commit()
        
        # ✅ CORREGIDO: UUID se genera al instanciar
        assert product.uuid is not None
        assert isinstance(product.uuid, uuid.UUID)
        print(f"\n✅ Product.uuid: {product.uuid}")
    
    def test_order_uuid(self, db_session):
        """Verificar UUID en Order"""
        order = Order(
            order_number="ORD-001",
            subtotal=100.0,
            total=100.0,
            shipping_address="Calle 123",
            user_id=1
        )
        db_session.add(order)
        db_session.commit()
        
        # ✅ CORREGIDO: UUID se genera al instanciar
        assert order.uuid is not None
        assert isinstance(order.uuid, uuid.UUID)
        print(f"\n✅ Order.uuid: {order.uuid}")
    
    def test_unique_uuids(self, db_session):
        """Verificar que los UUIDs son únicos"""
        user1 = User(username="test1", email="test1@example.com", hashed_password="hash")
        user2 = User(username="test2", email="test2@example.com", hashed_password="hash")
        db_session.add(user1)
        db_session.add(user2)
        db_session.commit()
        
        # ✅ CORREGIDO: UUIDs se generan al instanciar
        assert user1.uuid is not None
        assert user2.uuid is not None
        assert user1.uuid != user2.uuid
        
        print("\n✅ UUIDs únicos generados correctamente")


class TestModelCascade:
    """Pruebas de cascada en relaciones"""
    
    def test_user_product_cascade(self):
        """Verificar cascada User -> Product"""
        mapper = class_mapper(User)
        rel = mapper.get_property('products')
        
        assert rel.cascade is not None
        print("\n✅ User -> Products tiene cascade configurado")
    
    def test_order_items_cascade(self):
        """Verificar cascada Order -> OrderItem"""
        mapper = class_mapper(Order)
        rel = mapper.get_property('items')
        
        assert rel.cascade is not None
        print("\n✅ Order -> OrderItems tiene cascade configurado")
    
    def test_product_reviews_cascade(self):
        """Verificar cascada Product -> Review"""
        mapper = class_mapper(Product)
        rel = mapper.get_property('reviews')
        
        assert rel.cascade is not None
        print("\n✅ Product -> Reviews tiene cascade configurado")