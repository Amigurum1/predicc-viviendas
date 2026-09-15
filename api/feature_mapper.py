"""
Adaptador entre lo que rellena el usuario y el modelo de Ames Housing.

Este módulo es deliberadamente FINO: no construye el vector ni calcula
características. Traduce los 9 campos del formulario a campos reales del
dataset, y delega en `src/data/model_row.py`, que es la única vía por la que se
construye una fila para el modelo (y que reutiliza la ingeniería de
características de `src/data/preprocess.py`).

HISTORIA (por qué se reescribió)
--------------------------------
La versión anterior intentaba mapear distritos de Lima a columnas como
`Neighborhood_Miraflores` y tipos de propiedad a `MSSubClass_1`. Ninguna de esas
columnas existe en el modelo (sus características son barrios de Ames, Iowa),
así que:
  * `district` y `property_type` se descartaban en silencio, y
  * 12 features derivadas y ~15 columnas inválidas en 0 se enviaban al modelo.
El resultado era un precio sin relación con lo que el usuario pedía.
"""

import logging
import os
from typing import Any, Dict, List

from src.data.feature_contract import load_contract
from src.data.model_row import (
    apply_scaler,
    build_model_row,
    get_scaler_columns,
    predict_from_fields,
    validate_ranges,
)

logger = logging.getLogger(__name__)

# 1 m² = 10.7639 ft² (las unidades del dataset de Ames)
M2_A_FT2 = 10.7639

# Campos del formulario -> campo real del dataset
CAMPOS_DEL_FORMULARIO = [
    'neighborhood', 'ms_subclass', 'gr_liv_area_m2', 'lot_area_m2',
    'overall_qual', 'year_built', 'bedrooms', 'bathrooms', 'garage_cars',
]

# ------------------------------------------------------------------
# CARGA DEL CONTRATO
# ------------------------------------------------------------------

_CONTRATO: Dict[str, Any] = {}
_CONTRATO_ERROR: str = ''


def get_contract() -> Dict[str, Any]:
    """
    Carga (una sola vez) el contrato de características.

    Si falta, se lanza un error explícito: sin contrato la API no puede
    construir una fila válida, y es mejor fallar que inventarse un precio.
    """
    global _CONTRATO, _CONTRATO_ERROR

    if _CONTRATO:
        return _CONTRATO

    try:
        _CONTRATO = load_contract()
        _CONTRATO_ERROR = ''
        logger.info(
            "✅ Contrato cargado: %d características, %d barrios, %d tipos",
            len(_CONTRATO['feature_order']),
            len(_CONTRATO['ui']['neighborhoods']),
            len(_CONTRATO['ui']['ms_subclass']),
        )
    except Exception as e:
        _CONTRATO_ERROR = str(e)
        logger.error(
            "❌ No se pudo cargar models_saved/feature_contract.json: %s\n"
            "   Genéralo con: python src/data/feature_contract.py",
            e,
        )
        raise

    return _CONTRATO


def contract_error() -> str:
    """Error de carga del contrato, si lo hubo (para /health y depuración)."""
    return _CONTRATO_ERROR


# ------------------------------------------------------------------
# TRADUCCIÓN DE CAMPOS
# ------------------------------------------------------------------

def user_fields_to_ames(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Traduce los campos del formulario a campos reales del dataset de Ames.

    Las unidades se convierten a las del dataset (m² -> ft²) y las coherencias
    (garaje, sótano, plantas) las resuelve `build_model_row`.
    """
    contrato = get_contract()
    faltan = [c for c in CAMPOS_DEL_FORMULARIO if features.get(c) is None]
    if faltan:
        raise ValueError(f"Faltan campos obligatorios: {faltan}")

    barrios = {b['valor'] for b in contrato['ui']['neighborhoods']}
    tipos = {int(t['valor']) for t in contrato['ui']['ms_subclass']}

    barrio = str(features['neighborhood'])
    if barrio not in barrios:
        raise ValueError(
            f"Barrio desconocido: {barrio!r}. "
            f"Válidos: {sorted(barrios)}"
        )

    try:
        tipo = int(features['ms_subclass'])
    except (TypeError, ValueError):
        raise ValueError(f"Tipo de vivienda inválido: {features['ms_subclass']!r}")

    if tipo not in tipos:
        raise ValueError(
            f"Tipo de vivienda desconocido: {tipo}. Válidos: {sorted(tipos)}"
        )

    return {
        'Neighborhood': barrio,
        'MSSubClass': tipo,
        'GrLivArea': float(features['gr_liv_area_m2']) * M2_A_FT2,
        'LotArea': float(features['lot_area_m2']) * M2_A_FT2,
        'OverallQual': float(features['overall_qual']),
        'YearBuilt': float(features['year_built']),
        'BedroomAbvGr': float(features['bedrooms']),
        'FullBath': float(features['bathrooms']),
        'GarageCars': float(features['garage_cars']),
    }


# ------------------------------------------------------------------
# COMPATIBILIDAD CON LA API ANTERIOR
# ------------------------------------------------------------------

def validate_features(features: Dict) -> bool:
    """
    Valida los campos del formulario. Devuelve True/False y registra el motivo.

    Se mantiene el nombre porque lo usa `api/routers/predictions.py`.
    """
    try:
        user_fields_to_ames(features)
        return True
    except ValueError as e:
        logger.error("❌ Validación fallida: %s", e)
        return False


def map_features_to_model(features: Dict) -> Any:
    """
    Vector de características del modelo, SIN escalar.

    Se conserva el nombre por compatibilidad, pero el camino de producción es
    `predict_from_user`, que además escala y predice.
    """
    ames = user_fields_to_ames(features)
    return build_model_row(ames, get_contract())['vector']


def get_feature_info() -> Dict:
    """
    Información del modelo para el endpoint descriptivo y para la interfaz:
    opciones de barrio y tipo, y metadatos del dataset de entrenamiento.
    """
    contrato = get_contract()
    return {
        'total_features': len(contrato['feature_order']),
        'dataset': contrato['dataset'],
        'moneda': contrato['moneda'],
        'reference_year': contrato['reference_year'],
        'n_registros_entrenamiento': contrato['n_registros_entrenamiento'],
        'precio_mediano': contrato['precio_mediano'],
        'precio_min': contrato['precio_min'],
        'precio_max': contrato['precio_max'],
        'campos_del_formulario': CAMPOS_DEL_FORMULARIO,
        'neighborhoods': contrato['ui']['neighborhoods'],
        'ms_subclass': contrato['ui']['ms_subclass'],
    }


def get_options() -> Dict:
    """
    Opciones para rellenar los desplegables del formulario, con etiquetas en
    español y precios de referencia reales por barrio.

    Todos los rangos se derivan del contrato (unidades crudas del dataset), no
    de constantes escritas a mano: si algún día se reentrena con otro dataset,
    la interfaz se ajusta sola.
    """
    contrato = get_contract()

    # Precio mediano real de venta por barrio: contexto honesto en la interfaz.
    medianas = contrato.get('neighborhood_median_price', {})
    crudos = contrato.get('raw_ranges', {})

    def rango(campo: str, campo_min: str = 'min', campo_max: str = 'max'):
        """Rango del contrato en unidades crudas; None si falta."""
        info = crudos.get(campo)
        if not info:
            return None
        return [info[campo_min], info[campo_max]]

    def rango_m2(campo: str):
        """Rango del contrato convertido de ft² a m², redondeado."""
        info = crudos.get(campo)
        if not info:
            return None
        return [int(round(info['min'] / M2_A_FT2)), int(round(info['max'] / M2_A_FT2))]

    return {
        'neighborhoods': [
            {
                'valor': b['valor'],
                'etiqueta': b['etiqueta'],
                'precio_mediano': medianas.get(b['valor']),
            }
            for b in contrato['ui']['neighborhoods']
        ],
        'ms_subclass': contrato['ui']['ms_subclass'],
        'moneda': contrato['moneda'],
        'dataset': contrato['dataset'],
        'precio_mediano': contrato['precio_mediano'],
        'rangos': {
            'gr_liv_area_m2': rango_m2('GrLivArea'),
            'lot_area_m2': rango_m2('LotArea'),
            'overall_qual': rango('OverallQual'),
            'year_built': [
                crudos.get('YearBuilt', {}).get('min'),
                contrato['reference_year'],
            ],
            'bedrooms': rango('BedroomAbvGr'),
            'bathrooms': rango('FullBath'),
            'garage_cars': rango('GarageCars'),
        },
        'valores_asumidos': (
            'El resto de características de la vivienda (calidades, sótano, '
            'porches, reformas...) se completan con la vivienda mediana del '
            'dataset de Ames.'
        ),
    }


# ------------------------------------------------------------------
# PREDICCIÓN
# ------------------------------------------------------------------

def predict_from_user(features: Dict[str, Any], model, scaler) -> Dict[str, Any]:
    """
    Camino completo: campos del formulario -> precio + confianza.

    Lanza RuntimeError si faltan los artefactos, en vez de devolver un precio
    inventado con una confianza ficticia.
    """
    if model is None:
        raise RuntimeError(
            "El modelo no está cargado (models_saved/RandomForest_Tuned.pkl). "
            "No se devuelve un precio aproximado para no dar un resultado falso."
        )
    if scaler is None:
        raise RuntimeError(
            "El scaler no está cargado (models_saved/scaler.pkl). Sin él las "
            "predicciones estarían en la escala equivocada."
        )

    ames = user_fields_to_ames(features)
    contrato = get_contract()
    salida = predict_from_fields(ames, contrato, model, scaler)

    if salida['fuera_de_rango']:
        logger.warning(
            "⚠️ %d valores fuera del rango de entrenamiento: %s",
            len(salida['fuera_de_rango']),
            [a['feature'] for a in salida['fuera_de_rango'][:5]],
        )

    return salida
