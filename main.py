"""
Punto de entrada principal de la API
Configura la aplicación FastAPI y conecta todos los routers
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import logging
import time

from api.config import config
from api.database import create_tables, test_connection, get_missing_tables
from api.rate_limit import LimitadorEnMemoria, RateLimitMiddleware
from api.routers import auth, users, products, orders, reviews, categories, predictions

# ============================================
# CONFIGURACIÓN DE LOGGING
# ============================================

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)


# ============================================
# LIFESPAN (reemplaza on_event)
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Maneja eventos de inicio y cierre de la aplicación.
    Reemplaza los decoradores @app.on_event("startup") y @app.on_event("shutdown")
    """
    # ========== STARTUP ==========
    logger.info("=" * 60)
    logger.info(f"🚀 Iniciando {config.APP_NAME} v{config.APP_VERSION}")
    logger.info(f"📊 Entorno: {config.ENVIRONMENT}")
    logger.info(f"🔗 Base de datos: {config.DATABASE_URL}")
    
    # Crear tablas
    try:
        create_tables()
        logger.info("✅ Tablas creadas/verificadas")
    except Exception as e:
        logger.error(f"❌ Error creando tablas: {e}")

    # Verificar conexión
    if test_connection():
        logger.info("✅ Conexión a base de datos exitosa")
    else:
        logger.warning("⚠️ No se pudo conectar a la base de datos")

    # Verificar que las tablas existen realmente: sin ellas la API da 500 en
    # cualquier consulta aunque la conexión funcione.
    faltantes = get_missing_tables()
    if faltantes:
        logger.error(
            "❌ FALTAN TABLAS EN LA BASE DE DATOS: %s. La API responderá con error 500 "
            "en cualquier endpoint que consulte la base de datos. Revisa el error de "
            "create_tables() unas líneas más arriba.",
            ", ".join(faltantes),
        )
    else:
        logger.info("✅ Todas las tablas están presentes")

    logger.info("=" * 60)
    
    # ========== YIELD (la aplicación se ejecuta aquí) ==========
    yield
    
    # ========== SHUTDOWN ==========
    logger.info("=" * 60)
    logger.info(f"👋 Cerrando {config.APP_NAME}")
    logger.info("=" * 60)


# ============================================
# CREAR APLICACIÓN FASTAPI
# ============================================

app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description=config.APP_DESCRIPTION,
    docs_url="/docs" if config.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if config.ENVIRONMENT != "production" else None,
    lifespan=lifespan,  # ✅ Usar lifespan en lugar de on_event
)


# ============================================
# MIDDLEWARES
# ============================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get_cors_origins(),
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Límite de peticiones para los endpoints sensibles (/api/auth/* y
# /api/predictions/*). La configuración lo declaraba desde el principio pero no
# había ninguna implementación: esto lo cumple. Ver api/rate_limit.py para las
# limitaciones (es por proceso: con varios workers o varias instancias haría
# falta un almacén compartido).
limitador = None
if config.RATE_LIMIT_ENABLED:
    limitador = LimitadorEnMemoria(
        max_peticiones=config.RATE_LIMIT_REQUESTS,
        periodo=config.RATE_LIMIT_PERIOD,
    )
    app.add_middleware(RateLimitMiddleware, limitador=limitador)
    logger.info(
        "🚦 Límite de peticiones activo: %d peticiones cada %ds por IP y ruta",
        config.RATE_LIMIT_REQUESTS, config.RATE_LIMIT_PERIOD,
    )
else:
    logger.warning(
        "⚠️ Límite de peticiones DESACTIVADO (RATE_LIMIT_ENABLED=false)"
    )


# ============================================
# MIDDLEWARE PERSONALIZADO: LOG DE PETICIONES
# ============================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware para registrar todas las peticiones HTTP.
    """
    start_time = time.time()
    
    # Procesar la petición
    response = await call_next(request)
    
    # Calcular tiempo de respuesta
    process_time = time.time() - start_time
    
    # Registrar
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} "
        f"({process_time:.3f}s)"
    )
    
    # Añadir header con tiempo de respuesta
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# ============================================
# MANEJO DE EXCEPCIONES
# ============================================

def _serializar_errores_validacion(exc: RequestValidationError) -> list:
    """
    Convierte los errores de Pydantic en algo serializable a JSON.

    `exc.errors()` de Pydantic v2 incluye, para los errores lanzados por un
    validador propio (`@validator`), la clave `ctx` con el objeto ValueError
    original dentro. Ese objeto no es serializable, así que devolver
    `exc.errors()` tal cual hacía que la respuesta 422 fallara con
    "TypeError: Object of type ValueError is not JSON serializable" y el cliente
    recibiera un 500 en lugar del error de validación.

    Se conservan `loc`, `msg` y `type`, que es lo que necesita el cliente, y se
    añade `input` solo si es serializable.
    """
    limpios = []
    for error in exc.errors():
        item = {
            'loc': [str(parte) for parte in error.get('loc', [])],
            'msg': str(error.get('msg', '')),
            'type': str(error.get('type', '')),
        }
        entrada = error.get('input')
        if isinstance(entrada, (str, int, float, bool, type(None))):
            item['input'] = entrada
        limpios.append(item)
    return limpios


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Maneja errores de validación de Pydantic.
    """
    errores = _serializar_errores_validacion(exc)
    logger.warning(f"Error de validación en {request.url.path}: {errores}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": errores,
            "message": "Error de validación de datos"
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Maneja cualquier excepción no capturada.
    """
    logger.error(f"Error no controlado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Error interno del servidor",
            "message": str(exc) if config.ENVIRONMENT != "production" else "Ha ocurrido un error inesperado"
        }
    )


# ============================================
# CONECTAR ROUTERS
# ============================================

# Router de autenticación
app.include_router(auth.router, prefix="/api")

# Router de usuarios
app.include_router(users.router, prefix="/api")

# Router de productos
app.include_router(products.router, prefix="/api")

# Router de órdenes
app.include_router(orders.router, prefix="/api")

# Router de reseñas
app.include_router(reviews.router, prefix="/api")

# Router de categorías
app.include_router(categories.router, prefix="/api")

# Router de predicciones
app.include_router(predictions.router, prefix="/api")


# ============================================
# ENDPOINTS BÁSICOS
# ============================================

@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": f"Bienvenido a {config.APP_NAME}",
        "version": config.APP_VERSION,
        "environment": config.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
        "status": "online"
    }


@app.get("/health")
async def health_check():
    """Verificar estado de la API"""
    db_status = test_connection()
    faltantes = get_missing_tables() if db_status else []

    if not db_status:
        status_value = "degraded"
        db_detail = "disconnected"
    elif faltantes:
        status_value = "degraded"
        db_detail = f"connected, missing tables: {', '.join(faltantes)}"
    else:
        status_value = "healthy"
        db_detail = "connected"

    return {
        "status": status_value,
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "environment": config.ENVIRONMENT,
        "database": db_detail,
        "timestamp": time.time()
    }


@app.get("/ping")
async def ping():
    """Endpoint simple para verificar que la API responde"""
    return {"pong": True, "timestamp": time.time()}


# ============================================
# CONFIGURACIÓN DE DOCUMENTACIÓN
# ============================================

# Personalizar OpenAPI
app.openapi_tags = [
    {
        "name": "autenticación",
        "description": "Endpoints para registro, login y gestión de tokens"
    },
    {
        "name": "usuarios",
        "description": "Gestión de usuarios (CRUD)"
    },
    {
        "name": "productos",
        "description": "Gestión de productos (CRUD)"
    },
    {
        "name": "órdenes",
        "description": "Gestión de órdenes de compra"
    },
    {
        "name": "reseñas",
        "description": "Gestión de reseñas y calificaciones de productos"
    },
    {
        "name": "categorías",
        "description": "Gestión de categorías de productos"
    }
]


# ============================================
# EJECUCIÓN DIRECTA
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        workers=config.WORKERS,
        log_level=config.LOG_LEVEL.lower()
    )