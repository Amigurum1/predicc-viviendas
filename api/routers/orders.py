"""
Router de órdenes
Endpoints para la gestión de órdenes (CRUD)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import logging

from api.database import get_db
from api.crud import CRUDOrder, CRUDUser, CRUDProduct
from api.schemas import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderItemResponse,
    MessageResponse,
    FilterParams
)
from api.auth import (
    get_current_active_user,
    is_admin,
    is_moderator,
    owner_or_admin_required
)
from api.models import User, OrderStatus
from api.models import User, OrderStatus, Order  # ✅ Agregar Order aquí


# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/orders",
    tags=["órdenes"]
)


# ============================================
# ENDPOINTS PÚBLICOS (requieren autenticación)
# ============================================

@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear orden",
    description="Crea una nueva orden de compra"
)
def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Crear una nueva orden.
    
    - **Requiere**: Usuario autenticado
    - **Items**: Lista de productos con cantidades
    - **El stock se actualiza automáticamente**
    """
    try:
        order = CRUDOrder.create(db, order_data, current_user.id)
        logger.info(f"Orden creada: {order.order_number} por usuario {current_user.email}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando orden: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear orden"
        )


@router.get(
    "/",
    response_model=List[OrderResponse],
    summary="Listar órdenes del usuario",
    description="Obtiene las órdenes del usuario autenticado"
)
def get_my_orders(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(20, ge=1, le=50, description="Límite de registros"),
    status: Optional[OrderStatus] = Query(None, description="Filtrar por estado"),
    date_from: Optional[datetime] = Query(None, description="Fecha desde"),
    date_to: Optional[datetime] = Query(None, description="Fecha hasta"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> List[OrderResponse]:
    """
    Obtener las órdenes del usuario autenticado.
    
    - **Requiere**: Usuario autenticado
    - **Filtros**: status, date_from, date_to
    - **Paginación**: skip, limit
    """
    try:
        orders = CRUDOrder.get_all(
            db,
            skip=skip,
            limit=limit,
            user_id=current_user.id,
            status=status,
            date_from=date_from,
            date_to=date_to
        )
        return orders
    except Exception as e:
        logger.error(f"Error obteniendo órdenes del usuario: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener órdenes"
        )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Obtener orden por ID",
    description="Obtiene los detalles de una orden específica"
)
def get_order(
    order_id: int,
    current_user: User = Depends(owner_or_admin_required("order")),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Obtener orden por ID.
    
    - **Requiere**: Propietario de la orden o Administrador
    - **Param**: order_id - ID de la orden
    """
    try:
        order = CRUDOrder.get_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Orden con ID {order_id} no encontrada"
            )
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo orden {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener orden"
        )


@router.get(
    "/by-number/{order_number}",
    response_model=OrderResponse,
    summary="Obtener orden por número",
    description="Obtiene una orden por su número de orden"
)
def get_order_by_number(
    order_number: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Obtener orden por número de orden.
    
    - **Requiere**: Usuario autenticado
    - **Param**: order_number - Número de orden (ej: ORD-202401010000-1234)
    """
    try:
        order = CRUDOrder.get_by_order_number(db, order_number)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Orden con número {order_number} no encontrada"
            )
        
        # Verificar que el usuario sea el propietario o admin
        if order.user_id != current_user.id and current_user.role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para ver esta orden"
            )
        
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo orden por número {order_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener orden"
        )


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="Cancelar orden",
    description="Cancela una orden pendiente"
)
def cancel_order(
    order_id: int,
    reason: Optional[str] = Query(None, description="Motivo de la cancelación"),
    current_user: User = Depends(owner_or_admin_required("order")),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Cancelar una orden.
    
    - **Requiere**: Propietario de la orden o Administrador
    - **Solo**: Órdenes en estado PENDING o PROCESSING
    - **El stock se restaura automáticamente**
    """
    try:
        order = CRUDOrder.cancel(db, order_id, reason)
        logger.info(f"Orden {order_id} cancelada por {current_user.email}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelando orden {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cancelar orden"
        )


# ============================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================

@router.get(
    "/admin/all",
    response_model=List[OrderResponse],
    summary="Listar todas las órdenes (admin)",
    description="Obtiene todas las órdenes del sistema"
)
def get_all_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="Filtrar por usuario"),
    status: Optional[OrderStatus] = Query(None, description="Filtrar por estado"),
    payment_status: Optional[str] = Query(None, description="Filtrar por estado de pago"),
    date_from: Optional[datetime] = Query(None, description="Fecha desde"),
    date_to: Optional[datetime] = Query(None, description="Fecha hasta"),
    min_total: Optional[float] = Query(None, ge=0, description="Total mínimo"),
    max_total: Optional[float] = Query(None, ge=0, description="Total máximo"),
    sort_by: Optional[str] = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> List[OrderResponse]:
    """
    Obtener todas las órdenes con filtros.
    
    - **Requiere**: Moderador o Administrador
    - **Filtros**: user_id, status, payment_status, date_from, date_to, min_total, max_total
    """
    try:
        orders = CRUDOrder.get_all(
            db,
            skip=skip,
            limit=limit,
            user_id=user_id,
            status=status,
            payment_status=payment_status,
            date_from=date_from,
            date_to=date_to,
            min_total=min_total,
            max_total=max_total,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return orders
    except Exception as e:
        logger.error(f"Error obteniendo todas las órdenes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener órdenes"
        )


@router.get(
    "/admin/stats",
    response_model=dict,
    summary="Estadísticas de órdenes",
    description="Obtiene estadísticas de órdenes para el dashboard"
)
def get_order_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> dict:
    """
    Obtener estadísticas de órdenes.
    
    - **Requiere**: Administrador
    """
    try:
        stats = CRUDOrder.get_statistics(db)
        return stats
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de órdenes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


@router.put(
    "/admin/{order_id}/status",
    response_model=OrderResponse,
    summary="Actualizar estado de orden (admin)",
    description="Actualiza el estado de una orden"
)
def update_order_status(
    order_id: int,
    status: OrderStatus,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Actualizar el estado de una orden.
    
    - **Requiere**: Moderador o Administrador
    - **Estados**: pending, processing, shipped, delivered, cancelled
    """
    try:
        order = CRUDOrder.update_status(db, order_id, status)
        logger.info(f"Orden {order_id} actualizada a {status.value} por {current_user.email}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando estado de orden {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar estado de la orden"
        )


@router.put(
    "/admin/{order_id}/payment",
    response_model=OrderResponse,
    summary="Actualizar pago de orden",
    description="Actualiza el estado de pago de una orden"
)
def update_payment_status(
    order_id: int,
    payment_status: str,
    payment_id: Optional[str] = None,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Actualizar el estado de pago de una orden.
    
    - **Requiere**: Moderador o Administrador
    - **payment_status**: pending, paid, failed, refunded
    """
    try:
        order = CRUDOrder.update_payment(db, order_id, payment_status, payment_id)
        logger.info(f"Pago de orden {order_id} actualizado a {payment_status}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando pago de orden {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar pago de la orden"
        )


@router.post(
    "/admin/{order_id}/ship",
    response_model=OrderResponse,
    summary="Marcar como enviado",
    description="Marca una orden como enviada"
)
def mark_as_shipped(
    order_id: int,
    tracking_number: Optional[str] = Query(None, description="Número de seguimiento"),
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Marcar una orden como enviada.
    
    - **Requiere**: Moderador o Administrador
    - **Cambia**: status a SHIPPED
    - **Registra**: shipped_at y tracking_number
    """
    try:
        # Primero actualizar el estado
        order = CRUDOrder.update_status(db, order_id, OrderStatus.SHIPPED)
        
        # Luego actualizar el tracking number si se proporcionó
        if tracking_number:
            update_data = OrderUpdate(tracking_number=tracking_number)
            from api.crud import CRUDOrder
            # Actualizar el tracking number
            for key, value in update_data.model_dump(exclude_unset=True).items():
                setattr(order, key, value)
            db.commit()
            db.refresh(order)
        
        logger.info(f"Orden {order_id} marcada como enviada por {current_user.email}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marcando orden {order_id} como enviada: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al marcar orden como enviada"
        )


@router.post(
    "/admin/{order_id}/deliver",
    response_model=OrderResponse,
    summary="Marcar como entregado",
    description="Marca una orden como entregada"
)
def mark_as_delivered(
    order_id: int,
    current_user: User = Depends(is_moderator),
    db: Session = Depends(get_db)
) -> OrderResponse:
    """
    Marcar una orden como entregada.
    
    - **Requiere**: Moderador o Administrador
    - **Cambia**: status a DELIVERED
    - **Registra**: delivered_at
    """
    try:
        order = CRUDOrder.update_status(db, order_id, OrderStatus.DELIVERED)
        logger.info(f"Orden {order_id} marcada como entregada por {current_user.email}")
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marcando orden {order_id} como entregada: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al marcar orden como entregada"
        )


# ============================================
# FUNCIONES DE UTILIDAD (NO EXPUESTAS)
# ============================================

def get_order_or_404(db: Session, order_id: int) -> Order:
    """
    Obtener orden o lanzar 404.
    
    - **Uso interno**: Para reutilizar en otros endpoints
    """
    order = CRUDOrder.get_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Orden con ID {order_id} no encontrada"
        )
    return order


def validate_order_ownership(order: Order, current_user: User) -> bool:
    """
    Validar que el usuario sea propietario de la orden.
    
    - **Uso interno**: Para verificar permisos
    """
    if current_user.role in ["admin", "moderator"]:
        return True
    return order.user_id == current_user.id