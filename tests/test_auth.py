"""
Pruebas para el módulo de autenticación
"""

import pytest
from datetime import datetime, timedelta
from jose import jwt
from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    refresh_access_token,
    hash_password,
    verify_password,
    validate_password_strength,
    get_current_user,
)
from api.config import config
from api.models import UserRole

def test_hash_password():
    """Probar hashing de contraseñas"""
    password = "Test123!@#"
    hashed = hash_password(password)
    
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword", hashed)

def test_validate_password_strength():
    """Probar validación de fortaleza de contraseña"""
    # Contraseñas válidas
    assert validate_password_strength("Test123!@#")
    assert validate_password_strength("StrongP@ssw0rd")
    assert validate_password_strength("C0mpl3x!Password")
    
    # Contraseñas inválidas
    assert not validate_password_strength("weak")
    assert not validate_password_strength("alllowercase")
    assert not validate_password_strength("NONUMBERS")
    assert not validate_password_strength("NoSpecial1")

def test_create_access_token():
    """Probar creación de access token"""
    data = {"sub": "1", "email": "test@example.com", "role": "user"}
    token = create_access_token(data)
    
    assert token is not None
    assert isinstance(token, str)
    
    # Decodificar y verificar
    decoded = decode_token(token)
    assert decoded["sub"] == "1"
    assert decoded["email"] == "test@example.com"
    assert decoded["type"] == "access"

def test_create_refresh_token():
    """Probar creación de refresh token"""
    data = {"sub": "1", "email": "test@example.com"}
    token = create_refresh_token(data)
    
    assert token is not None
    assert isinstance(token, str)
    
    decoded = decode_token(token)
    assert decoded["type"] == "refresh"

def test_token_expiration():
    """
    Probar expiración de tokens.

    Antes creaba un token de 1 segundo y hacía `time.sleep(2)`, lo que añadía
    2 segundos a cada ejecución de la suite. Basta con emitir el token ya
    caducado (delta negativo): se comprueba exactamente lo mismo sin esperar.
    """
    data = {"sub": "1"}
    token = create_access_token(data, expires_delta=timedelta(seconds=-1))

    with pytest.raises(Exception):
        verify_token(token, "access")

def test_refresh_access_token():
    """Probar refresco de access token"""
    refresh_data = {
        "sub": "1",
        "email": "test@example.com",
        "role": "user"
    }
    refresh_token = create_refresh_token(refresh_data)
    
    result = refresh_access_token(refresh_token)
    assert "access_token" in result
    assert result["token_type"] == "bearer"
    
    # Verificar que el nuevo token es válido
    new_token = result["access_token"]
    decoded = decode_token(new_token)
    assert decoded["type"] == "access"
    assert decoded["sub"] == "1"

def test_invalid_token():
    """Probar tokens inválidos"""
    with pytest.raises(Exception):
        decode_token("invalid.token.here")
    
    with pytest.raises(Exception):
        verify_token("invalid.token.here", "access")