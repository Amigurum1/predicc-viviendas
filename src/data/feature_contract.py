# src/data/feature_contract.py
"""
Contrato de características del modelo de Ames Housing.

PROBLEMA QUE RESUELVE
---------------------
La API construía a mano un vector de 213 columnas. Eso provocaba un
"train/serve skew" sistemático:

  * 12 de las 23 columnas que el scaler espera son features DERIVADAS
    (TotalSF, LivArea_Qual, HouseAge, GrLivArea_sq...) y se enviaban a 0
    en lugar de calcularse.
  * Otras ~15 columnas son inválidas en 0: MSSubClass (20-190), LotFrontage
    (21-313), YrSold (2006-2010), las ordinales de calidad (1-5)...
  * Con YrSold=0, la edad salía NEGATIVA (HouseAge = 0 - YearBuilt), lo que
    envenenaba Age_Qual y HouseAge_sq.

SOLUCIÓN
--------
1. Este módulo deriva del dataset de entrenamiento una "fila de referencia"
   (la vivienda mediana real) y todas las tablas de apoyo.
2. `build_model_row()` parte de esa fila de referencia, sobrescribe solo los
   campos que el usuario especifica y ejecuta EXACTAMENTE las mismas funciones
   de ingeniería de `src/data/preprocess.py`.

Resultado: cualquier valor enviado al modelo está dentro de la distribución de
entrenamiento por construcción, y la ingeniería de características es idéntica
en entrenamiento y en inferencia (una sola fuente de verdad).

Uso:
    python src/data/feature_contract.py        # regenera el contrato
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd

# Raíz del proyecto al path para poder importar src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.preprocess import (  # noqa: E402
    COLUMN_GROUPS,
    drop_unused_columns,
    handle_missing_values,
    convert_ordinal_features,
    create_temporal_features,
    create_interaction_features,
    create_polynomial_features,
    handle_outliers,
    split_and_clean,
)

logger = logging.getLogger(__name__)

RAW_TRAIN = PROJECT_ROOT / 'data' / 'raw' / 'train.csv'
PROCESSED_X = PROJECT_ROOT / 'data' / 'processed' / 'X_train.csv'
FEATURE_NAMES = PROJECT_ROOT / 'models_saved' / 'feature_names.txt'
CONTRACT_PATH = PROJECT_ROOT / 'models_saved' / 'feature_contract.json'

# Columnas numéricas que en realidad son códigos nominales: se resume con la
# moda y no con la mediana (ver build_reference_row).
MODE_COLUMNS = {'MSSubClass'}


# ============================================================
# ETIQUETAS EN ESPAÑOL (nombre real del dataset + descripción)
# ============================================================

# Los 25 barrios de Ames. La descripción es orientativa y se muestra en la
# interfaz; el valor que recibe el modelo es siempre el código real.
NEIGHBORHOOD_LABELS: Dict[str, str] = {
    'Blmngtn':  'Bloomington Heights (norte, promoción reciente)',
    'Blueste':  'Bluestem (norte, promoción pequeña)',
    'BrDale':   'Briardale (norte, adosados años 70)',
    'BrkSide':  'Brookside (oeste, casas antiguas junto al arroyo)',
    'ClearCr':  'Clear Creek (sur, zona residencial valorada)',
    'CollgCr':  'College Creek (oeste, junto al campus)',
    'Crawfor':  'Crawford (oeste, barrio consolidado)',
    'Edwards':  'Edwards (oeste, el más económico y numeroso)',
    'Gilbert':  'Gilbert (norte, urbanización de los 90)',
    'IDOTRR':   'Iowa DOT and Rail Road (céntrico, junto al ferrocarril)',
    'MeadowV':  'Meadow Village (norte, el más barato del dataset)',
    'Mitchel':  'Mitchell (norte, vivienda unifamiliar estándar)',
    'NAmes':    'North Ames (norte, el más numeroso del dataset)',
    'NPkVill':  'Northpark Villa (norte, adosados)',
    'NWAmes':   'Northwest Ames (noroeste, residencial tranquilo)',
    'NoRidge':  'Northridge (norte, casas grandes de gama alta)',
    'NridgHt':  'Northridge Heights (norte, la zona más cara)',
    'OldTown':  'Old Town (centro histórico, casas antiguas)',
    'SWISU':    'South & West of ISU (sur del campus universitario)',
    'Sawyer':   'Sawyer (oeste, junto a la vía del tren)',
    'SawyerW':  'Sawyer West (oeste, mejor valorado que Sawyer)',
    'Somerst':  'Somerset (norte, familiar de gama media-alta)',
    'StoneBr':  'Stone Brook (norte, gama alta)',
    'Timber':   'Timberland (suroeste, gama alta junto al bosque)',
    'Veenker':  'Veenker (norte, junto al campo de golf)',
}

# Códigos MSSubClass: qué tipo de vivienda es cada uno (definición original).
MS_SUBCLASS_LABELS: Dict[int, str] = {
    20:  'Una planta, construida en 1946 o después',
    30:  'Una planta, construida antes de 1946',
    40:  'Una planta con buhardilla habitable',
    45:  'Planta y media, buhardilla sin terminar',
    50:  'Planta y media, buhardilla terminada',
    60:  'Dos plantas, construida en 1946 o después',
    70:  'Dos plantas, construida antes de 1946',
    75:  'Dos plantas y media',
    80:  'Niveles partidos o multinivel',
    85:  'Split foyer (entrada a media altura)',
    90:  'Dúplex',
    120: 'Una planta en urbanización planificada (PUD), 1946+',
    160: 'Dos plantas en urbanización planificada (PUD), 1946+',
    180: 'Multinivel en urbanización planificada (PUD)',
    190: 'Vivienda convertida en dos familias',
}


# ============================================================
# 1. CONSTRUCCIÓN DE LA FILA DE REFERENCIA
# ============================================================

def _clean_partial(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pasos 1-3 del pipeline (drop, nulos, ordinales) SIN escalar, codificar ni
    dividir.
    """
    out = drop_unused_columns(df.copy())
    out = handle_missing_values(out)
    out = convert_ordinal_features(out)
    return out


def build_pipeline_frame(raw: pd.DataFrame,
                         outlier_threshold: float = 2.0) -> pd.DataFrame:
    """
    Devuelve el DataFrame tal y como llega al One-Hot Encoding, CON la columna
    objetivo incluida (hace falta para el precio mediano por barrio).

    Es importante llegar hasta aquí (y no quedarse en `_clean_partial`) porque:

    * la eliminación de outliers ocurre antes del encoding y hace desaparecer
      categorías poco frecuentes. Ejemplo real: `RoofMatl` tiene 8 valores en el
      CSV, pero las viviendas con ClyTile, Membran, Metal y Roll se eliminan como
      outliers, así que el one-hot solo ve 5 valores (4 dummies + la base
      `CompShg`). Derivar el contrato del CSV sin filtrar produciría columnas
      one-hot que el modelo no conoce.
    * desde el arreglo de la fuga de datos, el encoding se ajusta SOLO con el
      conjunto de entrenamiento, así que el contrato debe mirar exactamente ese
      conjunto y no el total.

    Se reutiliza `split_and_clean` para que el contrato no pueda divergir del
    pipeline real.
    """
    X_train, _, y_train, _ = split_and_clean(
        raw,
        target_col='SalePrice',
        handle_outliers_flag=True,
        outlier_threshold=outlier_threshold,
    )
    frame = X_train.copy()
    frame['SalePrice'] = y_train
    return frame


def build_reference_row(clean: pd.DataFrame) -> Dict[str, Any]:
    """
    Vivienda mediana del dataset.

    Columnas numéricas -> mediana. Columnas categóricas (texto) -> moda.
    Es el punto de partida sobre el que se sobrescriben los campos del usuario.

    Excepción: MSSubClass es en realidad un CÓDIGO nominal (20, 30, 60, 120...)
    que el pipeline trata como número porque no está en ningún grupo de
    COLUMN_GROUPS. Su mediana (50) no representa nada; se usa la moda (20), que
    es el tipo de vivienda más frecuente del dataset.
    """
    row: Dict[str, Any] = {}
    for col in clean.columns:
        serie = clean[col]
        if pd.api.types.is_numeric_dtype(serie):
            if col in MODE_COLUMNS:
                modo = serie.mode()
                row[col] = float(modo.iloc[0]) if len(modo) else 0.0
            else:
                valor = serie.median()
                row[col] = float(valor) if pd.notna(valor) else 0.0
        else:
            modo = serie.mode()
            row[col] = str(modo.iloc[0]) if len(modo) else ''

    # Coherencia interna del sótano: en Ames TotalBsmtSF es la suma de los tres.
    # Se reconstruye desde sus componentes para no romper esa identidad.
    partes = ['BsmtFinSF1', 'BsmtFinSF2', 'BsmtUnfSF']
    if all(p in row for p in partes) and 'TotalBsmtSF' in row:
        row['TotalBsmtSF'] = float(sum(row[p] for p in partes))

    return row


def build_categorical_contract(clean: pd.DataFrame,
                               feature_order: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Para cada columna categórica: valores posibles y cuál queda como base.

    La categoría base NO se deduce de una regla sobre pandas (`get_dummies`
    con `drop_first=True` no elimina siempre la alfabéticamente primera: en
    `RoofMatl` elimina `CompShg`, no `ClyTile`). Se determina empíricamente:
    **la base es el valor cuyo dummy no aparece entre las 213 características**.
    Si no hay exactamente uno, es un error y se avisa.
    """
    orden = set(feature_order)
    contrato: Dict[str, Dict[str, Any]] = {}

    for col in COLUMN_GROUPS['categorical']:
        if col not in clean.columns:
            continue

        valores = sorted(clean[col].dropna().astype(str).unique().tolist())
        ausentes = [v for v in valores if f'{col}_{v}' not in orden]
        presentes = [v for v in valores if f'{col}_{v}' in orden]

        if len(ausentes) != 1:
            raise ValueError(
                f"No se puede determinar la categoría base de '{col}': "
                f"{len(ausentes)} valores sin dummy ({ausentes[:5]}). "
                f"Se esperaba exactamente uno."
            )
        if len(presentes) != len(valores) - 1:
            raise ValueError(f"Inconsistencia en los dummies de '{col}'.")

        base = ausentes[0]
        contrato[col] = {
            'valores': valores,
            'base': base,
            'dummies': [f'{col}_{v}' for v in valores if v != base],
        }

    return contrato


def build_garage_area_lookup(clean: pd.DataFrame) -> Dict[str, float]:
    """
    Mediana de GarageArea para cada número de plazas de garaje.

    Así GarageCars y GarageArea quedan siempre coherentes entre sí (en vez de
    tomar medianas independientes que describirían un garaje imposible).
    """
    if 'GarageCars' not in clean.columns or 'GarageArea' not in clean.columns:
        return {}
    agrupado = clean.groupby('GarageCars')['GarageArea'].median()
    return {str(int(k)): float(v) for k, v in agrupado.items()}


def build_ranges(x_train: pd.DataFrame, feature_order: List[str]) -> Dict[str, Dict[str, float]]:
    """Rango real de cada característica en el conjunto de entrenamiento."""
    rangos = {}
    for col in feature_order:
        if col in x_train.columns:
            rangos[col] = {
                'min': float(x_train[col].min()),
                'max': float(x_train[col].max()),
                'mean': float(x_train[col].mean()),
            }
    return rangos


# Campos que rellena el usuario en el formulario, en unidades crudas del
# dataset (ft², códigos, años...). Sus rangos reales se exportan para poder
# validar la entrada y para que ni el frontend ni la API lleven números mágicos.
CAMPOS_DEL_USUARIO = [
    'MSSubClass', 'GrLivArea', 'LotArea', 'OverallQual',
    'YearBuilt', 'BedroomAbvGr', 'FullBath', 'GarageCars',
]


def build_raw_ranges(frame: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Rango real (SIN escalar) de los campos del formulario.

    Ojo: `build_ranges` devuelve los rangos de X_train, y 23 de esas columnas
    están en z-scores. Estos son los valores tal y como los ve el usuario.
    """
    rangos = {}
    for col in CAMPOS_DEL_USUARIO:
        if col in frame.columns:
            serie = frame[col]
            rangos[col] = {
                'min': float(serie.min()),
                'max': float(serie.max()),
                'median': float(serie.median()),
                'mean': float(serie.mean()),
            }
    return rangos


def build_neighborhood_prices(frame: pd.DataFrame) -> Dict[str, float]:
    """
    Precio mediano real de venta por barrio.

    Sirve para dar contexto honesto en la interfaz (precio de referencia del
    barrio) y para poder comparar cuánto se desvía la predicción.
    """
    if 'Neighborhood' not in frame.columns or 'SalePrice' not in frame.columns:
        return {}
    medianas = frame.groupby('Neighborhood')['SalePrice'].median()
    return {str(k): float(v) for k, v in medianas.items()}


# ============================================================
# 2. GENERACIÓN DEL CONTRATO
# ============================================================

def build_contract() -> Dict[str, Any]:
    logger.info(f'📂 Leyendo {RAW_TRAIN}')
    raw = pd.read_csv(RAW_TRAIN)

    feature_order = [l.strip() for l in open(FEATURE_NAMES, encoding='utf-8') if l.strip()]
    x_train = pd.read_csv(PROCESSED_X)

    # Frame tal como llega al encoding: es la fuente de verdad del contrato.
    frame = build_pipeline_frame(raw)
    logger.info(f'  Filas de entrenamiento tras eliminar outliers: {len(frame)}')

    # El precio se usa para el contexto por barrio, pero no forma parte de las
    # características: se quita antes de construir la vivienda de referencia.
    precios_barrio = build_neighborhood_prices(frame)
    frame_sin_precio = frame.drop(columns=['SalePrice'], errors='ignore')

    reference_row = build_reference_row(frame_sin_precio)
    categorias = build_categorical_contract(frame_sin_precio, feature_order)

    # YrSold de referencia: la mediana del dataset. Todas las edades (HouseAge,
    # GarageAge, YearsSinceRemodel) se calculan contra este año para no salirse
    # de la distribución de entrenamiento.
    anio_referencia = int(reference_row.get('YrSold', 2008))

    barrios = sorted(frame_sin_precio['Neighborhood'].dropna().unique().tolist())
    tipos = sorted(int(v) for v in frame_sin_precio['MSSubClass'].dropna().unique().tolist())

    contrato: Dict[str, Any] = {
        'version': 1,
        'descripcion': (
            'Contrato de características derivado de data/raw/train.csv. '
            'Define la vivienda de referencia, las tablas one-hot y los rangos '
            'válidos para construir el vector de 213 características.'
        ),
        'moneda': 'USD',
        'dataset': 'Ames Housing (Iowa, EE. UU.)',
        'n_registros_entrenamiento': int(len(raw)),
        'precio_mediano': float(raw['SalePrice'].median()),
        'precio_medio': float(raw['SalePrice'].mean()),
        'precio_min': float(raw['SalePrice'].min()),
        'precio_max': float(raw['SalePrice'].max()),
        'feature_order': feature_order,
        'reference_row': reference_row,
        'reference_year': anio_referencia,
        'categorical': categorias,
        'garage_area_por_plaza': build_garage_area_lookup(frame),
        'ranges': build_ranges(x_train, feature_order),
        'raw_ranges': build_raw_ranges(frame),
        'neighborhood_median_price': precios_barrio,
        'ui': {
            'neighborhoods': [
                {'valor': b, 'etiqueta': NEIGHBORHOOD_LABELS.get(b, b)} for b in barrios
            ],
            'ms_subclass': [
                {'valor': t, 'etiqueta': MS_SUBCLASS_LABELS.get(t, f'Tipo {t}')} for t in tipos
            ],
        },
    }
    return contrato


def save_contract(contrato: Dict[str, Any], path: Path = CONTRACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(contrato, f, ensure_ascii=False, indent=2)
    return path


def load_contract(path: Path = CONTRACT_PATH) -> Dict[str, Any]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    contrato = build_contract()
    destino = save_contract(contrato)

    ref = contrato['reference_row']
    logger.info('=' * 64)
    logger.info('📋 CONTRATO DE CARACTERÍSTICAS GENERADO')
    logger.info('=' * 64)
    logger.info(f'  Destino               : {destino}')
    logger.info(f'  Características       : {len(contrato["feature_order"])}')
    logger.info(f'  Barrios disponibles   : {len(contrato["ui"]["neighborhoods"])}')
    logger.info(f'  Tipos MSSubClass      : {len(contrato["ui"]["ms_subclass"])}')
    logger.info(f'  Año de referencia     : {contrato["reference_year"]}')
    logger.info(f'  Precio mediano        : ${contrato["precio_mediano"]:,.0f}')
    logger.info('  Vivienda de referencia (selección):')
    for campo in ['GrLivArea', 'LotArea', 'OverallQual', 'OverallCond', 'YearBuilt',
                  'BedroomAbvGr', 'FullBath', 'GarageCars', 'GarageArea', 'TotalBsmtSF',
                  'Neighborhood', 'MSSubClass', 'YrSold', 'MoSold']:
        logger.info(f'    {campo:<14} = {ref.get(campo)}')
    logger.info('=' * 64)


if __name__ == '__main__':
    main()
