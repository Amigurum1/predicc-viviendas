"""
Router de usuarios
Endpoints para la gestión de usuarios (CRUD)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from api.database import get_db
from api.crud import CRUDUser
from api.schemas import (
    UserCreate,
    UserUpdate,
    UserSelfUpdate,
    UserResponse,
    MessageResponse,
    PaginationParams,
    FilterParams
)
from api.auth import (
    get_current_active_user,
    get_current_user,
    is_admin,
    is_moderator,
    owner_or_admin_required
)
from api.models import User, UserRole, UserStatus

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/users",
    tags=["usuarios"]
)


# ============================================
# ENDPOINTS PÚBLICOS (requieren autenticación)
# ============================================

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
    
    - **Requiere**: Autenticación
    - **Retorna**: Datos completos del usuario
    """
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Actualizar perfil propio",
    description=(
        "Actualiza los datos del usuario autenticado. NO se puede cambiar el rol "
        "ni el estado de la cuenta: solo un administrador puede hacerlo."
    )
)
def update_me(
    user_data: UserSelfUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Actualizar los datos del usuario autenticado.

    - **Requiere**: Autenticación
    - **Campos actualizables**:
        - first_name / last_name / phone
        - email / username (se comprueba que no estén en uso)
        - password (debe cumplir la política)
        - language / timezone / notifications_enabled

    Antes usaba `UserUpdate`, que incluye `role`, `status`, `is_active` e
    `is_verified`: un usuario podía ascenderse a administrador o desactivar su
    cuenta desde aquí.
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


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Eliminar cuenta propia",
    description="Elimina la cuenta del usuario autenticado (soft delete)"
)
def delete_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar la cuenta del usuario autenticado.
    
    - **Requiere**: Autenticación
    - **Nota**: Es un soft delete (el usuario se desactiva)
    """
    try:
        CRUDUser.delete(db, current_user.id, soft=True)
        logger.info(f"Usuario eliminó su cuenta: {current_user.email}")
        return MessageResponse(
            message="Cuenta eliminada correctamente",
            success=True
        )
    except Exception as e:
        logger.error(f"Error eliminando cuenta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar cuenta"
        )


# ============================================
# ENDPOINTS DE ADMINISTRACIÓN (requieren admin/moderador)
# ============================================

@router.get(
    "/",
    response_model=List[UserResponse],
    summary="Listar todos los usuarios",
    description="Obtiene una lista paginada de todos los usuarios"
)
def get_users(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(100, ge=1, le=100, description="Límite de registros"),
    search: Optional[str] = Query(None, description="Búsqueda por email, username o nombre"),
    role: Optional[UserRole] = Query(None, description="Filtrar por rol"),
    status: Optional[UserStatus] = Query(None, description="Filtrar por estado"),
    is_active: Optional[bool] = Query(None, description="Filtrar por activo/inactivo"),
    sort_by: Optional[str] = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Orden ascendente/descendente"),
    current_user: User = Depends(is_moderator),  # Moderador o admin
    db: Session = Depends(get_db)
) -> List[UserResponse]:
    """
    Obtener lista de todos los usuarios con filtros y paginación.
    
    - **Requiere**: Moderador o Administrador
    - **Filtros**: search, role, status, is_active
    - **Ordenamiento**: sort_by, sort_order
    - **Paginación**: skip, limit
    """
    try:
        users = CRUDUser.get_all(
            db,
            skip=skip,
            limit=limit,
            search=search,
            role=role,
            status=status,
            is_active=is_active,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return users
    except Exception as e:
        logger.error(f"Error obteniendo usuarios: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener usuarios"
        )


@router.get(
    "/count",
    response_model=dict,
    summary="Contar usuarios",
    description="Obtiene el número total de usuarios con filtros"
)
def count_users(
    search: Optional[str] = Query(None, description="Búsqueda por email, username o nombre"),
    role: Optional[UserRole] = Query(None, description="Filtrar por rol"),
    status: Optional[UserStatus] = Query(None, description="Filtrar por estado"),
    is_active: Optional[bool] = Query(None, description="Filtrar por activo/inactivo"),
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> dict:
    """
    Contar usuarios según filtros.
    
    - **Requiere**: Moderador o Administrador
    """
    try:
        total = CRUDUser.count_users(
            db,
            search=search,
            role=role,
            status=status,
            is_active=is_active
        )
        return {"total": total}
    except Exception as e:
        logger.error(f"Error contando usuarios: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al contar usuarios"
        )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Obtener usuario por ID",
    description="Obtiene los datos de un usuario específico"
)
def get_user(
    user_id: int,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Obtener usuario por ID.
    
    - **Requiere**: Moderador o Administrador
    - **Param**: user_id - ID del usuario a obtener
    """
    try:
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener usuario"
        )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Actualizar usuario",
    description="Actualiza los datos de un usuario específico"
)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(is_admin),  # Solo admin
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Actualizar usuario por ID.
    
    - **Requiere**: Administrador
    - **Param**: user_id - ID del usuario a actualizar
    """
    try:
        # Verificar que el usuario existe
        existing_user = CRUDUser.get_by_id(db, user_id)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        user = CRUDUser.update(db, user_id, user_data)
        logger.info(f"Usuario {user_id} actualizado por admin: {current_user.email}")
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar usuario"
        )


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Eliminar usuario",
    description="Elimina un usuario específico"
)
def delete_user(
    user_id: int,
    hard_delete: bool = Query(False, description="Eliminación permanente (hard delete)"),
    current_user: User = Depends(is_admin),  # Solo admin
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar usuario por ID.
    
    - **Requiere**: Administrador
    - **Param**: user_id - ID del usuario a eliminar
    - **Query**: hard_delete - Si es True, elimina permanentemente
    """
    try:
        # Verificar que el usuario existe
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        # No permitir eliminar a sí mismo
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes eliminarte a ti mismo"
            )
        
        result = CRUDUser.delete(db, user_id, soft=not hard_delete)
        
        if hard_delete:
            logger.warning(f"Usuario {user_id} eliminado permanentemente por admin: {current_user.email}")
            message = f"Usuario {user.email} eliminado permanentemente"
        else:
            logger.info(f"Usuario {user_id} desactivado por admin: {current_user.email}")
            message = f"Usuario {user.email} desactivado"
        
        return MessageResponse(
            message=message,
            success=True
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar usuario"
        )


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Cambiar estado de usuario",
    description="Activa o desactiva un usuario"
)
def change_user_status(
    user_id: int,
    status: UserStatus,
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Cambiar el estado de un usuario.
    
    - **Requiere**: Administrador
    - **Param**: user_id - ID del usuario
    - **Body**: status - Nuevo estado (active, inactive, suspended, pending)
    """
    try:
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        # No permitir cambiar el estado de sí mismo
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes cambiar tu propio estado"
            )
        
        update_data = UserUpdate(status=status)
        user = CRUDUser.update(db, user_id, update_data)
        
        logger.info(f"Estado del usuario {user_id} cambiado a {status.value} por admin: {current_user.email}")
        return user
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cambiando estado de usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar estado del usuario"
        )


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Cambiar rol de usuario",
    description="Cambia el rol de un usuario (admin, moderator, user, guest)"
)
def change_user_role(
    user_id: int,
    role: UserRole,
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Cambiar el rol de un usuario.
    
    - **Requiere**: Administrador
    - **Param**: user_id - ID del usuario
    - **Body**: role - Nuevo rol (admin, moderator, user, guest)
    """
    try:
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        # No permitir cambiar el rol de sí mismo (por seguridad)
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes cambiar tu propio rol"
            )
        
        update_data = UserUpdate(role=role)
        user = CRUDUser.update(db, user_id, update_data)
        
        logger.info(f"Rol del usuario {user_id} cambiado a {role.value} por admin: {current_user.email}")
        return user
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cambiando rol de usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar rol del usuario"
        )


# ============================================
# ENDPOINTS DE ESTADÍSTICAS
# ============================================

@router.get(
    "/stats/dashboard",
    response_model=dict,
    summary="Estadísticas de usuarios",
    description="Obtiene estadísticas de usuarios para el dashboard"
)
def get_user_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de usuarios.
    
    - **Requiere**: Administrador
    - **Retorna**: Estadísticas de usuarios (totales, activos, roles, etc.)
    """
    try:
        stats = CRUDUser.get_statistics(db)
        return stats
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


# ============================================
# FUNCIONES DE UTILIDAD (NO EXPUESTAS)
# ============================================

def get_user_or_404(db: Session, user_id: int) -> User:
    """
    Obtener usuario o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    user = CRUDUser.get_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con ID {user_id} no encontrado"
        )
    return user