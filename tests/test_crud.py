"""
Pruebas para operaciones CRUD
"""

import pytest
from sqlalchemy.exc import IntegrityError
from api.crud import (
    CRUDUser, CRUDProduct, CRUDOrder, CRUDReview, CRUDCategory
)
from api.schemas import (
    UserCreate, UserUpdate,
    ProductCreate, ProductUpdate,
    OrderCreate, OrderItemCreate,
    ReviewCreate,
    CategoryCreate
)
from api.models import UserRole, UserStatus, ProductStatus, OrderStatus

class TestCRUDUser:
    """Pruebas para CRUD de usuarios"""
    
    def test_create_user(self, db_session):
        """Crear usuario"""
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="Test123!@#",
            first_name="Test",
            last_name="User"
        )
        user = CRUDUser.create(db_session, user_data)
        
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.role == UserRole.USER
        # Los usuarios nacen ACTIVE: antes eran PENDING esperando una
        # verificación de email que nunca se enviaba.
        assert user.status == UserStatus.ACTIVE
    
    def test_create_user_duplicate_email(self, db_session, test_user):
        """Intentar crear usuario con email duplicado"""
        user_data = UserCreate(
            email="test@example.com",  # Mismo email que test_user
            username="anotheruser",
            password="Test123!@#"
        )
        
        with pytest.raises(ValueError) as exc_info:
            CRUDUser.create(db_session, user_data)
        assert "ya está registrado" in str(exc_info.value)
    
    def test_get_user_by_id(self, db_session, test_user):
        """Obtener usuario por ID"""
        user = CRUDUser.get_by_id(db_session, test_user.id)
        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email
    
    def test_get_user_by_email(self, db_session, test_user):
        """Obtener usuario por email"""
        user = CRUDUser.get_by_email(db_session, "test@example.com")
        assert user is not None
        assert user.id == test_user.id
    
    def test_update_user(self, db_session, test_user):
        """Actualizar usuario"""
        update_data = UserUpdate(
            first_name="Updated",
            last_name="Name",
            phone="123456789"
        )
        user = CRUDUser.update(db_session, test_user.id, update_data)
        
        assert user.first_name == "Updated"
        assert user.last_name == "Name"
        assert user.phone == "123456789"
    
    def test_authenticate_user(self, db_session, test_user):
        """Autenticar usuario"""
        user = CRUDUser.authenticate(
            db_session,
            "test@example.com",
            "Test123!@#"
        )
        assert user is not None
        assert user.id == test_user.id
        
        # Credenciales incorrectas
        user = CRUDUser.authenticate(
            db_session,
            "test@example.com",
            "WrongPassword"
        )
        assert user is None

class TestCRUDProduct:
    """Pruebas para CRUD de productos"""
    
    def test_create_product(self, db_session, test_user):
        """Crear producto"""
        product_data = ProductCreate(
            name="Test Product",
            description="Test Description",
            price=99.99,
            stock=10,
            sku="TEST-001",
            category="Electronics",
            brand="Test Brand",
            owner_id=test_user.id
        )
        product = CRUDProduct.create(db_session, product_data)
        
        assert product.id is not None
        assert product.name == "Test Product"
        assert product.price == 99.99
        assert product.stock == 10
        assert product.owner_id == test_user.id
    
    def test_update_stock(self, db_session, test_product):
        """Actualizar stock"""
        product = CRUDProduct.update_stock(db_session, test_product.id, 5)
        assert product.stock == 15
        
        # Verificar que no permite stock negativo
        with pytest.raises(ValueError):
            CRUDProduct.update_stock(db_session, test_product.id, -100)
    
    def test_get_products_with_filters(self, db_session, test_product):
        """Obtener productos con filtros"""
        products = CRUDProduct.get_all(
            db_session,
            category="Electrónicos",
            min_price=50,
            max_price=150
        )
        assert len(products) >= 1
        assert products[0].category == "Electrónicos"
    
    def test_update_rating(self, db_session, test_product):
        """Actualizar rating del producto"""
        product = CRUDProduct.update_rating(db_session, test_product.id)
        assert product.rating_avg == 0
        assert product.rating_count == 0

class TestCRUDOrder:
    """Pruebas para CRUD de órdenes"""
    
    def test_create_order(self, db_session, test_user, test_product):
        """Crear orden"""
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
        
        assert order.id is not None
        assert order.order_number.startswith("ORD-")
        assert order.user_id == test_user.id
        assert order.status == OrderStatus.PENDING
        assert order.total > 0
        assert len(order.items) == 1
    
    def test_update_order_status(self, db_session, test_order):
        """Actualizar estado de orden"""
        order = CRUDOrder.update_status(
            db_session,
            test_order.id,
            OrderStatus.PROCESSING
        )
        assert order.status == OrderStatus.PROCESSING
    
    def test_cancel_order(self, db_session, test_order):
        """Cancelar orden"""
        order = CRUDOrder.cancel(db_session, test_order.id)
        assert order.status == OrderStatus.CANCELLED