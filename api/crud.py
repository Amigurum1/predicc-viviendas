"""
Operaciones CRUD para la base de datos
Contiene todas las funciones de interacción con la BD
Organizado por modelo: User, Product, Order, Review, Category
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, or_, func, inspect
from typing import Optional, List, Dict, Any, Type
from datetime import datetime, timedelta
import logging
from passlib.context import CryptContext

from api import models, schemas
from api.config import config

# Configurar logger
logger = logging.getLogger(__name__)

# Contexto para hash de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

def get_password_hash(password: str) -> str:
    """Hashear una contraseña"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar una contraseña"""
    return pwd_context.verify(plain_password, hashed_password)

def apply_pagination(query, skip: int = 0, limit: int = 20):
    """
    Aplica paginación por DESPLAZAMIENTO (offset), no por número de página.

    Antes la firma era `(query, page, page_size)` pero las 6 llamadas del CRUD
    le pasaban `skip, limit`. El resultado: `offset = (skip - 1) * limit`, así
    que `skip=0` daba offset -limit (que SQLite interpreta como 0 y funcionaba
    por casualidad) y `skip=10` daba offset 90 en vez de 10, devolviendo 0 filas.
    Es decir, el historial y el resto de listados solo tenían primera página.

    Args:
        skip: número de registros a saltar (offset). Negativos -> 0.
        limit: tamaño de página. Se acota a config.MAX_PAGE_SIZE.
    """
    if skip is None or skip < 0:
        skip = 0
    if not limit or limit < 1:
        limit = 20
    if limit > config.MAX_PAGE_SIZE:
        limit = config.MAX_PAGE_SIZE

    return query.offset(skip).limit(limit)

def get_pagination_info(total: int, page: int, page_size: int) -> Dict[str, Any]:
    """Obtener información de paginación"""
    pages = (total + page_size - 1) // page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1
    }


# Dirección por defecto del desempate: se ordena por la clave primaria en el
# MISMO sentido que el campo principal, para que el orden sea estable.
def apply_ordering(query, model, sort_by: Optional[str] = None,
                   sort_order: str = "desc", default_column: Optional[str] = 'created_at'):
    """
    Aplica un ORDER BY estable a una query.

    El motivo del desempate: todas las filas creadas en el mismo segundo
    comparten `created_at`, así que un ORDER BY sobre esa columna deja el orden
    indefinido. Con paginación por offset eso hace que aparezcan registros
    repetidos y que otros no se vean nunca. Se añade siempre la clave primaria
    como segundo criterio.

    `sort_by` se valida contra las columnas REALES de la tabla (no con hasattr),
    para no aceptar nombres de relaciones ni atributos internos.
    """
    columnas = {c.key for c in inspect(model).columns}

    descendente = (sort_order or "desc").lower() != "asc"

    if sort_by and sort_by in columnas:
        columna = getattr(model, sort_by)
    elif default_column and default_column in columnas:
        columna = getattr(model, default_column)
    else:
        columna = None

    criterios = []
    if columna is not None:
        criterios.append(desc(columna) if descendente else asc(columna))
    # Desempate por clave primaria: sin esto el orden (y la paginación) es
    # indeterminado cuando hay valores repetidos.
    if 'id' in columnas and (columna is None or columna.key != 'id'):
        criterios.append(desc(model.id) if descendente else asc(model.id))

    return query.order_by(*criterios) if criterios else query

# ============================================
# CRUD - USUARIOS
# ============================================

class CRUDUser:
    """Operaciones CRUD para usuarios"""
    
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[models.User]:
        """Obtener usuario por ID"""
        return db.query(models.User).filter(models.User.id == user_id).first()
    
    @staticmethod
    def get_by_uuid(db: Session, uuid: str) -> Optional[models.User]:
        """Obtener usuario por UUID"""
        return db.query(models.User).filter(models.User.uuid == uuid).first()
    
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[models.User]:
        """Obtener usuario por email"""
        return db.query(models.User).filter(models.User.email == email).first()
    
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[models.User]:
        """Obtener usuario por username"""
        return db.query(models.User).filter(models.User.username == username).first()
    
    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        role: Optional[models.UserRole] = None,
        status: Optional[models.UserStatus] = None,
        is_active: Optional[bool] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: str = "desc"
    ) -> List[models.User]:
        """Obtener todos los usuarios con filtros"""
        query = db.query(models.User)
        
        # Aplicar filtros
        if search:
            query = query.filter(
                or_(
                    models.User.email.ilike(f"%{search}%"),
                    models.User.username.ilike(f"%{search}%"),
                    models.User.first_name.ilike(f"%{search}%"),
                    models.User.last_name.ilike(f"%{search}%")
                )
            )
        
        if role:
            query = query.filter(models.User.role == role)
        
        if status:
            query = query.filter(models.User.status == status)
        
        if is_active is not None:
            query = query.filter(models.User.is_active == is_active)
        
        # Aplicar ordenamiento (con desempate por id para que la paginación sea estable)
        query = apply_ordering(query, models.User, sort_by, sort_order)
        
        # Paginación
        query = apply_pagination(query, skip, limit)
        
        return query.all()
    
    @staticmethod
    def count_users(
        db: Session,
        search: Optional[str] = None,
        role: Optional[models.UserRole] = None,
        status: Optional[models.UserStatus] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """Contar usuarios con filtros"""
        query = db.query(models.User)
        
        if search:
            query = query.filter(
                or_(
                    models.User.email.ilike(f"%{search}%"),
                    models.User.username.ilike(f"%{search}%"),
                    models.User.first_name.ilike(f"%{search}%"),
                    models.User.last_name.ilike(f"%{search}%")
                )
            )
        
        if role:
            query = query.filter(models.User.role == role)
        
        if status:
            query = query.filter(models.User.status == status)
        
        if is_active is not None:
            query = query.filter(models.User.is_active == is_active)
        
        return query.count()
    
    @staticmethod
    def create(db: Session, user_data: schemas.UserCreate) -> models.User:
        """Crear un nuevo usuario"""
        # Verificar que email y username no existan
        if CRUDUser.get_by_email(db, user_data.email):
            raise ValueError(f"El email {user_data.email} ya está registrado")
        
        if CRUDUser.get_by_username(db, user_data.username):
            raise ValueError(f"El username {user_data.username} ya está en uso")
        
        # Crear usuario
        # El rol NO se toma de la entrada: `UserCreate` ya no expone `role`,
        # porque permitirlo en el registro público dejaba que cualquiera se
        # creara una cuenta de administrador. Un admin promueve después con
        # PATCH /users/{id}/role.
        #
        # El estado es ACTIVE desde el principio: antes nacían como PENDING
        # esperando una verificación de email que nunca se enviaba (no hay SMTP),
        # así que el estado no significaba nada. `is_verified` se conserva en la
        # tabla como campo reservado por si algún día se implementa.
        hashed_password = get_password_hash(user_data.password)
        db_user = models.User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            role=models.UserRole.USER,
            status=models.UserStatus.ACTIVE
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"Usuario creado: {db_user.email}")
        return db_user
    
    @staticmethod
    def update(db: Session, user_id: int, user_data: schemas.UserUpdate) -> models.User:
        """Actualizar un usuario"""
        db_user = CRUDUser.get_by_id(db, user_id)
        if not db_user:
            raise ValueError(f"Usuario {user_id} no encontrado")
        
        update_data = user_data.model_dump(exclude_unset=True)
        
        # Si se actualiza email, verificar que no exista
        if "email" in update_data and update_data["email"] != db_user.email:
            if CRUDUser.get_by_email(db, update_data["email"]):
                raise ValueError(f"El email {update_data['email']} ya está registrado")
        
        # Si se actualiza username, verificar que no exista
        if "username" in update_data and update_data["username"] != db_user.username:
            if CRUDUser.get_by_username(db, update_data["username"]):
                raise ValueError(f"El username {update_data['username']} ya está en uso")
        
        # Si se actualiza password, hashearla
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        # Actualizar campos
        for key, value in update_data.items():
            setattr(db_user, key, value)
        
        db_user.updated_at = datetime.now()
        db.commit()
        db.refresh(db_user)
        logger.info(f"Usuario actualizado: {db_user.email}")
        return db_user
    
    @staticmethod
    def delete(db: Session, user_id: int, soft: bool = True) -> bool:
        """Eliminar un usuario (soft delete por defecto)"""
        db_user = CRUDUser.get_by_id(db, user_id)
        if not db_user:
            raise ValueError(f"Usuario {user_id} no encontrado")
        
        if soft:
            # Soft delete: solo desactivar
            db_user.is_active = False
            db_user.status = models.UserStatus.INACTIVE
            db_user.updated_at = datetime.now()
            db.commit()
            logger.info(f"Usuario desactivado: {db_user.email}")
        else:
            # Hard delete: eliminar permanentemente
            db.delete(db_user)
            db.commit()
            logger.info(f"Usuario eliminado permanentemente: {db_user.email}")
        
        return True
    
    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> Optional[models.User]:
        """Autenticar un usuario"""
        user = CRUDUser.get_by_email(db, email)
        if not user:
            return None
        
        if not user.is_active:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        # Actualizar último login
        user.last_login = datetime.now()
        db.commit()
        
        return user
    
    @staticmethod
    def change_password(
        db: Session,
        user_id: int,
        old_password: str,
        new_password: str
    ) -> models.User:
        """Cambiar contraseña de usuario"""
        db_user = CRUDUser.get_by_id(db, user_id)
        if not db_user:
            raise ValueError(f"Usuario {user_id} no encontrado")
        
        if not verify_password(old_password, db_user.hashed_password):
            raise ValueError("Contraseña actual incorrecta")
        
        # Defensa en profundidad: la política se valida también en el esquema
        # Pydantic, pero así queda cubierto cualquier uso programático del CRUD.
        schemas.validar_fortaleza_password(new_password)
        
        db_user.hashed_password = get_password_hash(new_password)
        db_user.updated_at = datetime.now()
        db.commit()
        db.refresh(db_user)
        logger.info(f"Contraseña cambiada para: {db_user.email}")
        return db_user
    
    @staticmethod
    def get_statistics(db: Session) -> Dict[str, Any]:
        """Obtener estadísticas de usuarios"""
        total = db.query(models.User).count()
        active = db.query(models.User).filter(models.User.is_active == True).count()
        verified = db.query(models.User).filter(models.User.is_verified == True).count()
        
        roles = db.query(
            models.User.role,
            func.count(models.User.id).label('count')
        ).group_by(models.User.role).all()
        
        return {
            "total_users": total,
            "active_users": active,
            "verified_users": verified,
            "roles": [{"role": r.role.value, "count": r.count} for r in roles]
        }

# ============================================
# CRUD - PRODUCTOS
# ============================================

class CRUDProduct:
    """Operaciones CRUD para productos"""
    
    @staticmethod
    def get_by_id(db: Session, product_id: int) -> Optional[models.Product]:
        """Obtener producto por ID"""
        return db.query(models.Product).filter(models.Product.id == product_id).first()
    
    @staticmethod
    def get_by_uuid(db: Session, uuid: str) -> Optional[models.Product]:
        """Obtener producto por UUID"""
        return db.query(models.Product).filter(models.Product.uuid == uuid).first()
    
    @staticmethod
    def get_by_sku(db: Session, sku: str) -> Optional[models.Product]:
        """Obtener producto por SKU"""
        return db.query(models.Product).filter(models.Product.sku == sku).first()
    
    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock: Optional[bool] = None,
        status: Optional[models.ProductStatus] = None,
        is_active: Optional[bool] = None,
        is_featured: Optional[bool] = None,
        owner_id: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: str = "desc"
    ) -> List[models.Product]:
        """Obtener todos los productos con filtros"""
        query = db.query(models.Product)
        
        # Aplicar filtros
        if search:
            query = query.filter(
                or_(
                    models.Product.name.ilike(f"%{search}%"),
                    models.Product.description.ilike(f"%{search}%"),
                    models.Product.sku.ilike(f"%{search}%"),
                    models.Product.brand.ilike(f"%{search}%")
                )
            )
        
        if category:
            query = query.filter(models.Product.category == category)
        
        if brand:
            query = query.filter(models.Product.brand.ilike(f"%{brand}%"))
        
        if min_price is not None:
            query = query.filter(models.Product.price >= min_price)
        
        if max_price is not None:
            query = query.filter(models.Product.price <= max_price)
        
        if in_stock is not None:
            if in_stock:
                query = query.filter(models.Product.stock > 0)
            else:
                query = query.filter(models.Product.stock == 0)
        
        if status:
            query = query.filter(models.Product.status == status)
        
        if is_active is not None:
            query = query.filter(models.Product.is_active == is_active)
        
        if is_featured is not None:
            query = query.filter(models.Product.is_featured == is_featured)
        
        if owner_id:
            query = query.filter(models.Product.owner_id == owner_id)
        
        # Aplicar ordenamiento (con desempate por id para que la paginación sea estable)
        query = apply_ordering(query, models.Product, sort_by, sort_order)
        
        # Paginación
        query = apply_pagination(query, skip, limit)
        
        return query.all()
    
    @staticmethod
    def count_products(
        db: Session,
        search: Optional[str] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock: Optional[bool] = None,
        status: Optional[models.ProductStatus] = None,
        is_active: Optional[bool] = None,
        is_featured: Optional[bool] = None,
        owner_id: Optional[int] = None
    ) -> int:
        """Contar productos con filtros"""
        query = db.query(models.Product)
        
        if search:
            query = query.filter(
                or_(
                    models.Product.name.ilike(f"%{search}%"),
                    models.Product.description.ilike(f"%{search}%"),
                    models.Product.sku.ilike(f"%{search}%")
                )
            )
        
        if category:
            query = query.filter(models.Product.category == category)
        
        if min_price is not None:
            query = query.filter(models.Product.final_price >= min_price)
        
        if max_price is not None:
            query = query.filter(models.Product.final_price <= max_price)
        
        if in_stock is not None:
            if in_stock:
                query = query.filter(models.Product.stock > 0)
            else:
                query = query.filter(models.Product.stock == 0)
        
        if status:
            query = query.filter(models.Product.status == status)
        
        if is_active is not None:
            query = query.filter(models.Product.is_active == is_active)
        
        if is_featured is not None:
            query = query.filter(models.Product.is_featured == is_featured)
        
        if owner_id:
            query = query.filter(models.Product.owner_id == owner_id)
        
        return query.count()
    
    @staticmethod
    def create(db: Session, product_data: schemas.ProductCreate) -> models.Product:
        """Crear un nuevo producto"""
        # Verificar que el owner existe
        user = CRUDUser.get_by_id(db, product_data.owner_id)
        if not user:
            raise ValueError(f"Usuario {product_data.owner_id} no encontrado")
        
        # Verificar SKU único
        if product_data.sku:
            existing = CRUDProduct.get_by_sku(db, product_data.sku)
            if existing:
                raise ValueError(f"El SKU {product_data.sku} ya está en uso")
        
        # Crear producto
        db_product = models.Product(
            name=product_data.name,
            description=product_data.description,
            price=product_data.price,
            discount_price=product_data.discount_price,
            stock=product_data.stock,
            sku=product_data.sku,
            category=product_data.category,
            brand=product_data.brand,
            main_image=product_data.main_image,
            is_featured=product_data.is_featured,
            owner_id=product_data.owner_id,
            status=models.ProductStatus.PENDING
        )
        
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        logger.info(f"Producto creado: {db_product.name} (SKU: {db_product.sku})")
        return db_product
    
    @staticmethod
    def update(db: Session, product_id: int, product_data: schemas.ProductUpdate) -> models.Product:
        """Actualizar un producto"""
        db_product = CRUDProduct.get_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Producto {product_id} no encontrado")
        
        update_data = product_data.model_dump(exclude_unset=True)
        
        # Verificar SKU único si se actualiza
        if "sku" in update_data and update_data["sku"] != db_product.sku:
            existing = CRUDProduct.get_by_sku(db, update_data["sku"])
            if existing:
                raise ValueError(f"El SKU {update_data['sku']} ya está en uso")
        
        # Actualizar campos
        for key, value in update_data.items():
            setattr(db_product, key, value)
        
        db_product.updated_at = datetime.now()
        db.commit()
        db.refresh(db_product)
        logger.info(f"Producto actualizado: {db_product.name}")
        return db_product
    
    @staticmethod
    def delete(db: Session, product_id: int, soft: bool = True) -> bool:
        """Eliminar un producto"""
        db_product = CRUDProduct.get_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Producto {product_id} no encontrado")
        
        if soft:
            db_product.is_active = False
            db_product.status = models.ProductStatus.DISCONTINUED
            db_product.updated_at = datetime.now()
            db.commit()
            logger.info(f"Producto desactivado: {db_product.name}")
        else:
            db.delete(db_product)
            db.commit()
            logger.info(f"Producto eliminado permanentemente: {db_product.name}")
        
        return True
    
    @staticmethod
    def update_stock(db: Session, product_id: int, quantity: int) -> models.Product:
        """Actualizar stock de un producto"""
        db_product = CRUDProduct.get_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Producto {product_id} no encontrado")
        
        new_stock = db_product.stock + quantity
        if new_stock < 0:
            raise ValueError(f"Stock insuficiente. Stock actual: {db_product.stock}")
        
        db_product.stock = new_stock
        
        # Actualizar estado según stock
        if db_product.stock == 0:
            db_product.status = models.ProductStatus.OUT_OF_STOCK
        elif db_product.status == models.ProductStatus.OUT_OF_STOCK:
            db_product.status = models.ProductStatus.AVAILABLE
        
        db_product.updated_at = datetime.now()
        db.commit()
        db.refresh(db_product)
        logger.info(f"Stock actualizado para {db_product.name}: {new_stock}")
        return db_product
    
    @staticmethod
    def increment_view(db: Session, product_id: int) -> models.Product:
        """Incrementar contador de vistas"""
        db_product = CRUDProduct.get_by_id(db, product_id)
        if db_product:
            db_product.views_count += 1
            db.commit()
            db.refresh(db_product)
        return db_product
    
    @staticmethod
    def update_rating(db: Session, product_id: int) -> models.Product:
        """Actualizar rating promedio de un producto"""
        from api.models import Review
        
        db_product = CRUDProduct.get_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Producto {product_id} no encontrado")
        
        stats = db.query(
            func.avg(Review.rating).label('avg_rating'),
            func.count(Review.id).label('count')
        ).filter(Review.product_id == product_id).first()
        
        if stats.count > 0:
            db_product.rating_avg = float(stats.avg_rating) if stats.avg_rating else 0
            db_product.rating_count = stats.count
        else:
            db_product.rating_avg = 0
            db_product.rating_count = 0
        
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def get_featured(db: Session, limit: int = 10) -> List[models.Product]:
        """Obtener productos destacados"""
        return db.query(models.Product).filter(
            models.Product.is_featured == True,
            models.Product.is_active == True,
            models.Product.status == models.ProductStatus.AVAILABLE,
            models.Product.stock > 0
        ).order_by(desc(models.Product.rating_avg)).limit(limit).all()
    
    @staticmethod
    def get_best_sellers(db: Session, limit: int = 10) -> List[models.Product]:
        """Obtener productos más vendidos"""
        return db.query(models.Product).filter(
            models.Product.is_active == True,
            models.Product.status == models.ProductStatus.AVAILABLE
        ).order_by(desc(models.Product.sales_count)).limit(limit).all()

# ============================================
# CRUD - ÓRDENES
# ============================================

class CRUDOrder:
    """Operaciones CRUD para órdenes"""
    
    @staticmethod
    def generate_order_number() -> str:
        """Generar número de orden único"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        import random
        random_suffix = ''.join(random.choices('0123456789', k=4))
        return f"ORD-{timestamp}-{random_suffix}"
    
    @staticmethod
    def get_by_id(db: Session, order_id: int) -> Optional[models.Order]:
        """Obtener orden por ID"""
        return db.query(models.Order).filter(models.Order.id == order_id).first()
    
    @staticmethod
    def get_by_uuid(db: Session, uuid: str) -> Optional[models.Order]:
        """Obtener orden por UUID"""
        return db.query(models.Order).filter(models.Order.uuid == uuid).first()
    
    @staticmethod
    def get_by_order_number(db: Session, order_number: str) -> Optional[models.Order]:
        """Obtener orden por número de orden"""
        return db.query(models.Order).filter(models.Order.order_number == order_number).first()
    
    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
        status: Optional[models.OrderStatus] = None,
        payment_status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_total: Optional[float] = None,
        max_total: Optional[float] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: str = "desc"
    ) -> List[models.Order]:
        """Obtener todas las órdenes con filtros"""
        query = db.query(models.Order)
        
        if user_id:
            query = query.filter(models.Order.user_id == user_id)
        
        if status:
            query = query.filter(models.Order.status == status)
        
        if payment_status:
            query = query.filter(models.Order.payment_status == payment_status)
        
        if date_from:
            query = query.filter(models.Order.created_at >= date_from)
        
        if date_to:
            query = query.filter(models.Order.created_at <= date_to)
        
        if min_total is not None:
            query = query.filter(models.Order.total >= min_total)
        
        if max_total is not None:
            query = query.filter(models.Order.total <= max_total)
        
        # Aplicar ordenamiento (con desempate por id para que la paginación sea estable)
        query = apply_ordering(query, models.Order, sort_by, sort_order)
        
        # Paginación
        query = apply_pagination(query, skip, limit)
        
        return query.all()
    
    @staticmethod
    def create(db: Session, order_data: schemas.OrderCreate, user_id: int) -> models.Order:
        """Crear una nueva orden"""
        # Verificar que el usuario existe
        user = CRUDUser.get_by_id(db, user_id)
        if not user:
            raise ValueError(f"Usuario {user_id} no encontrado")
        
        # Calcular totales
        subtotal = 0.0
        order_items = []
        
        for item_data in order_data.items:
            # Verificar que el producto existe y tiene stock
            product = CRUDProduct.get_by_id(db, item_data.product_id)
            if not product:
                raise ValueError(f"Producto {item_data.product_id} no encontrado")
            
            if product.stock < item_data.quantity:
                raise ValueError(f"Stock insuficiente para {product.name}. Disponible: {product.stock}")
            
            # Calcular precio
            unit_price = product.final_price if item_data.unit_price == 0 else item_data.unit_price
            total_price = unit_price * item_data.quantity
            
            # Crear ítem de orden (temporal)
            order_items.append({
                "product_id": item_data.product_id,
                "quantity": item_data.quantity,
                "unit_price": unit_price,
                "discount_per_item": item_data.discount_per_item or 0,
                "total_price": total_price
            })
            
            subtotal += total_price
            
            # Actualizar stock
            CRUDProduct.update_stock(db, product.id, -item_data.quantity)
        
        # Calcular impuestos y total
        tax = subtotal * 0.18  # 18% IVA (ejemplo)
        total = subtotal + tax
        
        # Crear orden
        order_number = CRUDOrder.generate_order_number()
        db_order = models.Order(
            order_number=order_number,
            user_id=user_id,
            status=models.OrderStatus.PENDING,
            subtotal=subtotal,
            tax=tax,
            total=total,
            shipping_address=order_data.shipping_address,
            billing_address=order_data.billing_address,
            payment_method=order_data.payment_method,
            shipping_method=order_data.shipping_method,
            notes=order_data.notes
        )
        
        db.add(db_order)
        db.flush()  # Para obtener el ID de la orden
        
        # Crear ítems de orden
        for item in order_items:
            db_item = models.OrderItem(
                order_id=db_order.id,
                **item
            )
            db.add(db_item)
        
        db.commit()
        db.refresh(db_order)
        logger.info(f"Orden creada: {db_order.order_number} - Total: ${db_order.total}")
        return db_order
    
    @staticmethod
    def update_status(
        db: Session,
        order_id: int,
        status: models.OrderStatus
    ) -> models.Order:
        """Actualizar estado de una orden"""
        db_order = CRUDOrder.get_by_id(db, order_id)
        if not db_order:
            raise ValueError(f"Orden {order_id} no encontrada")
        
        old_status = db_order.status
        db_order.status = status
        
        # Actualizar fechas según estado
        now = datetime.now()
        if status == models.OrderStatus.SHIPPED and not db_order.shipped_at:
            db_order.shipped_at = now
        elif status == models.OrderStatus.DELIVERED and not db_order.delivered_at:
            db_order.delivered_at = now
        
        db_order.updated_at = now
        db.commit()
        db.refresh(db_order)
        logger.info(f"Orden {db_order.order_number}: {old_status} -> {status}")
        return db_order
    
    @staticmethod
    def update_payment(
        db: Session,
        order_id: int,
        payment_status: str,
        payment_id: Optional[str] = None
    ) -> models.Order:
        """Actualizar estado de pago de una orden"""
        db_order = CRUDOrder.get_by_id(db, order_id)
        if not db_order:
            raise ValueError(f"Orden {order_id} no encontrada")
        
        db_order.payment_status = payment_status
        if payment_id:
            db_order.payment_id = payment_id
        
        # Si el pago es exitoso, cambiar estado a procesando
        if payment_status == "paid" and db_order.status == models.OrderStatus.PENDING:
            db_order.status = models.OrderStatus.PROCESSING
        
        db_order.updated_at = datetime.now()
        db.commit()
        db.refresh(db_order)
        logger.info(f"Pago actualizado para orden {db_order.order_number}: {payment_status}")
        return db_order
    
    @staticmethod
    def cancel(db: Session, order_id: int, reason: Optional[str] = None) -> models.Order:
        """Cancelar una orden y devolver stock"""
        db_order = CRUDOrder.get_by_id(db, order_id)
        if not db_order:
            raise ValueError(f"Orden {order_id} no encontrada")
        
        # Solo se pueden cancelar órdenes pendientes o en procesamiento
        if db_order.status not in [models.OrderStatus.PENDING, models.OrderStatus.PROCESSING]:
            raise ValueError(f"No se puede cancelar una orden en estado {db_order.status}")
        
        # Devolver stock
        for item in db_order.items:
            CRUDProduct.update_stock(db, item.product_id, item.quantity)
        
        db_order.status = models.OrderStatus.CANCELLED
        if reason:
            db_order.notes = f"{db_order.notes or ''}\nCancelado: {reason}"
        
        db_order.updated_at = datetime.now()
        db.commit()
        db.refresh(db_order)
        logger.info(f"Orden cancelada: {db_order.order_number}")
        return db_order
    
    @staticmethod
    def get_user_orders(db: Session, user_id: int, limit: int = 50) -> List[models.Order]:
        """Obtener órdenes de un usuario"""
        return db.query(models.Order).filter(
            models.Order.user_id == user_id
        ).order_by(desc(models.Order.created_at)).limit(limit).all()
    
    @staticmethod
    def get_statistics(db: Session) -> Dict[str, Any]:
        """Obtener estadísticas de órdenes"""
        total_orders = db.query(models.Order).count()
        
        by_status = db.query(
            models.Order.status,
            func.count(models.Order.id).label('count')
        ).group_by(models.Order.status).all()
        
        total_revenue = db.query(
            func.sum(models.Order.total)
        ).filter(
            models.Order.status == models.OrderStatus.DELIVERED
        ).scalar() or 0
        
        recent_orders = db.query(models.Order).order_by(
            desc(models.Order.created_at)
        ).limit(10).all()
        
        return {
            "total_orders": total_orders,
            "by_status": [{"status": s.status.value, "count": s.count} for s in by_status],
            "total_revenue": float(total_revenue),
            "recent_orders": recent_orders
        }

# ============================================
# CRUD - RESEÑAS
# ============================================

class CRUDReview:
    """Operaciones CRUD para reseñas"""
    
    @staticmethod
    def get_by_id(db: Session, review_id: int) -> Optional[models.Review]:
        """Obtener reseña por ID"""
        return db.query(models.Review).filter(models.Review.id == review_id).first()
    
    @staticmethod
    def get_by_user_and_product(
        db: Session,
        user_id: int,
        product_id: int
    ) -> Optional[models.Review]:
        """Obtener reseña de un usuario para un producto"""
        return db.query(models.Review).filter(
            models.Review.user_id == user_id,
            models.Review.product_id == product_id
        ).first()
    
    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        product_id: Optional[int] = None,
        user_id: Optional[int] = None,
        rating: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: str = "desc"
    ) -> List[models.Review]:
        """Obtener todas las reseñas con filtros"""
        query = db.query(models.Review)
        
        if product_id:
            query = query.filter(models.Review.product_id == product_id)
        
        if user_id:
            query = query.filter(models.Review.user_id == user_id)
        
        if rating:
            query = query.filter(models.Review.rating == rating)
        
        # Aplicar ordenamiento (con desempate por id para que la paginación sea estable)
        query = apply_ordering(query, models.Review, sort_by, sort_order)
        
        # Paginación
        query = apply_pagination(query, skip, limit)
        
        return query.all()
    
    @staticmethod
    def create(db: Session, review_data: schemas.ReviewCreate, user_id: int) -> models.Review:
        """Crear una nueva reseña"""
        # Verificar que el producto existe
        product = CRUDProduct.get_by_id(db, review_data.product_id)
        if not product:
            raise ValueError(f"Producto {review_data.product_id} no encontrado")
        
        # Verificar que el usuario no haya reseñado este producto
        existing = CRUDReview.get_by_user_and_product(db, user_id, review_data.product_id)
        if existing:
            raise ValueError("Ya has reseñado este producto")
        
        # Crear reseña
        db_review = models.Review(
            user_id=user_id,
            product_id=review_data.product_id,
            rating=review_data.rating,
            comment=review_data.comment
        )
        
        db.add(db_review)
        db.commit()
        db.refresh(db_review)
        
        # Actualizar rating del producto
        CRUDProduct.update_rating(db, review_data.product_id)
        
        logger.info(f"Reseña creada para producto {review_data.product_id} por usuario {user_id}")
        return db_review
    
    @staticmethod
    def update(db: Session, review_id: int, review_data: schemas.ReviewUpdate) -> models.Review:
        """Actualizar una reseña"""
        db_review = CRUDReview.get_by_id(db, review_id)
        if not db_review:
            raise ValueError(f"Reseña {review_id} no encontrada")
        
        update_data = review_data.model_dump(exclude_unset=True)
        
        for key, value in update_data.items():
            setattr(db_review, key, value)
        
        db_review.updated_at = datetime.now()
        db.commit()
        db.refresh(db_review)
        
        # Actualizar rating del producto
        CRUDProduct.update_rating(db, db_review.product_id)
        
        logger.info(f"Reseña {review_id} actualizada")
        return db_review
    
    @staticmethod
    def delete(db: Session, review_id: int) -> bool:
        """Eliminar una reseña"""
        db_review = CRUDReview.get_by_id(db, review_id)
        if not db_review:
            raise ValueError(f"Reseña {review_id} no encontrada")
        
        product_id = db_review.product_id
        db.delete(db_review)
        db.commit()
        
        # Actualizar rating del producto
        CRUDProduct.update_rating(db, product_id)
        
        logger.info(f"Reseña {review_id} eliminada")
        return True
    
    @staticmethod
    def get_product_rating_stats(db: Session, product_id: int) -> Dict[str, Any]:
        """Obtener estadísticas de rating para un producto"""
        stats = db.query(
            func.avg(models.Review.rating).label('avg'),
            func.count(models.Review.id).label('count'),
            func.count(func.nullif(models.Review.rating <= 2, True)).label('positive'),
            func.count(func.nullif(models.Review.rating == 3, True)).label('neutral'),
            func.count(func.nullif(models.Review.rating >= 4, True)).label('negative')
        ).filter(models.Review.product_id == product_id).first()
        
        return {
            "average": float(stats.avg) if stats.avg else 0,
            "total": stats.count or 0,
            "distribution": {
                "1": db.query(models.Review).filter(
                    models.Review.product_id == product_id,
                    models.Review.rating == 1
                ).count(),
                "2": db.query(models.Review).filter(
                    models.Review.product_id == product_id,
                    models.Review.rating == 2
                ).count(),
                "3": db.query(models.Review).filter(
                    models.Review.product_id == product_id,
                    models.Review.rating == 3
                ).count(),
                "4": db.query(models.Review).filter(
                    models.Review.product_id == product_id,
                    models.Review.rating == 4
                ).count(),
                "5": db.query(models.Review).filter(
                    models.Review.product_id == product_id,
                    models.Review.rating == 5
                ).count()
            }
        }

# ============================================
# CRUD - CATEGORÍAS
# ============================================

class CRUDCategory:
    """Operaciones CRUD para categorías"""
    
    @staticmethod
    def get_by_id(db: Session, category_id: int) -> Optional[models.Category]:
        """Obtener categoría por ID"""
        return db.query(models.Category).filter(models.Category.id == category_id).first()
    
    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Optional[models.Category]:
        """Obtener categoría por slug"""
        return db.query(models.Category).filter(models.Category.slug == slug).first()
    
    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        parent_id: Optional[int] = None
    ) -> List[models.Category]:
        """Obtener todas las categorías"""
        query = db.query(models.Category)
        
        if is_active is not None:
            query = query.filter(models.Category.is_active == is_active)
        
        if parent_id is not None:
            query = query.filter(models.Category.parent_id == parent_id)
        
        # Orden por nombre con desempate por id (el nombre no es único)
        query = apply_ordering(query, models.Category, sort_by='name',
                               sort_order='asc', default_column='name')
        query = apply_pagination(query, skip, limit)
        
        return query.all()
    
    @staticmethod
    def create(db: Session, category_data: schemas.CategoryCreate) -> models.Category:
        """Crear una nueva categoría"""
        # Verificar slug único
        existing = CRUDCategory.get_by_slug(db, category_data.slug)
        if existing:
            raise ValueError(f"El slug {category_data.slug} ya está en uso")
        
        # Verificar que el padre existe
        if category_data.parent_id:
            parent = CRUDCategory.get_by_id(db, category_data.parent_id)
            if not parent:
                raise ValueError(f"Categoría padre {category_data.parent_id} no encontrada")
        
        db_category = models.Category(**category_data.model_dump())
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
        logger.info(f"Categoría creada: {db_category.name}")
        return db_category
    
    @staticmethod
    def update(db: Session, category_id: int, category_data: schemas.CategoryUpdate) -> models.Category:
        """Actualizar una categoría"""
        db_category = CRUDCategory.get_by_id(db, category_id)
        if not db_category:
            raise ValueError(f"Categoría {category_id} no encontrada")
        
        update_data = category_data.model_dump(exclude_unset=True)
        
        # Verificar slug único
        if "slug" in update_data and update_data["slug"] != db_category.slug:
            existing = CRUDCategory.get_by_slug(db, update_data["slug"])
            if existing:
                raise ValueError(f"El slug {update_data['slug']} ya está en uso")
        
        for key, value in update_data.items():
            setattr(db_category, key, value)
        
        db_category.updated_at = datetime.now()
        db.commit()
        db.refresh(db_category)
        logger.info(f"Categoría actualizada: {db_category.name}")
        return db_category
    
    @staticmethod
    def delete(db: Session, category_id: int) -> bool:
        """Eliminar una categoría"""
        db_category = CRUDCategory.get_by_id(db, category_id)
        if not db_category:
            raise ValueError(f"Categoría {category_id} no encontrada")
        
        # Verificar que no tenga subcategorías
        children = db.query(models.Category).filter(
            models.Category.parent_id == category_id
        ).count()
        
        if children > 0:
            raise ValueError(f"No se puede eliminar: tiene {children} subcategorías")
        
        db.delete(db_category)
        db.commit()
        logger.info(f"Categoría eliminada: {db_category.name}")
        return True
    
    @staticmethod
    def get_tree(db: Session) -> List[Dict[str, Any]]:
        """Obtener árbol de categorías"""
        def build_tree(parent_id=None):
            categories = db.query(models.Category).filter(
                models.Category.parent_id == parent_id,
                models.Category.is_active == True
            ).order_by(models.Category.name).all()
            
            return [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "slug": cat.slug,
                    "description": cat.description,
                    "icon": cat.icon,
                    "children": build_tree(cat.id)
                }
                for cat in categories
            ]
        
        return build_tree()

# ============================================
# EXPORTAR TODAS LAS CLASES
# ============================================

__all__ = [
    'CRUDUser',
    'CRUDProduct', 
    'CRUDOrder',
    'CRUDReview',
    'CRUDCategory',
    'get_password_hash',
    'verify_password',
    'apply_pagination',
    'get_pagination_info'
]


# api/crud.py - Agregar al final del archivo

# ============================================
# CRUD - PREDICCIONES
# ============================================

class CRUDPrediction:
    """Operaciones CRUD para predicciones"""
    
    @staticmethod
    def get_by_id(db: Session, prediction_id: int) -> Optional[models.Prediction]:
        """Obtener predicción por ID"""
        return db.query(models.Prediction).filter(models.Prediction.id == prediction_id).first()
    
    @staticmethod
    def get_by_user(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> List[models.Prediction]:
        """Obtener predicciones de un usuario"""
        query = db.query(models.Prediction).filter(models.Prediction.user_id == user_id)
        
        # Orden estable: `created_at` empata al segundo entre predicciones
        # seguidas, así que el desempate por id es imprescindible aquí.
        query = apply_ordering(query, models.Prediction, sort_by, sort_order)
        
        query = apply_pagination(query, skip, limit)
        return query.all()
    
    @staticmethod
    def count_by_user(db: Session, user_id: int) -> int:
        """Contar predicciones de un usuario"""
        return db.query(models.Prediction).filter(models.Prediction.user_id == user_id).count()
    
    @staticmethod
    def create(
        db: Session,
        prediction_data: schemas.PredictionCreate,
        user_id: int,
        predicted_price: float,
        confidence: float = 0.0
    ) -> models.Prediction:
        """Crear una nueva predicción"""
        db_prediction = models.Prediction(
            user_id=user_id,
            predicted_price=predicted_price,
            confidence=confidence,
            **prediction_data.model_dump()
        )
        db.add(db_prediction)
        db.commit()
        db.refresh(db_prediction)
        logger.info(f"Predicción creada para usuario {user_id}: ${predicted_price:,.2f}")
        return db_prediction
    
    @staticmethod
    def get_stats(db: Session, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Obtener estadísticas de predicciones.

        IMPORTANTE: todos los desgloses respetan el filtro `user_id`. Antes solo
        lo aplicaba el agregado principal, así que `/predictions/stats/me`
        mostraba los barrios y precios del resto de usuarios (fuga de datos).
        """
        query = db.query(models.Prediction)
        if user_id:
            query = query.filter(models.Prediction.user_id == user_id)

        stats = query.with_entities(
            func.count(models.Prediction.id).label('total'),
            func.avg(models.Prediction.predicted_price).label('avg_price'),
            func.min(models.Prediction.predicted_price).label('min_price'),
            func.max(models.Prediction.predicted_price).label('max_price'),
            func.avg(models.Prediction.confidence).label('avg_confidence')
        ).first()

        # Top barrios (con el mismo filtro de usuario)
        top_barrios = query.with_entities(
            models.Prediction.neighborhood,
            func.count(models.Prediction.id).label('count'),
            func.avg(models.Prediction.predicted_price).label('avg_price')
        ).filter(models.Prediction.neighborhood.isnot(None)).group_by(
            models.Prediction.neighborhood
        ).order_by(func.count(models.Prediction.id).desc()).limit(10).all()

        # Por tipo de vivienda (MSSubClass)
        por_tipo = query.with_entities(
            models.Prediction.ms_subclass,
            func.count(models.Prediction.id).label('count'),
            func.avg(models.Prediction.predicted_price).label('avg_price')
        ).filter(models.Prediction.ms_subclass.isnot(None)).group_by(
            models.Prediction.ms_subclass
        ).all()

        # Etiquetas legibles (import diferido para no acoplar el CRUD al mapper)
        etiquetas_barrio: Dict[str, str] = {}
        etiquetas_tipo: Dict[int, str] = {}
        try:
            from api.feature_mapper import get_contract
            ui = get_contract()['ui']
            etiquetas_barrio = {b['valor']: b['etiqueta'] for b in ui['neighborhoods']}
            etiquetas_tipo = {int(t['valor']): t['etiqueta'] for t in ui['ms_subclass']}
        except Exception as e:
            logger.warning(f"No se pudieron cargar las etiquetas del contrato: {e}")

        return {
            "total_predictions": stats.total or 0,
            "avg_predicted_price": float(stats.avg_price) if stats.avg_price else 0,
            "min_predicted_price": float(stats.min_price) if stats.min_price else 0,
            "max_predicted_price": float(stats.max_price) if stats.max_price else 0,
            "avg_confidence": float(stats.avg_confidence) if stats.avg_confidence else 0,
            "top_neighborhoods": [
                {
                    "neighborhood": d.neighborhood,
                    "label": etiquetas_barrio.get(d.neighborhood, d.neighborhood),
                    "count": d.count,
                    "avg_price": float(d.avg_price) if d.avg_price else 0,
                }
                for d in top_barrios
            ],
            "by_property_type": [
                {
                    "type": t.ms_subclass,
                    "label": etiquetas_tipo.get(t.ms_subclass, f"Tipo {t.ms_subclass}"),
                    "count": t.count,
                    "avg_price": float(t.avg_price) if t.avg_price else 0,
                }
                for t in por_tipo
            ]
        }