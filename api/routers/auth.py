
"""
Router de autenticación
Endpoints para login, registro y refresh de tokens
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
import logging

from api.database import get_db
from api.crud import CRUDUser
from api.schemas import (
    UserCreate,
    UserResponse,
    UserLogin,
    UserTokenResponse,
    UserRefreshToken,
    UserSelfUpdate,
    PasswordChangeRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse
)
from api.auth import (
    create_access_token,
    create_refresh_token,
    refresh_access_token,
    get_current_active_user,
    verify_password
)
from api.models import User
from api.config import config

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/auth",
    tags=["autenticación"]
)


# ============================================
# ENDPOINTS DE AUTENTICACIÓN
# ============================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo usuario",
    description="Crea una nueva cuenta de usuario"
)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Registrar un nuevo usuario en el sistema.
    
    - **email**: Email único del usuario
    - **username**: Nombre de usuario único
    - **password**: Contraseña (mínimo 8 caracteres)
    - **first_name**: Nombre (opcional)
    - **last_name**: Apellido (opcional)
    - **phone**: Teléfono (opcional)
    """
    try:
        # Crear usuario
        user = CRUDUser.create(db, user_data)
        logger.info(f"Usuario registrado: {user.email}")
        return user
    except ValueError as e:
        logger.warning(f"Error en registro: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error inesperado en registro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar usuario"
        )


@router.post(
    "/login",
    response_model=UserTokenResponse,
    summary="Iniciar sesión",
    description="Autentica un usuario y devuelve tokens de acceso"
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> UserTokenResponse:
    """
    Iniciar sesión con email y contraseña.
    
    - **username**: Email del usuario
    - **password**: Contraseña del usuario
    
    Devuelve:
    - **access_token**: Token JWT para autenticación (expira en 30 min)
    - **refresh_token**: Token para renovar el access_token (expira en 7 días)
    - **user**: Datos del usuario autenticado
    """
    try:
        # Autenticar usuario
        user = CRUDUser.authenticate(db, form_data.username, form_data.password)
        
        if not user:
            # Cubre los tres casos: email inexistente, contraseña incorrecta y
            # usuario inactivo. `CRUDUser.authenticate` devuelve None en los tres
            # a propósito, para no revelar si una cuenta existe.
            #
            # Aquí había además un `if not user.is_active: 403` que nunca se
            # ejecutaba, porque un usuario inactivo ya ha salido por esta rama.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Crear tokens
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "user_id": user.id
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        logger.info(f"Usuario autenticado: {user.email}")
        
        return UserTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al iniciar sesión"
        )


@router.post(
    "/refresh",
    response_model=UserTokenResponse,
    summary="Renovar token de acceso",
    description="Genera un nuevo par de tokens (access + refresh) usando un refresh_token válido"
)
def refresh(
    refresh_data: UserRefreshToken,
    db: Session = Depends(get_db)
) -> UserTokenResponse:
    """
    Renovar el token de acceso usando un refresh token.
    
    - **refresh_token**: Token de refresco obtenido en el login
    
    Devuelve un nuevo par de tokens (access + refresh) y los datos del usuario.
    El refresh token se rota en cada llamada.
    """
    from api.auth import verify_token
    
    try:
        # Validar el refresh token y obtener el usuario real de la base de datos
        payload = verify_token(refresh_data.refresh_token, token_type="refresh")
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido: no contiene el usuario",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = CRUDUser.get_by_id(db, int(user_id))
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El usuario del token ya no existe",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo. Contacte al administrador."
            )
        
        # Generar el nuevo par de tokens
        result = refresh_access_token(refresh_data.refresh_token)
        
        logger.info(f"Tokens renovados para: {user.email}")
        
        return UserTokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type="bearer",
            user=user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado"
        )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Cerrar sesión",
    description="Invalida el token actual (cliente debe eliminar el token localmente)"
)
def logout(
    current_user: User = Depends(get_current_active_user)
) -> MessageResponse:
    """
    Cerrar sesión del usuario actual.
    
    Nota: El servidor no almacena tokens, por lo que este endpoint es informativo.
    El cliente debe eliminar los tokens almacenados localmente.
    """
    logger.info(f"Usuario cerró sesión: {current_user.email}")
    return MessageResponse(
        message="Sesión cerrada correctamente",
        success=True
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener perfil propio",
    description="Devuelve los datos del usuario autenticado"
)
def get_me(
    current_user: User = Depends(get_current_active_user)
) -> UserResponse:
    """
    Obtener información del usuario autenticado.
    """
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Actualizar perfil propio",
    description=(
        "Actualiza los datos del usuario autenticado. Todos los campos son "
        "opcionales. NO se puede cambiar el rol ni el estado de la cuenta: solo "
        "un administrador puede hacerlo."
    )
)
def update_me(
    user_data: UserSelfUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Actualizar los datos del usuario autenticado.

    - **first_name** / **last_name** / **phone**: opcionales
    - **email** / **username**: opcionales (se comprueba que no estén en uso)
    - **password**: opcional (debe cumplir la política)

    Antes recibía `UserCreate`, así que había que reenviar email, username y
    contraseña completos para cambiar solo el nombre; y como `UserCreate`
    heredaba `role`, se podía escalar a administrador desde aquí.
    """
    try:
        user = CRUDUser.update(db, current_user.id, user_data)
        logger.info(f"Perfil actualizado: {user.email}")
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error actualizando perfil: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar perfil"
        )


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Cambiar contraseña",
    description=(
        "Cambia la contraseña del usuario autenticado. Las contraseñas viajan en "
        "el CUERPO de la petición, nunca en la URL."
    )
)
def change_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Cambiar la contraseña del usuario autenticado.

    - **old_password**: Contraseña actual
    - **new_password**: Nueva contraseña, debe cumplir la política (8+, mayúscula,
      minúscula, número y carácter especial)

    Antes eran parámetros sueltos, así que acababan en el query string: quedaban
    escritos en el log de accesos de uvicorn, en el middleware de logging de la
    aplicación y en el historial del navegador.
    """
    try:
        user = CRUDUser.change_password(
            db,
            current_user.id,
            data.old_password,
            data.new_password
        )
        logger.info(f"Contraseña cambiada para: {user.email}")
        return MessageResponse(
            message="Contraseña cambiada correctamente",
            success=True
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cambiando contraseña: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar contraseña"
        )


# ============================================
# RESETEO DE CONTRASEÑA
# ============================================
# Nota: aquí estaba el endpoint `GET /verify-email/{token}`. Se ha retirado
# junto con el resto del flujo de verificación de email: el token no se enviaba
# nunca (no hay SMTP), así que era un endpoint imposible de usar en la práctica.
# El campo `is_verified` de la tabla se conserva como reservado.

@router.post(
    "/request-password-reset",
    response_model=MessageResponse,
    summary="Solicitar reseteo de contraseña",
    description="Envía un email con el token para resetear la contraseña"
)
def request_password_reset(
    data: PasswordResetRequest,
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Solicitar reseteo de contraseña.

    - **email**: Email del usuario registrado

    El token solo se devuelve en la respuesta en entorno de desarrollo (no hay
    envío de emails implementado). En producción NUNCA se incluye: hacerlo
    permitiría a cualquiera con el email de la víctima cambiarle la contraseña.
    """
    from api.auth import create_password_reset_token
    from api.config import config

    try:
        user = CRUDUser.get_by_email(db, data.email)
        if not user:
            # No revelar si el email existe o no por seguridad
            return MessageResponse(
                message="Si el email está registrado, recibirás un enlace de reseteo",
                success=True
            )

        # Crear token de reseteo (en producción, enviar por email)
        token = create_password_reset_token(user.id, user.email)
        logger.info(f"Token de reseteo generado para: {user.email}")

        if config.ENVIRONMENT == "production":
            logger.warning(
                "⚠️ Reseteo solicitado en producción pero el envío de emails no está "
                "implementado: el usuario no recibirá el enlace."
            )
            return MessageResponse(
                message="Si el email está registrado, recibirás un enlace de reseteo",
                success=True
            )

        # Solo en desarrollo/pruebas, para poder probar el flujo sin SMTP.
        logger.warning(
            "⚠️ Devolviendo el token de reseteo en la respuesta (solo desarrollo)"
        )
        return MessageResponse(
            message="Si el email está registrado, recibirás un enlace de reseteo",
            success=True,
            data={"reset_token": token}  # SOLO desarrollo
        )
    except Exception as e:
        logger.error(f"Error solicitando reseteo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la solicitud"
        )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Resetear contraseña",
    description=(
        "Resetea la contraseña usando un token válido. El token y la contraseña "
        "viajan en el CUERPO de la petición, nunca en la URL."
    )
)
def reset_password(
    data: PasswordResetConfirm,
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Resetear la contraseña.

    - **token**: Token de reseteo recibido por email
    - **new_password**: Nueva contraseña (debe cumplir la política)
    """
    from api.auth import verify_password_reset_token
    from api.schemas import UserUpdate
    
    try:
        payload = verify_password_reset_token(data.token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido"
            )
        
        # Actualizar contraseña
        update_data = UserUpdate(password=data.new_password)
        user = CRUDUser.update(db, int(user_id), update_data)
        
        logger.info(f"Contraseña reseteada para: {user.email}")
        return MessageResponse(
            message="Contraseña actualizada correctamente",
            success=True
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error reseteando contraseña: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado"
        )