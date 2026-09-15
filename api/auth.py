"""
Módulo de autenticación y autorización
Maneja JWT tokens, verificación de permisos y seguridad
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import logging
import secrets
from passlib.context import CryptContext

from api.config import config
from api.database import get_db
from api.models import User, UserRole, UserStatus
from api.crud import CRUDUser



# Configurar logger
logger = logging.getLogger(__name__)

# Contexto para hash de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================================
# CONFIGURACIÓN DE TOKENS
# ============================================



# Configuración JWT
SECRET_KEY = config.SECRET_KEY
ALGORITHM = config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = config.REFRESH_TOKEN_EXPIRE_DAYS

# ============================================
# FUNCIONES DE TOKENS
# ============================================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Crear un token de acceso JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        # Identificador único del token: evita que dos tokens emitidos en el mismo
        # segundo (misma exp/iat) sean byte a byte idénticos.
        "jti": secrets.token_hex(16),
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Crear un token de refresco JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        # Identificador único: hace que la rotación del refresh token genere
        # siempre un token distinto aunque se pida dentro del mismo segundo.
        "jti": secrets.token_hex(16),
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodificar y validar un token JWT
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Error decodificando token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Verificar un token JWT (acceso o refresco)
    """
    payload = decode_token(token)
    
    # Verificar tipo de token
    if payload.get("type") != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: se esperaba {token_type}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verificar que el token no haya expirado
    exp = payload.get("exp")
    if exp and datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload

def refresh_access_token(refresh_token: str) -> Dict[str, str]:
    """
    Generar un nuevo par de tokens (access + refresh) a partir de un refresh token.

    Se emite también un refresh token nuevo (rotación): antes se devolvía solo el
    de acceso y el router reutilizaba el antiguo, de modo que un refresh token
    robado servía indefinidamente hasta su caducidad.
    """
    payload = verify_token(refresh_token, token_type="refresh")
    
    # Extraer datos del usuario del payload
    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido",
        )
    
    # Datos para los nuevos tokens
    token_data = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "user_id": payload.get("user_id", user_id),
    }
    
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }

# ============================================
# DEPENDENCIAS DE AUTENTICACIÓN
# ============================================

def _no_autenticado(detail: str = "No autenticado") -> HTTPException:
    """
    Error 401 uniforme para credenciales ausentes o inválidas.

    Incluye `WWW-Authenticate: Bearer`, que es lo que espera un cliente HTTP
    para saber que debe autenticarse.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class TokenBearer(HTTPBearer):
    """
    Dependencia para obtener y validar el token Bearer.

    Devuelve 401 (no autenticado), no 403. El 403 significa que el cliente SÍ
    está identificado pero no tiene permiso; para una credencial ausente o
    inválida lo correcto es 401 con la cabecera `WWW-Authenticate: Bearer`.

    Se normaliza aquí a propósito porque `HTTPBearer` de Starlette ha devuelto
    403 en unas versiones y 401 en otras: sin esto, la respuesta de la API
    dependía de la versión instalada (se detectó justo así, con la suite pasando
    en local y fallando con los pins de requirements.txt).
    """
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        try:
            credentials = await super().__call__(request)
        except HTTPException as e:
            raise _no_autenticado() from e

        if not credentials:
            raise _no_autenticado()

        if credentials.scheme != "Bearer":
            raise _no_autenticado("Esquema de autenticación inválido. Use Bearer")

        return credentials

# Instancia del bearer token
token_bearer = TokenBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(token_bearer),
    db: Session = Depends(get_db)
) -> User:
    """
    Obtener el usuario actual a partir del token JWT
    """
    token = credentials.credentials
    
    try:
        payload = verify_token(token, token_type="access")
        
        user_id = payload.get("sub")
        email = payload.get("email")
        
        if not user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: datos incompletos",
            )
        
        # Obtener usuario de la base de datos
        user = CRUDUser.get_by_id(db, int(user_id))
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo",
            )
        
        return user
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo usuario actual: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error de autenticación",
        )

async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Verificar que el usuario actual esté activo
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )
    return current_user

# ============================================
# DEPENDENCIAS DE PERMISOS (RBAC)
# ============================================

def require_roles(allowed_roles: List[UserRole]):
    """
    Decorador/función para verificar que el usuario tenga uno de los roles permitidos
    """
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere uno de los roles: {[r.value for r in allowed_roles]}",
            )
        return current_user
    return role_checker

def require_permission(permission: str):
    """
    Verificar que el usuario tenga un permiso específico (para sistemas más granulares)
    """
    async def permission_checker(current_user: User = Depends(get_current_active_user)):
        # Aquí se podría implementar un sistema de permisos más granular
        # Por ahora, los admin tienen todos los permisos
        if current_user.role == UserRole.ADMIN:
            return current_user
        
        # Verificar permiso específico (ejemplo)
        # user_permissions = get_user_permissions(current_user.id)
        # if permission not in user_permissions:
        #     raise HTTPException(...)
        
        # Por defecto, solo admin puede hacer todo
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permiso '{permission}' denegado",
        )
    return permission_checker

# ============================================
# DEPENDENCIAS DE OWNERSHIP
# ============================================

async def check_ownership(
    resource_id: int,
    resource_type: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> bool:
    """
    Verificar que el usuario sea propietario de un recurso
    """
    # Si es admin, tiene acceso a todo
    if current_user.role == UserRole.ADMIN:
        return True
    
    # Verificar según el tipo de recurso
    if resource_type == "user":
        return current_user.id == resource_id
    
    elif resource_type == "product":
        from api.crud import CRUDProduct
        product = CRUDProduct.get_by_id(db, resource_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado",
            )
        return product.owner_id == current_user.id
    
    elif resource_type == "order":
        from api.crud import CRUDOrder
        order = CRUDOrder.get_by_id(db, resource_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orden no encontrada",
            )
        return order.user_id == current_user.id
    
    elif resource_type == "review":
        from api.crud import CRUDReview
        review = CRUDReview.get_by_id(db, resource_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reseña no encontrada",
            )
        return review.user_id == current_user.id
    
    return False

def require_owner(resource_type: str, resource_id_param: str = "id"):
    """
    Dependencia para verificar que el usuario sea propietario del recurso.

    Igual que `owner_or_admin_required`, el id se lee de la ruta en tiempo de
    petición para no generar un parámetro de query fantasma.
    """
    async def owner_checker(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        resource_id = _extract_resource_id(request, resource_type)

        has_ownership = await check_ownership(resource_id, resource_type, current_user, db)
        
        if not has_ownership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No eres propietario de este {resource_type}",
            )
        
        return current_user
    return owner_checker

# ============================================
# TOKENS DE RESETEO DE CONTRASEÑA
# ============================================
# Nota: aquí vivían también los ayudantes de verificación de email
# (`generate_verification_token`, `create_verification_token`,
# `verify_verification_token`) y `generate_password_reset_token`. Se han
# retirado: el token de verificación no se enviaba nunca (no hay SMTP), así que
# el flujo estaba a medias y nadie podía completarlo.

def create_password_reset_token(user_id: int, email: str) -> str:
    """
    Crear token JWT para reseteo de contraseña
    """
    data = {
        "sub": str(user_id),
        "email": email,
        "type": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hora
    }
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def verify_password_reset_token(token: str) -> Dict[str, Any]:
    """
    Verificar token de reseteo de contraseña
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido",
            )
        
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado",
        )

# ============================================
# MIDDLEWARES Y UTILIDADES
# ============================================

class AuthMiddleware:
    """
    Middleware para logging de autenticación
    """
    @staticmethod
    async def log_auth_attempt(request: Request, success: bool, user: Optional[User] = None):
        """
        Registrar intentos de autenticación
        """
        client_ip = request.client.host if request.client else "unknown"
        
        if success:
            logger.info(f"Auth exitosa - IP: {client_ip}, Usuario: {user.email if user else 'unknown'}")
        else:
            logger.warning(f"Auth fallida - IP: {client_ip}")

# ============================================
# UTILIDADES DE PASSWORD
# ============================================

def hash_password(password: str) -> str:
    """
    Hashear una contraseña
    """
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verificar una contraseña
    """
    return pwd_context.verify(plain_password, hashed_password)

def validate_password_strength(password: str) -> bool:
    """
    Validar la fortaleza de una contraseña.

    Delega en `api.schemas.validar_fortaleza_password`, que es la definición
    ÚNICA de la política (la usan también los esquemas de registro, cambio de
    contraseña y reseteo). Antes esta función existía aquí pero no la llamaba
    nadie, así que `change-password` aceptaba contraseñas como "1".
    """
    from api.schemas import validar_fortaleza_password
    try:
        validar_fortaleza_password(password)
        return True
    except ValueError:
        return False

# ============================================
# DEPENDENCIAS DE PERMISOS PREDEFINIDOS
# ============================================

# Dependencias predefinidas para roles comunes
is_admin = require_roles([UserRole.ADMIN])
is_moderator = require_roles([UserRole.ADMIN, UserRole.MODERATOR])
is_user = require_roles([UserRole.ADMIN, UserRole.USER, UserRole.MODERATOR])
is_authenticated = get_current_active_user

# ============================================
# DECORADORES PARA RUTAS
# ============================================

def auth_required():
    """
    Decorador para requerir autenticación
    """
    return get_current_active_user

def admin_required():
    """
    Decorador para requerir rol de administrador
    """
    return require_roles([UserRole.ADMIN])

def moderator_required():
    """
    Decorador para requerir rol de moderador o administrador
    """
    return require_roles([UserRole.ADMIN, UserRole.MODERATOR])

def _extract_resource_id(request: Request, resource_type: str) -> int:
    """
    Obtiene el id del recurso desde los parámetros de ruta reales de la petición.

    A propósito NO se declara como parámetro de la dependencia: si se declarara
    (por ejemplo `resource_id: int`), FastAPI lo interpretaría como un parámetro
    de *query* obligatorio en todas las rutas, porque cada router nombra el suyo
    `product_id`, `order_id` o `review_id`. El resultado era un 422 en todos los
    endpoints protegidos con `owner_or_admin_required`.
    """
    path_params = request.path_params

    candidatos = [f"{resource_type}_id", "resource_id", "id"]
    candidatos += [clave for clave in path_params if clave.endswith("_id")]

    for clave in candidatos:
        if clave in path_params:
            try:
                return int(path_params[clave])
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Identificador inválido en la ruta: {clave}={path_params[clave]!r}",
                )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"No se encontró el identificador de '{resource_type}' en la ruta.",
    )


def owner_or_admin_required(resource_type: str):
    """
    Decorador para requerir ser propietario o administrador
    """
    async def checker(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        # Admin tiene acceso total
        if current_user.role == UserRole.ADMIN:
            return current_user

        resource_id = _extract_resource_id(request, resource_type)

        # Verificar propiedad
        has_ownership = await check_ownership(resource_id, resource_type, current_user, db)

        if not has_ownership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder a este recurso",
            )

        return current_user
    return checker

# ============================================
# EXPORTAR TODO
# ============================================

__all__ = [
    # Funciones de tokens
    'create_access_token',
    'create_refresh_token',
    'decode_token',
    'verify_token',
    'refresh_access_token',
    
    # Dependencias de autenticación
    'token_bearer',
    'get_current_user',
    'get_current_active_user',
    
    # Dependencias de permisos
    'require_roles',
    'require_permission',
    'check_ownership',
    'require_owner',
    
    # Tokens de reseteo de contraseña
    'create_password_reset_token',
    'verify_password_reset_token',
    
    # Utilidades de password
    'hash_password',
    'verify_password',
    'validate_password_strength',
    
    # Dependencias predefinidas
    'is_admin',
    'is_moderator',
    'is_user',
    'is_authenticated',
    
    # Decoradores
    'auth_required',
    'admin_required',
    'moderator_required',
    'owner_or_admin_required',
    
    # Middleware
    'AuthMiddleware',
]