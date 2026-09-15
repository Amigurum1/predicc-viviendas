"""
Router de productos
Endpoints para la gestión de productos (CRUD)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from api.database import get_db
from api.crud import CRUDProduct, CRUDUser
from api.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    MessageResponse,
    FilterParams
)
from api.auth import (
    get_current_active_user,
    is_admin,
    is_moderator,
    owner_or_admin_required
)
from api.models import User, ProductStatus
from api.models import User, Product, ProductStatus  # ✅ Agregar Product aquí
from api.config import config

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/products",
    tags=["productos"]
)


# ============================================
# ENDPOINTS PÚBLICOS (no requieren autenticación)
# ============================================

@router.get(
    "/",
    response_model=List[ProductResponse],
    summary="Listar productos",
    description="Obtiene una lista paginada de productos con filtros"
)
def get_products(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(20, ge=1, le=100, description="Límite de registros"),
    search: Optional[str] = Query(None, description="Búsqueda por nombre, descripción o SKU"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    brand: Optional[str] = Query(None, description="Filtrar por marca"),
    min_price: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    in_stock: Optional[bool] = Query(None, description="Solo productos en stock"),
    is_featured: Optional[bool] = Query(None, description="Solo productos destacados"),
    sort_by: Optional[str] = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Orden ascendente/descendente"),
    db: Session = Depends(get_db)
) -> List[ProductResponse]:
    """
    Obtener lista de productos con filtros y paginación.
    
    - **Filtros**: search, category, brand, min_price, max_price, in_stock, is_featured
    - **Ordenamiento**: sort_by, sort_order
    - **Paginación**: skip, limit
    - **Acceso**: Público
    """
    try:
        products = CRUDProduct.get_all(
            db,
            skip=skip,
            limit=limit,
            search=search,
            category=category,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            is_active=True,  # Solo productos activos
            is_featured=is_featured,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return products
    except Exception as e:
        logger.error(f"Error obteniendo productos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener productos"
        )


@router.get(
    "/featured",
    response_model=List[ProductResponse],
    summary="Productos destacados",
    description="Obtiene los productos destacados"
)
def get_featured_products(
    limit: int = Query(10, ge=1, le=20, description="Número de productos destacados"),
    db: Session = Depends(get_db)
) -> List[ProductResponse]:
    """
    Obtener productos destacados.
    
    - **Retorna**: Productos con is_featured=True y en stock
    - **Acceso**: Público
    """
    try:
        products = CRUDProduct.get_featured(db, limit=limit)
        return products
    except Exception as e:
        logger.error(f"Error obteniendo productos destacados: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener productos destacados"
        )


@router.get(
    "/bestsellers",
    response_model=List[ProductResponse],
    summary="Productos más vendidos",
    description="Obtiene los productos más vendidos"
)
def get_bestsellers(
    limit: int = Query(10, ge=1, le=20, description="Número de productos"),
    db: Session = Depends(get_db)
) -> List[ProductResponse]:
    """
    Obtener productos más vendidos.
    
    - **Retorna**: Productos ordenados por ventas
    - **Acceso**: Público
    """
    try:
        products = CRUDProduct.get_best_sellers(db, limit=limit)
        return products
    except Exception as e:
        logger.error(f"Error obteniendo bestsellers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener productos más vendidos"
        )


@router.get(
    "/categories",
    response_model=List[str],
    summary="Listar categorías",
    description="Obtiene todas las categorías de productos disponibles"
)
def get_categories(
    db: Session = Depends(get_db)
) -> List[str]:
    """
    Obtener todas las categorías de productos.
    
    - **Acceso**: Público
    - **Retorna**: Lista de categorías únicas
    """
    try:
        from sqlalchemy import distinct
        categories = db.query(distinct(Product.category)).filter(
            Product.category.isnot(None),
            Product.is_active == True
        ).all()
        return [c[0] for c in categories if c[0]]
    except Exception as e:
        logger.error(f"Error obteniendo categorías: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categorías"
        )


@router.get(
    "/brands",
    response_model=List[str],
    summary="Listar marcas",
    description="Obtiene todas las marcas de productos disponibles"
)
def get_brands(
    db: Session = Depends(get_db)
) -> List[str]:
    """
    Obtener todas las marcas de productos.
    
    - **Acceso**: Público
    - **Retorna**: Lista de marcas únicas
    """
    try:
        from sqlalchemy import distinct
        brands = db.query(distinct(Product.brand)).filter(
            Product.brand.isnot(None),
            Product.is_active == True
        ).all()
        return [b[0] for b in brands if b[0]]
    except Exception as e:
        logger.error(f"Error obteniendo marcas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener marcas"
        )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Obtener producto por ID",
    description="Obtiene los detalles de un producto específico"
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Obtener producto por ID.
    
    - **Param**: product_id - ID del producto
    - **Acceso**: Público
    """
    try:
        product = CRUDProduct.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {product_id} no encontrado"
            )
        
        # Incrementar contador de vistas
        CRUDProduct.increment_view(db, product_id)
        
        return product
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener producto"
        )


# ============================================
# ENDPOINTS DE ADMINISTRACIÓN (requieren autenticación)
# ============================================

@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto",
    description="Crea un nuevo producto"
)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Crear un nuevo producto.
    
    - **Requiere**: Usuario autenticado
    - **El usuario se asigna automáticamente como owner**
    """
    try:
        # Asignar el usuario actual como owner
        product_data.owner_id = current_user.id
        
        product = CRUDProduct.create(db, product_data)
        logger.info(f"Producto creado: {product.name} por usuario {current_user.email}")
        return product
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando producto: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear producto"
        )


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Actualizar producto",
    description="Actualiza un producto existente"
)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    current_user: User = Depends(owner_or_admin_required("product")),
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Actualizar producto por ID.
    
    - **Requiere**: Propietario del producto o Administrador
    - **Param**: product_id - ID del producto a actualizar
    """
    try:
        product = CRUDProduct.update(db, product_id, product_data)
        logger.info(f"Producto {product_id} actualizado: {product.name}")
        return product
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar producto"
        )


@router.delete(
    "/{product_id}",
    response_model=MessageResponse,
    summary="Eliminar producto",
    description="Elimina un producto (soft delete por defecto)"
)
def delete_product(
    product_id: int,
    hard_delete: bool = Query(False, description="Eliminación permanente (hard delete)"),
    current_user: User = Depends(owner_or_admin_required("product")),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar producto por ID.
    
    - **Requiere**: Propietario del producto o Administrador
    - **Param**: product_id - ID del producto a eliminar
    - **Query**: hard_delete - Si es True, elimina permanentemente
    """
    try:
        product = CRUDProduct.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {product_id} no encontrado"
            )
        
        result = CRUDProduct.delete(db, product_id, soft=not hard_delete)
        
        if hard_delete:
            logger.warning(f"Producto {product_id} eliminado permanentemente por {current_user.email}")
            message = f"Producto '{product.name}' eliminado permanentemente"
        else:
            logger.info(f"Producto {product_id} desactivado por {current_user.email}")
            message = f"Producto '{product.name}' desactivado"
        
        return MessageResponse(
            message=message,
            success=True
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar producto"
        )


@router.patch(
    "/{product_id}/status",
    response_model=ProductResponse,
    summary="Cambiar estado de producto",
    description="Cambia el estado de un producto"
)
def change_product_status(
    product_id: int,
    status: ProductStatus,
    current_user: User = Depends(owner_or_admin_required("product")),
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Cambiar el estado de un producto.
    
    - **Requiere**: Propietario del producto o Administrador
    - **Estados**: available, out_of_stock, discontinued, pending
    """
    try:
        update_data = ProductUpdate(status=status)
        product = CRUDProduct.update(db, product_id, update_data)
        logger.info(f"Estado del producto {product_id} cambiado a {status.value}")
        return product
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cambiando estado de producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar estado del producto"
        )


@router.patch(
    "/{product_id}/stock",
    response_model=ProductResponse,
    summary="Actualizar stock",
    description="Actualiza el stock de un producto"
)
def update_stock(
    product_id: int,
    quantity: int = Query(..., description="Cantidad a agregar (positivo) o restar (negativo)"),
    current_user: User = Depends(owner_or_admin_required("product")),
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Actualizar el stock de un producto.
    
    - **Requiere**: Propietario del producto o Administrador
    - **Param**: quantity - Cantidad a agregar/restar
    - **Ejemplo**: quantity=5 (agrega 5), quantity=-3 (resta 3)
    """
    try:
        product = CRUDProduct.update_stock(db, product_id, quantity)
        logger.info(f"Stock del producto {product_id} actualizado: {product.stock}")
        return product
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando stock de producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar stock"
        )


@router.post(
    "/{product_id}/toggle-featured",
    response_model=ProductResponse,
    summary="Alternar producto destacado",
    description="Marca o desmarca un producto como destacado"
)
def toggle_featured(
    product_id: int,
    current_user: User = Depends(is_moderator),  # Moderador o admin
    db: Session = Depends(get_db)
) -> ProductResponse:
    """
    Alternar el estado destacado de un producto.
    
    - **Requiere**: Moderador o Administrador
    - **Cambia**: is_featured de True a False o viceversa
    """
    try:
        product = CRUDProduct.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {product_id} no encontrado"
            )
        
        update_data = ProductUpdate(is_featured=not product.is_featured)
        product = CRUDProduct.update(db, product_id, update_data)
        
        action = "destacado" if product.is_featured else "no destacado"
        logger.info(f"Producto {product_id} marcado como {action}")
        return product
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error alternando featured de producto {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar estado destacado"
        )


# ============================================
# ENDPOINTS PARA ADMINISTRACIÓN COMPLETA
# ============================================

@router.get(
    "/admin/all",
    response_model=List[ProductResponse],
    summary="Listar todos los productos (admin)",
    description="Obtiene todos los productos incluyendo inactivos"
)
def get_all_products_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[ProductStatus] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> List[ProductResponse]:
    """
    Obtener todos los productos (incluyendo inactivos).
    
    - **Requiere**: Administrador
    - **Uso**: Para panel de administración
    """
    try:
        products = CRUDProduct.get_all(
            db,
            skip=skip,
            limit=limit,
            search=search,
            status=status,
            is_active=is_active
        )
        return products
    except Exception as e:
        logger.error(f"Error obteniendo todos los productos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener productos"
        )


@router.get(
    "/admin/stats",
    response_model=dict,
    summary="Estadísticas de productos",
    description="Obtiene estadísticas de productos para el dashboard"
)
def get_product_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de productos.
    
    - **Requiere**: Administrador
    - **Retorna**: Estadísticas de productos
    """
    try:
        from sqlalchemy import func
        
        total = db.query(Product).count()
        active = db.query(Product).filter(Product.is_active == True).count()
        in_stock = db.query(Product).filter(Product.stock > 0).count()
        
        by_status = db.query(
            Product.status,
            func.count(Product.id).label('count')
        ).group_by(Product.status).all()
        
        categories = db.query(
            Product.category,
            func.count(Product.id).label('count')
        ).filter(Product.category.isnot(None)).group_by(Product.category).all()
        
        return {
            "total_products": total,
            "active_products": active,
            "in_stock_products": in_stock,
            "by_status": [{"status": s.status.value, "count": s.count} for s in by_status],
            "by_category": [{"category": c.category, "count": c.count} for c in categories]
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de productos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


# ============================================
# FUNCIONES DE UTILIDAD (NO EXPUESTAS)
# ============================================

def get_product_or_404(db: Session, product_id: int) -> Product:
    """
    Obtener producto o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    product = CRUDProduct.get_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con ID {product_id} no encontrado"
        )
    return product