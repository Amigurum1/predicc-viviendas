"""
Router de reseñas
Endpoints para la gestión de reseñas y calificaciones de productos
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from api.database import get_db
from api.crud import CRUDReview, CRUDProduct, CRUDUser
from api.schemas import (
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    MessageResponse,
    FilterParams
)
from api.auth import (
    get_current_active_user,
    is_admin,
    is_moderator,
    owner_or_admin_required
)
from api.models import User, Review  # ✅ Agregar Review aquí


# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/reviews",
    tags=["reseñas"]
)


# ============================================
# ENDPOINTS PÚBLICOS (no requieren autenticación)
# ============================================

@router.get(
    "/product/{product_id}",
    response_model=List[ReviewResponse],
    summary="Obtener reseñas de un producto",
    description="Obtiene todas las reseñas de un producto específico"
)
def get_product_reviews(
    product_id: int,
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(20, ge=1, le=50, description="Límite de registros"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filtrar por calificación"),
    sort_by: Optional[str] = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Orden ascendente/descendente"),
    db: Session = Depends(get_db)
) -> List[ReviewResponse]:
    """
    Obtener reseñas de un producto.
    
    - **Param**: product_id - ID del producto
    - **Filtros**: rating
    - **Acceso**: Público
    """
    try:
        # Verificar que el producto existe
        product = CRUDProduct.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {product_id} no encontrado"
            )
        
        reviews = CRUDReview.get_all(
            db,
            skip=skip,
            limit=limit,
            product_id=product_id,
            rating=rating,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return reviews
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo reseñas del producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener reseñas"
        )


@router.get(
    "/product/{product_id}/stats",
    response_model=dict,
    summary="Estadísticas de calificaciones",
    description="Obtiene estadísticas de calificaciones de un producto"
)
def get_product_rating_stats(
    product_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de calificaciones de un producto.
    
    - **Param**: product_id - ID del producto
    - **Retorna**: Promedio, total y distribución de calificaciones
    - **Acceso**: Público
    """
    try:
        # Verificar que el producto existe
        product = CRUDProduct.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {product_id} no encontrado"
            )
        
        stats = CRUDReview.get_product_rating_stats(db, product_id)
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas del producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


@router.get(
    "/user/{user_id}",
    response_model=List[ReviewResponse],
    summary="Obtener reseñas de un usuario",
    description="Obtiene todas las reseñas de un usuario específico"
)
def get_user_reviews(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> List[ReviewResponse]:
    """
    Obtener reseñas de un usuario.
    
    - **Requiere**: Usuario autenticado
    - **Param**: user_id - ID del usuario
    - **Nota**: Solo el propio usuario o admin pueden ver las reseñas
    """
    try:
        # Verificar permisos
        if user_id != current_user.id and current_user.role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para ver las reseñas de este usuario"
            )
        
        # Verificar que el usuario existe
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        reviews = CRUDReview.get_all(
            db,
            skip=skip,
            limit=limit,
            user_id=user_id
        )
        return reviews
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo reseñas del usuario {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener reseñas"
        )


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Obtener reseña por ID",
    description="Obtiene los detalles de una reseña específica"
)
def get_review(
    review_id: int,
    db: Session = Depends(get_db)
) -> ReviewResponse:
    """
    Obtener reseña por ID.
    
    - **Param**: review_id - ID de la reseña
    - **Acceso**: Público
    """
    try:
        review = CRUDReview.get_by_id(db, review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reseña con ID {review_id} no encontrada"
            )
        return review
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo reseña {review_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener reseña"
        )


# ============================================
# ENDPOINTS PROTEGIDOS (requieren autenticación)
# ============================================

@router.post(
    "/",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear reseña",
    description="Crea una nueva reseña para un producto"
)
def create_review(
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ReviewResponse:
    """
    Crear una nueva reseña.
    
    - **Requiere**: Usuario autenticado
    - **Campos**: rating (1-5), comment (opcional), product_id
    - **Nota**: Un usuario solo puede reseñar un producto una vez
    """
    try:
        review = CRUDReview.create(db, review_data, current_user.id)
        logger.info(f"Reseña creada para producto {review_data.product_id} por usuario {current_user.email}")
        return review
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando reseña: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear reseña"
        )


@router.put(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Actualizar reseña",
    description="Actualiza una reseña existente"
)
def update_review(
    review_id: int,
    review_data: ReviewUpdate,
    current_user: User = Depends(owner_or_admin_required("review")),
    db: Session = Depends(get_db)
) -> ReviewResponse:
    """
    Actualizar reseña por ID.
    
    - **Requiere**: Propietario de la reseña o Administrador
    - **Campos**: rating, comment
    """
    try:
        review = CRUDReview.update(db, review_id, review_data)
        logger.info(f"Reseña {review_id} actualizada")
        return review
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando reseña {review_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar reseña"
        )


@router.delete(
    "/{review_id}",
    response_model=MessageResponse,
    summary="Eliminar reseña",
    description="Elimina una reseña"
)
def delete_review(
    review_id: int,
    current_user: User = Depends(owner_or_admin_required("review")),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar reseña por ID.
    
    - **Requiere**: Propietario de la reseña o Administrador
    """
    try:
        review = CRUDReview.get_by_id(db, review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reseña con ID {review_id} no encontrada"
            )
        
        result = CRUDReview.delete(db, review_id)
        logger.info(f"Reseña {review_id} eliminada por {current_user.email}")
        return MessageResponse(
            message="Reseña eliminada correctamente",
            success=True
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando reseña {review_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar reseña"
        )


# ============================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================

@router.get(
    "/admin/all",
    response_model=List[ReviewResponse],
    summary="Listar todas las reseñas (admin)",
    description="Obtiene todas las reseñas del sistema"
)
def get_all_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    product_id: Optional[int] = Query(None, description="Filtrar por producto"),
    user_id: Optional[int] = Query(None, description="Filtrar por usuario"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filtrar por calificación"),
    sort_by: Optional[str] = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> List[ReviewResponse]:
    """
    Obtener todas las reseñas con filtros.
    
    - **Requiere**: Moderador o Administrador
    """
    try:
        reviews = CRUDReview.get_all(
            db,
            skip=skip,
            limit=limit,
            product_id=product_id,
            user_id=user_id,
            rating=rating,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return reviews
    except Exception as e:
        logger.error(f"Error obteniendo todas las reseñas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener reseñas"
        )


@router.get(
    "/admin/stats",
    response_model=dict,
    summary="Estadísticas de reseñas",
    description="Obtiene estadísticas de reseñas para el dashboard"
)
def get_review_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de reseñas.
    
    - **Requiere**: Administrador
    """
    try:
        from sqlalchemy import func
        from api.models import Review
        
        total = db.query(Review).count()
        
        by_rating = db.query(
            Review.rating,
            func.count(Review.id).label('count')
        ).group_by(Review.rating).all()
        
        # Productos con más reseñas
        top_products = db.query(
            Review.product_id,
            func.count(Review.id).label('count')
        ).group_by(Review.product_id).order_by(func.count(Review.id).desc()).limit(10).all()
        
        return {
            "total_reviews": total,
            "by_rating": [{"rating": r.rating, "count": r.count} for r in by_rating],
            "top_products": [{"product_id": p.product_id, "count": p.count} for p in top_products]
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de reseñas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


# ============================================
# FUNCIONES DE UTILIDAD (NO EXPUESTAS)
# ============================================

def get_review_or_404(db: Session, review_id: int) -> Review:
    """
    Obtener reseña o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    review = CRUDReview.get_by_id(db, review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reseña con ID {review_id} no encontrada"
        )
    return review


def validate_review_ownership(review: Review, current_user: User) -> bool:
    """
    Validar que el usuario sea propietario de la reseña.
    
    - **Uso interno**: Para verificar permisos
    """
    if current_user.role in ["admin", "moderator"]:
        return True
    return review.user_id == current_user.id