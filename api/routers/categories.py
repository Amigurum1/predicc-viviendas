"""
Router de categorías
Endpoints para la gestión de categorías de productos
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging

from api.database import get_db
from api.crud import CRUDCategory, CRUDProduct
from api.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    MessageResponse,
    FilterParams
)
from api.auth import (
    get_current_active_user,
    is_admin,
    is_moderator
)
from api.models import User, Category

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/categories",
    tags=["categorías"]
)


# ============================================
# ENDPOINTS PÚBLICOS (no requieren autenticación)
# ============================================

@router.get(
    "/",
    response_model=List[CategoryResponse],
    summary="Listar categorías",
    description="Obtiene todas las categorías activas"
)
def get_categories(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(50, ge=1, le=100, description="Límite de registros"),
    is_active: Optional[bool] = Query(True, description="Filtrar por activo/inactivo"),
    parent_id: Optional[int] = Query(None, description="Filtrar por categoría padre"),
    db: Session = Depends(get_db)
) -> List[CategoryResponse]:
    """
    Obtener lista de categorías.
    
    - **Filtros**: is_active, parent_id
    - **Paginación**: skip, limit
    - **Acceso**: Público
    """
    try:
        categories = CRUDCategory.get_all(
            db,
            skip=skip,
            limit=limit,
            is_active=is_active,
            parent_id=parent_id
        )
        return categories
    except Exception as e:
        logger.error(f"Error obteniendo categorías: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categorías"
        )


@router.get(
    "/tree",
    response_model=List[Dict[str, Any]],
    summary="Árbol de categorías",
    description="Obtiene las categorías en formato jerárquico (árbol)"
)
def get_category_tree(
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Obtener árbol de categorías.
    
    - **Retorna**: Categorías organizadas jerárquicamente
    - **Acceso**: Público
    """
    try:
        tree = CRUDCategory.get_tree(db)
        return tree
    except Exception as e:
        logger.error(f"Error obteniendo árbol de categorías: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener árbol de categorías"
        )


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Obtener categoría por ID",
    description="Obtiene los detalles de una categoría específica"
)
def get_category(
    category_id: int,
    db: Session = Depends(get_db)
) -> CategoryResponse:
    """
    Obtener categoría por ID.
    
    - **Param**: category_id - ID de la categoría
    - **Acceso**: Público
    """
    try:
        category = CRUDCategory.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría con ID {category_id} no encontrada"
            )
        return category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo categoría {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categoría"
        )


@router.get(
    "/by-slug/{slug}",
    response_model=CategoryResponse,
    summary="Obtener categoría por slug",
    description="Obtiene una categoría por su slug"
)
def get_category_by_slug(
    slug: str,
    db: Session = Depends(get_db)
) -> CategoryResponse:
    """
    Obtener categoría por slug.
    
    - **Param**: slug - Slug de la categoría
    - **Acceso**: Público
    """
    try:
        category = CRUDCategory.get_by_slug(db, slug)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría con slug '{slug}' no encontrada"
            )
        return category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo categoría por slug {slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categoría"
        )


@router.get(
    "/{category_id}/products",
    response_model=List[Dict[str, Any]],
    summary="Productos de una categoría",
    description="Obtiene los productos de una categoría específica"
)
def get_category_products(
    category_id: int,
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(20, ge=1, le=50, description="Límite de registros"),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Obtener productos de una categoría.
    
    - **Param**: category_id - ID de la categoría
    - **Acceso**: Público
    """
    try:
        # Verificar que la categoría existe
        category = CRUDCategory.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría con ID {category_id} no encontrada"
            )
        
        # Obtener productos de la categoría
        from api.crud import CRUDProduct
        products = CRUDProduct.get_all(
            db,
            skip=skip,
            limit=limit,
            category=category.name,
            is_active=True
        )
        
        # También incluir subcategorías (opcional)
        # Aquí se podría expandir para incluir productos de subcategorías
        
        return [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "discount_price": p.discount_price,
                "final_price": p.final_price,
                "main_image": p.main_image,
                "stock": p.stock,
                "rating_avg": p.rating_avg
            }
            for p in products
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo productos de categoría {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener productos de la categoría"
        )


# ============================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================

@router.post(
    "/",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear categoría",
    description="Crea una nueva categoría"
)
def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> CategoryResponse:
    """
    Crear una nueva categoría.
    
    - **Requiere**: Moderador o Administrador
    - **Campos**: name, slug, description, parent_id, icon
    - **Slug**: Debe ser único y URL-friendly
    """
    try:
        category = CRUDCategory.create(db, category_data)
        logger.info(f"Categoría creada: {category.name} por {current_user.email}")
        return category
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando categoría: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear categoría"
        )


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Actualizar categoría",
    description="Actualiza una categoría existente"
)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> CategoryResponse:
    """
    Actualizar categoría por ID.
    
    - **Requiere**: Moderador o Administrador
    - **Param**: category_id - ID de la categoría
    """
    try:
        category = CRUDCategory.update(db, category_id, category_data)
        logger.info(f"Categoría {category_id} actualizada: {category.name}")
        return category
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando categoría {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar categoría"
        )


@router.delete(
    "/{category_id}",
    response_model=MessageResponse,
    summary="Eliminar categoría",
    description="Elimina una categoría (solo si no tiene subcategorías)"
)
def delete_category(
    category_id: int,
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar categoría por ID.
    
    - **Requiere**: Administrador
    - **Param**: category_id - ID de la categoría
    - **Nota**: No se puede eliminar si tiene subcategorías
    """
    try:
        category = CRUDCategory.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría con ID {category_id} no encontrada"
            )
        
        result = CRUDCategory.delete(db, category_id)
        logger.info(f"Categoría {category_id} eliminada por {current_user.email}")
        return MessageResponse(
            message=f"Categoría '{category.name}' eliminada correctamente",
            success=True
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando categoría {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar categoría"
        )


@router.patch(
    "/{category_id}/toggle-active",
    response_model=CategoryResponse,
    summary="Alternar estado de categoría",
    description="Activa o desactiva una categoría"
)
def toggle_category_active(
    category_id: int,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> CategoryResponse:
    """
    Alternar el estado activo/inactivo de una categoría.
    
    - **Requiere**: Moderador o Administrador
    """
    try:
        category = CRUDCategory.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría con ID {category_id} no encontrada"
            )
        
        update_data = CategoryUpdate(is_active=not category.is_active)
        category = CRUDCategory.update(db, category_id, update_data)
        
        action = "activada" if category.is_active else "desactivada"
        logger.info(f"Categoría {category_id} {action} por {current_user.email}")
        return category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error alternando estado de categoría {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar estado de la categoría"
        )


@router.get(
    "/admin/stats",
    response_model=dict,
    summary="Estadísticas de categorías",
    description="Obtiene estadísticas de categorías para el dashboard"
)
def get_category_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de categorías.
    
    - **Requiere**: Administrador
    """
    try:
        from sqlalchemy import func
        from api.models import Category, Product
        
        total = db.query(Category).count()
        active = db.query(Category).filter(Category.is_active == True).count()
        
        # Categorías con más productos
        top_categories = db.query(
            Category.name,
            func.count(Product.id).label('product_count')
        ).join(Product, Product.category == Category.name).filter(
            Product.is_active == True
        ).group_by(Category.name).order_by(
            func.count(Product.id).desc()
        ).limit(10).all()
        
        return {
            "total_categories": total,
            "active_categories": active,
            "top_categories": [
                {"name": c.name, "product_count": c.product_count}
                for c in top_categories
            ]
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de categorías: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


# ============================================
# FUNCIONES DE UTILIDAD (NO EXPUESTAS)
# ============================================

def get_category_or_404(db: Session, category_id: int) -> Category:
    """
    Obtener categoría o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    category = CRUDCategory.get_by_id(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Categoría con ID {category_id} no encontrada"
        )
    return category


def get_category_by_slug_or_404(db: Session, slug: str) -> Category:
    """
    Obtener categoría por slug o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    category = CRUDCategory.get_by_slug(db, slug)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Categoría con slug '{slug}' no encontrada"
        )
    return category