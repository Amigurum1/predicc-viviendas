"""
Pruebas de integración de la API
"""

import pytest
from fastapi import status

class TestAuthEndpoints:
    """Pruebas de endpoints de autenticación"""
    
    def test_register_user(self, client):
        """Registrar usuario"""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "Test123!@#",
                "first_name": "New",
                "last_name": "User"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["username"] == "newuser"
    
    def test_login_user(self, client, test_user):
        """Login de usuario"""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "test@example.com",
                "password": "Test123!@#"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_wrong_password(self, client, test_user):
        """Login con contraseña incorrecta"""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "test@example.com",
                "password": "WrongPassword"
            }
        )
        assert response.status_code == 401

class TestUserEndpoints:
    """Pruebas de endpoints de usuarios"""
    
    def test_get_me(self, client, auth_headers):
        """Obtener perfil propio"""
        response = client.get("/api/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
    
    def test_update_profile(self, client, auth_headers):
        """Actualizar perfil"""
        response = client.put(
            "/api/users/me",
            headers=auth_headers,
            json={
                "first_name": "Updated",
                "phone": "987654321"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
    
    def test_unauthorized_access(self, client):
        """Acceso sin autenticación"""
        response = client.get("/api/users/me")
        assert response.status_code == 401

class TestProductEndpoints:
    """Pruebas de endpoints de productos"""
    
    def test_create_product(self, client, auth_headers):
        """Crear producto"""
        response = client.post(
            "/api/products/",
            headers=auth_headers,
            json={
                "name": "API Test Product",
                "description": "Created from API test",
                "price": 199.99,
                "stock": 20,
                "sku": "API-TEST-001",
                "category": "Electronics",
                "brand": "API Brand"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Test Product"
        assert data["price"] == 199.99
    
    def test_get_products(self, client):
        """Obtener lista de productos"""
        response = client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_product_detail(self, client, test_product):
        """Obtener detalle de producto"""
        response = client.get(f"/api/products/{test_product.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_product.id
        assert data["name"] == test_product.name

class TestHealthCheck:
    """Pruebas de health check"""
    
    def test_health_endpoint(self, client):
        """Verificar health check"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"