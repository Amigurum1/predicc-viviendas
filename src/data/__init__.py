# src/data/__init__.py
"""
Módulo de datos para Ames Housing
"""

# ✅ Importar funciones de la NUEVA versión de preprocess.py
from .preprocess import (
    process_data,
    drop_unused_columns,
    handle_missing_values,
    convert_ordinal_features,
    create_temporal_features,
    create_interaction_features,
    create_polynomial_features,
    handle_outliers,
    encode_categorical_features,
    scale_features,
    get_feature_names
)

# ✅ También importar del make_dataset (para compatibilidad)
from .make_dataset import load_data, save_processed_data

__all__ = [
    # De preprocess
    'process_data',
    'drop_unused_columns',
    'handle_missing_values',
    'convert_ordinal_features',
    'create_temporal_features',
    'create_interaction_features',
    'create_polynomial_features',
    'handle_outliers',
    'encode_categorical_features',
    'scale_features',
    'get_feature_names',
    # De make_dataset
    'load_data',
    'save_processed_data'
]