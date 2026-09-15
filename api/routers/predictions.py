"""
Router de predicciones
Endpoints para usar el modelo de Machine Learning
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import joblib
import numpy as np
import os
from datetime import datetime

from api.database import get_db
from api.auth import get_current_active_user, is_admin
from api.crud import CRUDPrediction, CRUDProduct
from api.schemas import (
    PredictionCreate,
    PredictionResponse,
    PredictionHistoryResponse,
    PredictionStats,
    MessageResponse
)
from api.models import User, Prediction
from api.feature_mapper import (
    get_contract,
    get_feature_info,
    get_options,
    predict_from_user,
    user_fields_to_ames,
)

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/predictions",
    tags=["predicciones"]
)

# ============================================
# CARGAR MODELO Y SCALER
# ============================================

MODEL_PATH = os.getenv('MODEL_PATH', 'models_saved/RandomForest_Tuned.pkl')
SCALER_PATH = os.getenv('SCALER_PATH', 'models_saved/scaler.pkl')

# Cargar modelo
model = None
scaler = None

try:
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        logger.info(f"✅ Modelo cargado desde: {MODEL_PATH}")
        if hasattr(model, 'estimators_'):
            logger.info(f"   📊 Número de árboles: {len(model.estimators_)}")
    else:
        logger.error(f"❌ Modelo no encontrado en: {MODEL_PATH}")
        logger.info("   📁 Buscando archivos en models_saved/...")
        if os.path.exists('models_saved'):
            files = os.listdir('models_saved')
            logger.info(f"   📄 Archivos disponibles: {', '.join(files)}")
except Exception as e:
    logger.error(f"❌ Error cargando modelo: {e}")

try:
    if os.path.exists(SCALER_PATH):
        scaler = joblib.load(SCALER_PATH)
        logger.info(f"✅ Scaler cargado desde: {SCALER_PATH}")
    else:
        logger.warning(f"⚠️ Scaler no encontrado en: {SCALER_PATH}")
except Exception as e:
    logger.warning(f"⚠️ Error cargando scaler: {e}")

# Log de información del contrato de características
try:
    _info = get_feature_info()
    logger.info(f"📊 Modelo espera {_info['total_features']} características")
    logger.info(f"   🏘️  Barrios disponibles: {len(_info['neighborhoods'])}")
    logger.info(f"   🏠 Tipos de vivienda: {len(_info['ms_subclass'])}")
    logger.info(f"   📅 Dataset: {_info['dataset']} | moneda {_info['moneda']}")
except Exception as e:
    logger.error(
        f"❌ No se pudo cargar el contrato de características: {e}. "
        "La API no podrá predecir. Genéralo con: python src/data/feature_contract.py"
    )


# ============================================
# FUNCIÓN DE PREDICCIÓN
# ============================================

def predict_price(features: dict) -> tuple[float, float]:
    """
    Predice el precio de una vivienda a partir de los 9 campos del formulario.

    Todo el trabajo real vive en `api/feature_mapper.predict_from_user`, que
    delega en `src/data/model_row.py`: construye las 213 características con la
    MISMA ingeniería que el entrenamiento y aplica el scaler a las columnas
    correctas. Aquí solo se traduce el resultado.

    Si faltan los artefactos se lanza RuntimeError: antes había un "modelo de
    respaldo" aritmético con multiplicadores por distrito que devolvía un precio
    inventado con una confianza fija del 75%, lo que ocultaba el problema.

    Returns:
        tuple: (precio_predicho, confianza)
    """
    logger.info(f"🔍 Características recibidas: {features}")

    try:
        salida = predict_from_user(features, model, scaler)
    except ValueError as e:
        logger.error(f"❌ Características inválidas: {e}")
        raise
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"❌ Error en la predicción: {e}")
        raise RuntimeError(f"Error al construir la predicción: {e}")

    precio = salida['precio']
    confianza = salida['confianza']

    if salida['fuera_de_rango']:
        # No es un error: el bosque acota. Pero conviene saberlo.
        logger.warning(
            "⚠️ La vivienda tiene %d valores fuera del rango de entrenamiento: %s",
            len(salida['fuera_de_rango']),
            [a['feature'] for a in salida['fuera_de_rango'][:5]],
        )

    logger.info(
        f"✅ Predicción: ${precio:,.2f} (confianza {confianza:.1%}) | "
        f"barrio={features.get('neighborhood')} "
        f"{features.get('gr_liv_area_m2')}m²"
    )
    return float(precio), float(confianza)


# ============================================
# ENDPOINTS DE PREDICCIÓN
# ============================================

@router.post(
    "/",
    response_model=PredictionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Predecir precio",
    description=(
        "Predice el precio (en USD) de una vivienda del dataset de Ames a partir "
        "de 9 características. El resto de características se completan con la "
        "vivienda mediana del dataset de entrenamiento."
    )
)
def predict(
    features: PredictionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> PredictionResponse:
    """
    Predecir el precio de una vivienda.

    - **Requiere**: Usuario autenticado
    - **Características** (9 campos):
        - neighborhood: Barrio de Ames (ver `GET /api/predictions/options`)
        - ms_subclass: Tipo de vivienda (código MSSubClass)
        - gr_liv_area_m2: Superficie habitable en m²
        - lot_area_m2: Superficie de la parcela en m²
        - overall_qual: Calidad general (1-10)
        - year_built: Año de construcción
        - bedrooms: Dormitorios
        - bathrooms: Baños completos
        - garage_cars: Plazas de garaje
        - latitude / longitude: opcionales, solo informativos
    """
    try:
        # Obtener el diccionario de características
        features_dict = features.model_dump()
        
        # Realizar la predicción
        predicted_price, confidence = predict_price(features_dict)
        
        # Guardar en base de datos
        prediction = CRUDPrediction.create(
            db,
            features,
            current_user.id,
            predicted_price,
            confidence
        )
        
        logger.info(f"✅ Predicción guardada para usuario {current_user.id}: ${predicted_price:,.2f}")
        return prediction
        
    except ValueError as e:
        logger.error(f"❌ Error en predicción: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Error en predicción: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al predecir precio: {str(e)}"
        )


@router.get(
    "/history",
    response_model=PredictionHistoryResponse,
    summary="Historial de predicciones",
    description="Obtiene el historial de predicciones del usuario"
)
def get_prediction_history(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(20, ge=1, le=50, description="Límite de registros"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> PredictionHistoryResponse:
    """
    Obtener historial de predicciones del usuario autenticado.
    
    - **Requiere**: Usuario autenticado
    - **Paginación**: skip, limit
    """
    try:
        predictions = CRUDPrediction.get_by_user(
            db,
            current_user.id,
            skip=skip,
            limit=limit
        )
        total = CRUDPrediction.count_by_user(db, current_user.id)
        
        pages = (total + limit - 1) // limit if limit > 0 else 1
        page = (skip // limit) + 1 if limit > 0 else 1
        
        return PredictionHistoryResponse(
            items=predictions,
            total=total,
            page=page,
            page_size=limit,
            pages=pages
        )
    except Exception as e:
        logger.error(f"Error obteniendo historial: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener historial de predicciones"
        )


@router.get(
    "/options",
    response_model=dict,
    summary="Opciones del formulario",
    description=(
        "Lista de barrios y tipos de vivienda disponibles, con su etiqueta en "
        "español, el precio mediano real del barrio y los rangos válidos de cada "
        "campo. Es un endpoint PÚBLICO: la interfaz lo necesita para pintar el "
        "formulario."
    )
)
def get_form_options() -> dict:
    """
    Opciones para rellenar los desplegables del formulario.

    IMPORTANTE: esta ruta va declarada ANTES de `/{prediction_id}`. Si se
    declarara después, FastAPI intentaría interpretar "options" como un id y
    devolvería un 422.
    """
    try:
        return get_options()
    except Exception as e:
        logger.error(f"Error obteniendo las opciones del formulario: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El contrato de características no está disponible "
                "(models_saved/feature_contract.json)."
            )
        )


@router.get(
    "/{prediction_id}",
    response_model=PredictionResponse,
    summary="Obtener predicción por ID",
    description="Obtiene los detalles de una predicción específica"
)
def get_prediction(
    prediction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> PredictionResponse:
    """
    Obtener predicción por ID.
    
    - **Requiere**: Usuario autenticado
    - **Param**: prediction_id - ID de la predicción
    """
    try:
        prediction = CRUDPrediction.get_by_id(db, prediction_id)
        if not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Predicción con ID {prediction_id} no encontrada"
            )
        
        # Verificar que el usuario sea el propietario o admin
        if prediction.user_id != current_user.id and current_user.role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para ver esta predicción"
            )
        
        return prediction
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo predicción {prediction_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener predicción"
        )


@router.delete(
    "/{prediction_id}",
    response_model=MessageResponse,
    summary="Eliminar predicción",
    description="Elimina una predicción"
)
def delete_prediction(
    prediction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Eliminar predicción por ID.
    
    - **Requiere**: Usuario autenticado (propietario o admin)
    """
    try:
        prediction = CRUDPrediction.get_by_id(db, prediction_id)
        if not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Predicción con ID {prediction_id} no encontrada"
            )
        
        # Verificar permisos
        if prediction.user_id != current_user.id and current_user.role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para eliminar esta predicción"
            )
        
        db.delete(prediction)
        db.commit()
        
        logger.info(f"Predicción {prediction_id} eliminada por usuario {current_user.id}")
        return MessageResponse(
            message="Predicción eliminada correctamente",
            success=True
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando predicción {prediction_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar predicción"
        )


@router.get(
    "/stats/me",
    response_model=PredictionStats,
    summary="Estadísticas personales",
    description="Obtiene estadísticas de predicciones del usuario"
)
def get_my_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> PredictionStats:
    """
    Obtener estadísticas de predicciones del usuario.
    
    - **Requiere**: Usuario autenticado
    """
    try:
        stats = CRUDPrediction.get_stats(db, current_user.id)
        return PredictionStats(**stats)
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


@router.get(
    "/admin/stats",
    response_model=PredictionStats,
    summary="Estadísticas globales (admin)",
    description="Obtiene estadísticas globales de todas las predicciones"
)
def get_global_stats(
    current_user: User = Depends(is_admin),
    db: Session = Depends(get_db)
) -> PredictionStats:
    """
    Obtener estadísticas globales de predicciones.
    
    - **Requiere**: Administrador
    """
    try:
        stats = CRUDPrediction.get_stats(db)
        return PredictionStats(**stats)
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas globales: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )


@router.post(
    "/batch",
    response_model=List[PredictionResponse],
    summary="Predicción múltiple",
    description="Predice precios para múltiples propiedades"
)
def batch_predict(
    features_list: List[PredictionCreate],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> List[PredictionResponse]:
    """
    Realizar predicciones para múltiples propiedades.
    
    - **Requiere**: Usuario autenticado
    - **Body**: Lista de características
    """
    try:
        results = []
        for features in features_list:
            features_dict = features.model_dump()
            predicted_price, confidence = predict_price(features_dict)
            prediction = CRUDPrediction.create(
                db,
                features,
                current_user.id,
                predicted_price,
                confidence
            )
            results.append(prediction)
        
        logger.info(f"✅ Predicción batch: {len(results)} propiedades para usuario {current_user.id}")
        return results
    except Exception as e:
        logger.error(f"Error en batch prediction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en predicción batch: {str(e)}"
        )


@router.get(
    "/info/model",
    response_model=dict,
    summary="Información del modelo",
    description="Obtiene información sobre el modelo de Machine Learning"
)
def get_model_info(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Obtener información del modelo cargado.

    - **Requiere**: Usuario autenticado
    """
    info = {
        "model_loaded": model is not None,
        "model_path": MODEL_PATH,
        "scaler_loaded": scaler is not None,
        "scaler_path": SCALER_PATH,
    }

    if model:
        info["model_type"] = str(type(model))
        if hasattr(model, 'estimators_'):
            info["n_estimators"] = len(model.estimators_)
        if hasattr(model, 'n_features_in_'):
            info["n_features_in"] = model.n_features_in_
        # Versión de scikit-learn con la que se serializó el modelo: si no
        # coincide con la instalada, sklearn avisa y las predicciones pueden
        # no ser válidas (ver B5/A2).
        try:
            import sklearn
            info["sklearn_instalado"] = sklearn.__version__
            info["sklearn_del_modelo"] = getattr(model, '_sklearn_version', 'desconocida')
        except Exception:
            pass

    try:
        info["features"] = get_feature_info()
    except Exception as e:
        info["features_error"] = str(e)

    return info