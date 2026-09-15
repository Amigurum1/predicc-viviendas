# src/data/preprocess.py
"""
Módulo de preprocesamiento para Ames Housing Dataset
Versión: 2.0 - Diseñado para 81 columnas
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
import logging
from typing import Tuple, List, Dict, Optional

# Configurar logging
# NOTA: no se llama a logging.basicConfig() a nivel de módulo a propósito.
# Este módulo lo importa la API (api/feature_mapper.py) y basicConfig() aquí
# instalaría un handler raíz que anularía la configuración de uvicorn/main.py.
logger = logging.getLogger(__name__)


# ============================================================
# 1. CLASIFICACIÓN DE COLUMNAS
# ============================================================

COLUMN_GROUPS = {
    'numeric_continuous': [
        'LotArea', 'GrLivArea', 'TotalBsmtSF', '1stFlrSF', '2ndFlrSF',
        'GarageArea', 'WoodDeckSF', 'OpenPorchSF', 'EnclosedPorch',
        'ScreenPorch', 'PoolArea'
    ],
    'temporal': [
        'YearBuilt', 'YearRemodAdd', 'GarageYrBlt', 'YrSold'
    ],
    'ordinal': [
        'OverallQual', 'OverallCond', 'ExterQual', 'ExterCond',
        'BsmtQual', 'BsmtCond', 'BsmtFinType1', 'HeatingQC',
        'KitchenQual', 'FireplaceQu', 'GarageQual', 'GarageCond',
        'PoolQC'
    ],
    'categorical': [
        'MSZoning', 'Street', 'Alley', 'LotShape', 'LandContour',
        'Utilities', 'LotConfig', 'LandSlope', 'Neighborhood',
        'Condition1', 'Condition2', 'BldgType', 'HouseStyle',
        'RoofStyle', 'RoofMatl', 'Exterior1st', 'Exterior2nd',
        'MasVnrType', 'Foundation', 'Heating', 'CentralAir',
        'Electrical', 'Functional', 'GarageType', 'GarageFinish',
        'PavedDrive', 'SaleType', 'SaleCondition'
    ],
    'count': [
        'BedroomAbvGr', 'KitchenAbvGr', 'FullBath', 'HalfBath',
        'BsmtFullBath', 'BsmtHalfBath', 'Fireplaces', 'GarageCars'
    ],
    'drop': [
        'Id', 'PoolQC', 'MiscFeature', 'Alley', 'Fence'
    ]
}

# Mapeo de ordinales a valores numéricos
ORDINAL_MAPPING = {
    'ExterQual': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'ExterCond': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'BsmtQual': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'BsmtCond': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'HeatingQC': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'KitchenQual': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'FireplaceQu': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'GarageQual': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'GarageCond': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'PoolQC': {'Po': 1, 'Fa': 2, 'TA': 3, 'Gd': 4, 'Ex': 5},
    'BsmtFinType1': {'Unf': 1, 'LwQ': 2, 'Rec': 3, 'BLQ': 4, 'ALQ': 5, 'GLQ': 6},
    'BsmtFinType2': {'Unf': 1, 'LwQ': 2, 'Rec': 3, 'BLQ': 4, 'ALQ': 5, 'GLQ': 6},
    'BsmtExposure': {'No': 0, 'Mn': 1, 'Av': 2, 'Gd': 3},
}


# Columnas derivadas que también se escalan (no son binarias).
# Se define aquí para que el ajuste y la transformación no puedan divergir.
SCALED_EXTRA_COLUMNS = [
    'TotalSF', 'LivArea_Qual', 'Bsmt_Qual', 'Qual_Cond',
    'Age_Qual', 'HouseAge', 'YearsSinceRemodel', 'GarageAge',
    'GrLivArea_sq', 'OverallQual_sq', 'TotalBsmtSF_sq', 'HouseAge_sq',
]


# ============================================================
# 2. FUNCIONES DE LIMPIEZA
# ============================================================

def drop_unused_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Elimina columnas que no aportan valor
    """
    cols_to_drop = [col for col in COLUMN_GROUPS['drop'] if col in df.columns]
    if cols_to_drop:
        logger.info(f"🗑️ Eliminando columnas: {cols_to_drop}")
        df = df.drop(columns=cols_to_drop)
    return df


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maneja valores nulos según el tipo de columna
    """
    logger.info("🔍 Manejando valores nulos...")
    df_clean = df.copy()
    
    # 1. Columnas numéricas continuas → mediana
    for col in COLUMN_GROUPS['numeric_continuous']:
        if col in df_clean.columns and df_clean[col].isnull().any():
            median_val = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(median_val)
            logger.info(f"  - {col}: rellenados con mediana ({median_val:.0f})")
    
    # 2. Columnas temporales → mediana
    for col in COLUMN_GROUPS['temporal']:
        if col in df_clean.columns and df_clean[col].isnull().any():
            median_val = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(median_val)
            logger.info(f"  - {col}: rellenados con mediana ({median_val:.0f})")
    
    # 3. Columnas ordinales → moda
    for col in COLUMN_GROUPS['ordinal']:
        if col in df_clean.columns and df_clean[col].isnull().any():
            mode_val = df_clean[col].mode()[0]
            df_clean[col] = df_clean[col].fillna(mode_val)
            logger.info(f"  - {col}: rellenados con moda ({mode_val})")
    
    # 4. Columnas categóricas → moda
    for col in COLUMN_GROUPS['categorical']:
        if col in df_clean.columns and df_clean[col].isnull().any():
            mode_val = df_clean[col].mode()[0]
            df_clean[col] = df_clean[col].fillna(mode_val)
            logger.info(f"  - {col}: rellenados con moda ({mode_val})")
    
    # 5. Columnas de recuento → 0
    for col in COLUMN_GROUPS['count']:
        if col in df_clean.columns and df_clean[col].isnull().any():
            df_clean[col] = df_clean[col].fillna(0)
            logger.info(f"  - {col}: rellenados con 0")
    
    # 6. Columnas específicas (NUEVO)
    # LotFrontage → mediana global
    if 'LotFrontage' in df_clean.columns and df_clean['LotFrontage'].isnull().any():
        median_val = df_clean['LotFrontage'].median()
        df_clean['LotFrontage'] = df_clean['LotFrontage'].fillna(median_val)
        logger.info(f"  - LotFrontage: rellenados con mediana global ({median_val:.0f})")
    
    # MasVnrArea → 0 (sin revestimiento)
    if 'MasVnrArea' in df_clean.columns and df_clean['MasVnrArea'].isnull().any():
        df_clean['MasVnrArea'] = df_clean['MasVnrArea'].fillna(0)
        logger.info("  - MasVnrArea: rellenados con 0")
    
    # BsmtExposure → 'No' (sin exposición)
    if 'BsmtExposure' in df_clean.columns and df_clean['BsmtExposure'].isnull().any():
        df_clean['BsmtExposure'] = df_clean['BsmtExposure'].fillna('No')
        logger.info("  - BsmtExposure: rellenados con 'No'")
    
    # BsmtFinType2 → 'Unf' (sin terminar)
    if 'BsmtFinType2' in df_clean.columns and df_clean['BsmtFinType2'].isnull().any():
        df_clean['BsmtFinType2'] = df_clean['BsmtFinType2'].fillna('Unf')
        logger.info("  - BsmtFinType2: rellenados con 'Unf'")
    
    # 7. Columnas de garaje (si no hay garaje → valores por defecto)
    if 'GarageFinish' in df_clean.columns and df_clean['GarageFinish'].isnull().any():
        df_clean['GarageFinish'] = df_clean['GarageFinish'].fillna('Unf')
        logger.info("  - GarageFinish: rellenados con 'Unf'")
    
    if 'GarageQual' in df_clean.columns and df_clean['GarageQual'].isnull().any():
        df_clean['GarageQual'] = df_clean['GarageQual'].fillna('TA')
        logger.info("  - GarageQual: rellenados con 'TA'")
    
    if 'GarageCond' in df_clean.columns and df_clean['GarageCond'].isnull().any():
        df_clean['GarageCond'] = df_clean['GarageCond'].fillna('TA')
        logger.info("  - GarageCond: rellenados con 'TA'")
    
    logger.info("✅ Valores nulos manejados")
    return df_clean


def convert_ordinal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte columnas ordinales a valores numéricos
    """
    logger.info("🔄 Convirtiendo ordinales a números...")
    df_clean = df.copy()
    
    for col, mapping in ORDINAL_MAPPING.items():
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].map(mapping)
            # Si algún valor no está en el mapeo, lo dejamos como NaN
            # (pero ya deberían estar manejados)
            logger.info(f"  - {col}: convertido a numérico")
    
    return df_clean


def create_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea features temporales a partir de los años
    """
    logger.info("📅 Creando features temporales...")
    df_clean = df.copy()
    
    # Edad de la casa
    if 'YearBuilt' in df_clean.columns and 'YrSold' in df_clean.columns:
        df_clean['HouseAge'] = df_clean['YrSold'] - df_clean['YearBuilt']
        logger.info("  - HouseAge: creada")
    
    # Años desde remodelación
    if 'YearRemodAdd' in df_clean.columns and 'YrSold' in df_clean.columns:
        df_clean['YearsSinceRemodel'] = df_clean['YrSold'] - df_clean['YearRemodAdd']
        logger.info("  - YearsSinceRemodel: creada")
    
    # Edad del garaje
    if 'GarageYrBlt' in df_clean.columns and 'YrSold' in df_clean.columns:
        df_clean['GarageAge'] = df_clean['YrSold'] - df_clean['GarageYrBlt']
        # Si no hay garaje, GarageYrBlt es 0, la edad es 0
        df_clean['GarageAge'] = df_clean['GarageAge'].clip(lower=0)
        logger.info("  - GarageAge: creada")
    
    # Casa remodelada (booleano)
    if 'YearBuilt' in df_clean.columns and 'YearRemodAdd' in df_clean.columns:
        df_clean['IsRemodeled'] = (df_clean['YearRemodAdd'] != df_clean['YearBuilt']).astype(int)
        logger.info("  - IsRemodeled: creada")
    
    return df_clean


def create_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea features de interacción con sentido económico para Ames
    """
    logger.info("🔗 Creando features de interacción...")
    df_clean = df.copy()
    
    # 1. Área × Calidad (lo más importante en bienes raíces)
    if 'GrLivArea' in df_clean.columns and 'OverallQual' in df_clean.columns:
        df_clean['LivArea_Qual'] = df_clean['GrLivArea'] * df_clean['OverallQual']
        logger.info("  - LivArea_Qual: GrLivArea × OverallQual")
    
    # 2. Sótano × Calidad
    if 'TotalBsmtSF' in df_clean.columns and 'OverallQual' in df_clean.columns:
        df_clean['Bsmt_Qual'] = df_clean['TotalBsmtSF'] * df_clean['OverallQual']
        logger.info("  - Bsmt_Qual: TotalBsmtSF × OverallQual")
    
    # 3. Área total (incluyendo sótano)
    if 'GrLivArea' in df_clean.columns and 'TotalBsmtSF' in df_clean.columns:
        df_clean['TotalSF'] = df_clean['GrLivArea'] + df_clean['TotalBsmtSF']
        logger.info("  - TotalSF: GrLivArea + TotalBsmtSF")
    
    # 4. Calidad × Condición
    if 'OverallQual' in df_clean.columns and 'OverallCond' in df_clean.columns:
        df_clean['Qual_Cond'] = df_clean['OverallQual'] * df_clean['OverallCond']
        logger.info("  - Qual_Cond: OverallQual × OverallCond")
    
    # 5. Edad × Calidad (casas viejas pero bien mantenidas)
    if 'HouseAge' in df_clean.columns and 'OverallQual' in df_clean.columns:
        df_clean['Age_Qual'] = df_clean['HouseAge'] * df_clean['OverallQual']
        logger.info("  - Age_Qual: HouseAge × OverallQual")
    
    # 6. Porche total
    porch_cols = ['OpenPorchSF', 'EnclosedPorch', 'ScreenPorch']
    existing_porch = [col for col in porch_cols if col in df_clean.columns]
    if len(existing_porch) > 1:
        df_clean['TotalPorchSF'] = df_clean[existing_porch].sum(axis=1)
        logger.info(f"  - TotalPorchSF: {existing_porch}")
    
    return df_clean


def create_polynomial_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea features polinómicas (cuadrados) para variables clave
    """
    logger.info("📐 Creando features polinómicas...")
    df_clean = df.copy()
    
    poly_features = ['GrLivArea', 'OverallQual', 'TotalBsmtSF', 'HouseAge']
    
    for feat in poly_features:
        if feat in df_clean.columns:
            df_clean[f'{feat}_sq'] = df_clean[feat] ** 2
            logger.info(f"  - {feat}_sq: creada")
    
    return df_clean


def handle_outliers(df: pd.DataFrame, method: str = 'iqr', threshold: float = 2.0) -> pd.DataFrame:
    """
    Detecta y elimina outliers en variables numéricas continuas
    """
def compute_outlier_limits(df: pd.DataFrame, method: str = 'iqr',
                           threshold: float = 2.0) -> Dict[str, Dict[str, float]]:
    """
    Calcula los umbrales de outlier por columna usando SOLO el DataFrame recibido.

    Está separado de `apply_outlier_limits` a propósito: los umbrales deben
    calcularse con el conjunto de ENTRENAMIENTO y aplicarse después al de test.
    Calcularlos con todos los datos sería una fuga de información (el modelo
    "sabría" de antemano dónde están los extremos del test).
    """
    logger.info(f"📊 Calculando umbrales de outliers (método: {method}, threshold: {threshold})...")

    # Columnas que NO deben ser evaluadas para outliers (por tener muchos ceros)
    exclude_from_outliers = [
        'PoolArea',           # 99% son 0
        'EnclosedPorch',      # Muchos ceros
        'ScreenPorch',        # Muchos ceros
        'OpenPorchSF',        # Muchos ceros
        'WoodDeckSF',         # Muchos ceros
        'GarageArea',         # 0 significa "no hay garaje"
        'BsmtFinSF1',         # 0 significa "no hay sótano terminado"
        'BsmtFinSF2',
        'BsmtUnfSF',
        'TotalBsmtSF',        # 0 significa "no hay sótano"
        'LowQualFinSF',       # Área de baja calidad (muchos ceros)
        'MiscVal'             # Valor de misceláneos (muchos ceros)
    ]

    limites: Dict[str, Dict[str, float]] = {}

    for col in COLUMN_GROUPS['numeric_continuous']:
        if col not in df.columns:
            continue

        # Saltar columnas excluidas
        if col in exclude_from_outliers:
            logger.info(f"  - {col}: excluida de análisis de outliers")
            continue

        # No aplicar a variables con muy pocos valores únicos
        if df[col].nunique() < 10:
            continue

        if method == 'iqr':
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            limites[col] = {
                'lower': float(Q1 - threshold * IQR),
                'upper': float(Q3 + threshold * IQR),
            }
        elif method == 'zscore':
            media = df[col].mean()
            std = df[col].std()
            limites[col] = {
                'lower': float(media - threshold * std),
                'upper': float(media + threshold * std),
            }
        else:
            raise ValueError(f"Método {method} no soportado")

    return limites


def outlier_mask(df: pd.DataFrame,
                 limites: Dict[str, Dict[str, float]]) -> pd.Series:
    """
    Máscara booleana de las filas que superan los umbrales indicados.

    Se expone aparte para poder aplicar EXACTAMENTE la misma máscara a las
    características y al objetivo (si no, se desalinean las etiquetas).
    """
    mascara = pd.Series(False, index=df.index)
    for col, lim in limites.items():
        if col not in df.columns:
            continue
        outliers = (df[col] < lim['lower']) | (df[col] > lim['upper'])
        if outliers.sum() > 0:
            logger.info(f"  - {col}: {outliers.sum()} outliers detectados")
        mascara = mascara | outliers
    return mascara


def apply_outlier_limits(df: pd.DataFrame,
                         limites: Dict[str, Dict[str, float]],
                         reset_index: bool = True) -> pd.DataFrame:
    """
    Elimina las filas que superan los umbrales indicados.

    Los umbrales deben venir del conjunto de entrenamiento.
    """
    if not limites:
        return df.reset_index(drop=True) if reset_index else df

    mascara = outlier_mask(df, limites)
    limpio = df[~mascara]
    logger.info(f"✅ Eliminados {int(mascara.sum())} outliers - {len(limpio)} registros restantes")
    return limpio.reset_index(drop=True) if reset_index else limpio


def handle_outliers(df: pd.DataFrame, method: str = 'iqr',
                    threshold: float = 2.0) -> pd.DataFrame:
    """
    Calcula y aplica los umbrales sobre el MISMO conjunto.

    Se mantiene por comodidad, pero el pipeline usa `compute_outlier_limits` +
    `apply_outlier_limits` para no calcular los umbrales con el conjunto de test.
    """
    return apply_outlier_limits(df, compute_outlier_limits(df, method, threshold))


def encode_categorical_features(df: pd.DataFrame,
                                columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    One-Hot Encoding de las variables categóricas.

    Dos modos:

    * `columns=None` (AJUSTE): genera los dummies del conjunto de entrenamiento.
      Con `drop_first=True` se elimina una categoría por columna, y esa categoría
      pasa a representarse con todos los dummies a 0.
    * `columns=[...]` (TRANSFORMACIÓN): codifica otro conjunto y lo alinea con
      las columnas del entrenamiento. Las categorías no vistas en entrenamiento
      quedan a 0 (equivalentes a la categoría base), en vez de crear columnas
      nuevas que el modelo no conoce.
    """
    categorias = [c for c in COLUMN_GROUPS['categorical'] if c in df.columns]

    if columns is None:
        logger.info("🏷️ Aplicando One-Hot Encoding (ajuste sobre entrenamiento)...")
        codificado = pd.get_dummies(df, columns=categorias, drop_first=True)
        logger.info(f"  - {len(categorias)} columnas codificadas")
        logger.info(f"  - Nuevas columnas: {codificado.shape[1]}")
        return codificado

    logger.info("🏷️ Aplicando One-Hot Encoding (alineado con entrenamiento)...")
    codificado = pd.get_dummies(df, columns=categorias, drop_first=False)

    for col in columns:
        if col in codificado.columns:
            continue
        if col in df.columns:
            # Es una columna original que falta: el DataFrame no es el esperado.
            raise ValueError(f"Falta la columna '{col}' al codificar el conjunto de test")
        # Dummy de una categoría que no existía en entrenamiento: se queda a 0.
        codificado[col] = 0

    return codificado[columns]


def scale_features(df: pd.DataFrame, scaler: Optional[StandardScaler] = None) -> Tuple[pd.DataFrame, StandardScaler]:
    """
    Escala las features numéricas continuas.

    Dos modos:

    * `scaler=None` (AJUSTE): decide qué columnas escalar (numéricas continuas
      con más de dos valores distintos) y ajusta el escalador con ellas.
    * `scaler=<ajustado>` (TRANSFORMACIÓN): usa EXACTAMENTE las columnas con las
      que se ajustó. Es importante no recalcularlas: sobre un conjunto pequeño
      (o una sola fila) `nunique() > 2` daría otra lista y el escalado sería
      incorrecto. El propio escalador guarda sus columnas en `feature_names_in_`.
    """
    df_scaled = df.copy()

    if scaler is None:
        logger.info("📏 Ajustando el escalado de features numéricas...")
        cols_to_scale = [c for c in COLUMN_GROUPS['numeric_continuous'] if c in df_scaled.columns]
        cols_to_scale.extend([c for c in SCALED_EXTRA_COLUMNS if c in df_scaled.columns])
        # No escalar variables binarias (0/1)
        cols_to_scale = [c for c in cols_to_scale if df_scaled[c].nunique() > 2]

        logger.info(f"  - Escalando {len(cols_to_scale)} columnas")
        scaler = StandardScaler()
        df_scaled[cols_to_scale] = scaler.fit_transform(df_scaled[cols_to_scale])
        logger.info("✅ Escalado ajustado")
        return df_scaled, scaler

    # Ojo: feature_names_in_ es un np.ndarray, así que `nombres or []` lanzaría
    # "The truth value of an array with more than one element is ambiguous".
    nombres_attr = getattr(scaler, 'feature_names_in_', None)
    nombres = [str(c) for c in nombres_attr] if nombres_attr is not None else []
    if not nombres:
        raise ValueError(
            "El scaler no expone 'feature_names_in_': no se puede saber qué columnas escalar"
        )
    faltan = [c for c in nombres if c not in df_scaled.columns]
    if faltan:
        raise ValueError(f"Faltan columnas que el scaler espera escalar: {faltan[:5]}")

    logger.info(f"📏 Aplicando el escalado a {len(nombres)} columnas")
    df_scaled[nombres] = scaler.transform(df_scaled[nombres])
    logger.info("✅ Escalado aplicado")
    return df_scaled, scaler
    
    logger.info(f"  - Escalando {len(cols_to_scale)} columnas")
    
    if scaler is None:
        scaler = StandardScaler()
        df_scaled[cols_to_scale] = scaler.fit_transform(df_scaled[cols_to_scale])
    else:
        df_scaled[cols_to_scale] = scaler.transform(df_scaled[cols_to_scale])
    logger.info("✅ Escalado completado")
    return df_scaled, scaler


def get_feature_names() -> List[str]:
    """
    Retorna los nombres de todas las features posibles
    Útil para la API
    """
    all_features = (
        COLUMN_GROUPS['numeric_continuous'] +
        COLUMN_GROUPS['count'] +
        ['HouseAge', 'YearsSinceRemodel', 'GarageAge', 'IsRemodeled',
         'TotalSF', 'LivArea_Qual', 'Bsmt_Qual', 'Qual_Cond', 'Age_Qual', 'TotalPorchSF',
         'GrLivArea_sq', 'OverallQual_sq', 'TotalBsmtSF_sq', 'HouseAge_sq']
    )
    return all_features


# ============================================================
# 3. FUNCIÓN PRINCIPAL - PIPELINE COMPLETO
# ============================================================

def split_and_clean(
    df: pd.DataFrame,
    target_col: str = 'SalePrice',
    handle_outliers_flag: bool = True,
    outlier_threshold: float = 2.0,
    test_size: float = 0.2,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Limpieza, ingeniería de características y separación train/test.

    Devuelve `(X_train, X_test, y_train, y_test)` SIN codificar ni escalar.

    EL ORDEN IMPORTA. Antes se hacía todo con el conjunto completo y se dividía
    AL FINAL, lo que producía fuga de datos:

      * el `StandardScaler` se ajustaba con train + test, así que las métricas de
        test salían optimistas;
      * los umbrales de outliers se calculaban con train + test;
      * las categorías del One-Hot Encoding se decidían viendo también el test.

    Ahora se divide PRIMERO y todo lo que "aprende" parámetros (outliers,
    categorías, escalado) se ajusta solo con train.

    Los outliers se eliminan únicamente del conjunto de entrenamiento, a
    propósito: el test debe representar la distribución real que verá el modelo
    en producción, extremos incluidos.
    """
    logger.info("🧹 Limpieza e ingeniería de características...")
    df = drop_unused_columns(df)
    df = handle_missing_values(df)
    df = convert_ordinal_features(df)
    df = create_temporal_features(df)
    df = create_interaction_features(df)
    df = create_polynomial_features(df)

    X = df.drop(columns=[target_col])
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )
    logger.info(f"✂️  División train/test: {len(X_train)} / {len(X_test)}")

    if handle_outliers_flag:
        # Los umbrales se calculan SOLO con train y se aplican SOLO a train.
        # La misma máscara se aplica a X y a y para que no se desalineen.
        limites = compute_outlier_limits(X_train, method='iqr', threshold=outlier_threshold)
        mascara = outlier_mask(X_train, limites)
        logger.info(f"✅ Eliminados {int(mascara.sum())} outliers de entrenamiento "
                    f"({len(X_train) - int(mascara.sum())} filas restantes)")
        X_train = X_train[~mascara].reset_index(drop=True)
        y_train = y_train[~mascara].reset_index(drop=True)

    return X_train, X_test, y_train, y_test


def process_data(
    df: pd.DataFrame,
    target_col: str = 'SalePrice',
    handle_outliers_flag: bool = True,
    outlier_threshold: float = 2.0,
    encode_categorical: bool = True,
    scale: bool = True,
    test_size: float = 0.2,
    random_state: int = 42
) -> Dict:
    """
    Pipeline completo de preprocesamiento para Ames Housing.

    Orden: limpieza -> ingeniería -> división train/test -> outliers (train) ->
    One-Hot (ajustado en train) -> escalado (ajustado en train).

    Args:
        df: DataFrame raw
        target_col: Nombre de la columna objetivo
        handle_outliers_flag: Si eliminar outliers del conjunto de entrenamiento
        encode_categorical: Si aplicar One-Hot Encoding
        scale: Si escalar features
        test_size: Proporción para test
        random_state: Semilla para reproducibilidad

    Returns:
        Diccionario con X_train, X_test, y_train, y_test, scaler
    """
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO PIPELINE DE PREPROCESAMIENTO")
    logger.info("=" * 60)

    # 1-7. Limpieza, ingeniería y división (sin fuga de datos)
    X_train, X_test, y_train, y_test = split_and_clean(
        df,
        target_col=target_col,
        handle_outliers_flag=handle_outliers_flag,
        outlier_threshold=outlier_threshold,
        test_size=test_size,
        random_state=random_state,
    )

    # 8. Codificar categóricas: las categorías se deciden con train y el test se
    #    alinea a esas columnas.
    if encode_categorical:
        X_train = encode_categorical_features(X_train)
        X_test = encode_categorical_features(X_test, columns=X_train.columns.tolist())

    # 9. Escalar: el escalador se ajusta SOLO con train.
    if scale:
        X_train, scaler = scale_features(X_train)
        X_test, _ = scale_features(X_test, scaler=scaler)
    else:
        scaler = None

    # 10. Resumen final
    total = len(X_train) + len(X_test)
    logger.info("\n" + "=" * 60)
    logger.info("📊 RESUMEN FINAL:")
    logger.info(f"  - Registros totales: {total}")
    logger.info(f"  - Train: {len(X_train)} ({len(X_train)/total*100:.1f}%)")
    logger.info(f"  - Test: {len(X_test)} ({len(X_test)/total*100:.1f}%)")
    logger.info(f"  - Features: {X_train.shape[1]}")
    logger.info(f"  - Target medio (train): ${y_train.mean():,.2f}")
    logger.info(f"  - Target medio (test):  ${y_test.mean():,.2f}")
    logger.info("=" * 60)
    logger.info("✅ PIPELINE COMPLETADO!")

    return {
        'X_train': X_train,
        'X_test': X_test,
        'y_train': y_train,
        'y_test': y_test,
        'scaler': scaler,
        'feature_names': X_train.columns.tolist()
    }