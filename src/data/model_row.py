# src/data/model_row.py
"""
Construcción del vector de entrada del modelo (213 características) para una
vivienda concreta.

Es la ÚNICA vía por la que se construye una fila para el modelo, tanto en
inferencia como en las pruebas. Garantiza dos cosas:

1. **Consistencia train/serve**: reutiliza literalmente las funciones de
   ingeniería de `src/data/preprocess.py`, así que la fila se construye igual
   que durante el entrenamiento. Nada de reimplementar fórmulas a mano.

2. **Nada de ceros silenciosos**: toda característica que no produzca la
   ingeniería tiene que ser un one-hot conocido; si alguna se queda sin origen,
   se lanza un error en vez de enviar un 0 al modelo. Antes esto pasaba con 12
   features derivadas (TotalSF, LivArea_Qual...) y ~15 columnas inválidas en 0
   (MSSubClass, YrSold, ordinales de calidad).

Ejemplo:
    contrato = load_contract()
    salida = build_model_row({'Neighborhood': 'NridgHt', 'GrLivArea': 2000}, contrato)
    X = salida['vector']            # (1, 213) sin escalar
"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.data.preprocess import (
    create_interaction_features,
    create_polynomial_features,
    create_temporal_features,
)
from src.data.feature_contract import load_contract

logger = logging.getLogger(__name__)


# Campos de Ames que se pueden fijar explícitamente desde fuera (unidades del
# dataset: pies cuadrados, códigos, años...). Cualquier otra clave es un error.
CAMPOS_PERMITIDOS = {
    'Neighborhood',      # barrio (texto)
    'MSSubClass',        # tipo de vivienda (código)
    'GrLivArea',         # superficie habitable sobre rasante (ft²)
    'LotArea',           # superficie de la parcela (ft²)
    'OverallQual',       # calidad general 1-10
    'OverallCond',       # estado general 1-10
    'YearBuilt',         # año de construcción
    'YearRemodAdd',      # año de reforma
    'BedroomAbvGr',      # dormitorios sobre rasante
    'FullBath',          # baños completos
    'HalfBath',          # aseos
    'TotRmsAbvGrd',      # estancias totales sobre rasante
    'Fireplaces',        # chimeneas
    'GarageCars',        # plazas de garaje
    'GarageArea',        # superficie del garaje (ft²)
    'TotalBsmtSF',       # superficie de sótano (ft²)
    'PoolArea',          # superficie de piscina (ft²)
    'WoodDeckSF',        # terraza de madera (ft²)
    'OpenPorchSF',       # porche descubierto (ft²)
    'LotFrontage',       # frente de parcela (ft)
    'ExterQual',         # calidad del exterior 1-5
    'KitchenQual',       # calidad de la cocina 1-5
    'BsmtQual',          # calidad del sótano 1-5
}

# Campos que el dataset calcula en función de otros: si se fijan a mano se
# rompen identidades internas del dataset (por ejemplo GrLivArea =
# 1stFlrSF + 2ndFlrSF + LowQualFinSF). Se rechazan explícitamente.
CAMPOS_DERIVADOS = {
    'HouseAge', 'YearsSinceRemodel', 'GarageAge', 'IsRemodeled',
    'TotalSF', 'LivArea_Qual', 'Bsmt_Qual', 'Qual_Cond', 'Age_Qual',
    'TotalPorchSF', 'GrLivArea_sq', 'OverallQual_sq', 'TotalBsmtSF_sq',
    'HouseAge_sq', 'YrSold', 'MoSold', 'IsRemodeled',
}


def _apply_overrides(row: Dict[str, Any], campos: Dict[str, Any],
                     contrato: Dict[str, Any]) -> Dict[str, Any]:
    """Sobrescribe la fila de referencia y restablece las coherencias internas."""
    row = dict(row)

    desconocidos = set(campos) - CAMPOS_PERMITIDOS
    if desconocidos:
        derivados = sorted(desconocidos & CAMPOS_DERIVADOS)
        pista = (
            f" {derivados} se calculan a partir de otros campos y no se pueden fijar."
            if derivados else ''
        )
        raise ValueError(
            f"Campos no soportados: {sorted(desconocidos)}.{pista} "
            f"Permitidos: {sorted(CAMPOS_PERMITIDOS)}"
        )

    for clave, valor in campos.items():
        if valor is None:
            continue
        row[clave] = valor

    # --- Coherencias que el dataset mantiene y aquí hay que reproducir ---

    # 1. El sótano es la suma de sus tres componentes.
    if 'TotalBsmtSF' in campos and campos['TotalBsmtSF'] is not None:
        total = float(campos['TotalBsmtSF'])
        partes = ['BsmtFinSF1', 'BsmtFinSF2', 'BsmtUnfSF']
        suma_ref = sum(float(row.get(p, 0.0)) for p in partes)
        if suma_ref > 0:
            # Se reparte proporcionalmente al reparto típico del dataset.
            for p in partes:
                row[p] = total * (float(row.get(p, 0.0)) / suma_ref)
        else:
            row['BsmtFinSF1'], row['BsmtFinSF2'], row['BsmtUnfSF'] = total, 0.0, 0.0

    # 2. Superficie habitable = planta baja + planta alta + calidad baja.
    #    Se asume vivienda de una planta (la mediana del dataset tiene
    #    2ndFlrSF = 0), lo que mantiene la identidad exacta.
    if 'GrLivArea' in campos and campos['GrLivArea'] is not None:
        row['1stFlrSF'] = float(campos['GrLivArea'])
        row['2ndFlrSF'] = 0.0
        row['LowQualFinSF'] = 0.0

    # 3. Sin reforma declarada, la reforma coincide con la construcción
    #    (IsRemodeled = 0, que es una categoría muy poblada del dataset).
    if 'YearBuilt' in campos and campos['YearBuilt'] is not None:
        anio = float(campos['YearBuilt'])
        if 'YearRemodAdd' not in campos:
            row['YearRemodAdd'] = anio
        if float(row.get('GarageCars', 0) or 0) > 0:
            # El garaje se construyó con la casa.
            row['GarageYrBlt'] = anio

    # 4. Garaje coherente: la superficie se deriva de las plazas con la mediana
    #    real del dataset, y sin plazas el garaje es 0. Si se indicó una
    #    superficie explícita, se respeta.
    if 'GarageCars' in campos and campos['GarageCars'] is not None:
        plazas = int(campos['GarageCars'])
        lookup = contrato.get('garage_area_por_plaza', {})
        if plazas <= 0:
            row['GarageCars'] = 0.0
            row['GarageArea'] = 0.0
        elif 'GarageArea' not in campos:
            row['GarageArea'] = float(lookup.get(str(plazas), row.get('GarageArea', 0.0)))

    # 5. Las estancias totales crecen con los dormitorios. La mediana del
    #    dataset es 3 dormitorios y 6 estancias, de ahí el +3.
    if 'BedroomAbvGr' in campos and campos['BedroomAbvGr'] is not None:
        if 'TotRmsAbvGrd' not in campos:
            row['TotRmsAbvGrd'] = float(np.clip(int(campos['BedroomAbvGr']) + 3, 2, 14))

    # 6. Un aseo solo tiene sentido si hay baños completos.
    if float(row.get('FullBath', 0) or 0) == 0:
        row['HalfBath'] = 0.0

    return row


def _resolve_features(row_frame: pd.DataFrame, contrato: Dict[str, Any]) -> Dict[str, float]:
    """
    Traduce la fila ya procesada a las 213 características, por nombre.

    Los one-hot parten de 0 (la categoría base del dataset es legítimamente 0)
    y se pone a 1 el dummy del valor elegido. Después se comprueba que NINGUNA
    característica se haya quedado sin origen conocido: si la ingeniería no la
    produjo y no es un dummy declarado, es un error, no un 0.
    """
    feature_order: List[str] = contrato['feature_order']
    categorias: Dict[str, Dict[str, Any]] = contrato['categorical']

    valores: Dict[str, float] = {col: 0.0 for col in feature_order}
    producidas = set()

    # a) Columnas que la ingeniería sí ha producido
    fila = row_frame.iloc[0]
    for col in feature_order:
        if col in row_frame.columns:
            valores[col] = float(fila[col])
            producidas.add(col)

    # b) One-hot de las categóricas
    todos_los_dummies = set()
    for cat, info in categorias.items():
        todos_los_dummies.update(info['dummies'])
        if cat not in row_frame.columns:
            continue
        valor = str(fila[cat])
        if valor == info['base']:
            continue  # la categoría base son todos los dummies a 0
        dummy = f'{cat}_{valor}'
        if dummy not in valores:
            raise ValueError(
                f"Valor desconocido para '{cat}': {valor!r}. "
                f"Válidos: {info['valores']}"
            )
        valores[dummy] = 1.0
        producidas.add(dummy)

    # c) Control: nada puede quedarse a 0 por olvido
    sin_origen = [
        col for col in feature_order
        if col not in producidas and col not in todos_los_dummies
    ]
    if sin_origen:
        raise RuntimeError(
            "Estas características no las ha producido la ingeniería ni son "
            f"one-hot conocidos: {sin_origen[:10]} "
            f"(y {max(0, len(sin_origen) - 10)} más). Revisa el contrato."
        )

    return valores


def validate_ranges(vector: np.ndarray, contrato: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Comprueba que cada valor esté dentro del rango visto en entrenamiento.

    IMPORTANTE: el vector debe estar en el MISMO espacio que `X_train.csv`, es
    decir **ya escalado**. Las columnas que el scaler transforma están en
    z-scores en el conjunto de entrenamiento (LotArea va de -2,43 a 3,16), así
    que comparar ahí valores crudos daría falsos positivos constantes.
    """
    feature_order = contrato['feature_order']
    rangos = contrato.get('ranges', {})
    avisos = []

    for i, col in enumerate(feature_order):
        rango = rangos.get(col)
        if not rango:
            continue
        valor = float(vector[0, i])
        # Tolerancia: los one-hot son 0/1 exactos, los continuos pueden diferir
        # en el último decimal por el redondeo de la fila de referencia.
        margen = max(1e-6, abs(rango['max'] - rango['min']) * 1e-6)
        if valor < rango['min'] - margen or valor > rango['max'] + margen:
            avisos.append({
                'feature': col,
                'valor': valor,
                'min': rango['min'],
                'max': rango['max'],
            })

    return avisos


def build_model_row(campos: Dict[str, Any], contrato: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye el vector de 213 características (sin escalar) de una vivienda.

    Args:
        campos: valores en unidades del dataset (ver CAMPOS_PERMITIDOS).
                Lo que no se especifique toma el valor de la vivienda mediana.
        contrato: contrato cargado con `load_contract()`

    Returns:
        dict con:
            vector      -> np.ndarray (1, 213), SIN escalar
            usados      -> campos aplicados
            asumidos    -> campos que quedaron con el valor de la vivienda mediana

    Para validar rangos hay que usar `predict_from_fields`, porque el rango de
    referencia está en el espacio escalado.
    """
    if not contrato.get('feature_order'):
        raise ValueError('El contrato no contiene "feature_order".')

    row = _apply_overrides(dict(contrato['reference_row']), campos, contrato)

    # YrSold y MoSold siempre al valor de referencia: son columnas del vector
    # (no escaladas, rango 2006-2010 y 1-12) y con 0 quedaban fuera de rango.
    row['YrSold'] = float(contrato['reference_year'])
    row['MoSold'] = float(contrato['reference_row'].get('MoSold', 6.0))

    # Dataframe de una fila con TODAS las columnas del dataset limpio.
    row_frame = pd.DataFrame([row])
    row_frame = create_temporal_features(row_frame)
    row_frame = create_interaction_features(row_frame)
    row_frame = create_polynomial_features(row_frame)

    valores = _resolve_features(row_frame, contrato)
    vector = np.array([[valores[c] for c in contrato['feature_order']]], dtype=float)

    aplicados = {k: v for k, v in campos.items() if v is not None}
    asumidos = sorted(set(CAMPOS_PERMITIDOS) - set(aplicados))

    return {
        'vector': vector,
        'usados': aplicados,
        'asumidos': asumidos,
    }


# ============================================================
# ESCALADO Y PREDICCIÓN
# ============================================================

def get_scaler_columns(scaler) -> List[str]:
    """
    Columnas con las que se ajustó el scaler, en orden.

    El scaler NO se entrenó con las 213 características sino con un subconjunto
    de 23 columnas numéricas, por eso hay que localizarlas por nombre. Pasarle
    la matriz completa lanza ValueError ("X has 213 features, but
    StandardScaler is expecting 23 features").
    """
    nombres = getattr(scaler, 'feature_names_in_', None)
    if nombres is None:
        raise ValueError(
            "El scaler no expone 'feature_names_in_': se ajustó con un array sin "
            "nombres de columna y no se puede saber a qué características aplicarlo."
        )

    # feature_names_in_ es un np.ndarray: `nombres or []` daría un ValueError
    # por ambigüedad, así que se comprueba explícitamente.
    cols = [str(c) for c in nombres]
    if not cols:
        raise ValueError("El scaler tiene 'feature_names_in_' vacío.")

    n_features = getattr(scaler, 'n_features_in_', None)
    if n_features is not None and n_features != len(cols):
        raise ValueError(
            f"Scaler inconsistente: n_features_in_={n_features} pero "
            f"feature_names_in_ tiene {len(cols)} nombres."
        )
    return cols


def apply_scaler(vector: np.ndarray, scaler, contrato: Dict[str, Any]) -> np.ndarray:
    """
    Escala ÚNICAMENTE las columnas que el scaler conoce, localizándolas por
    nombre dentro del vector de 213 posiciones.
    """
    feature_order: List[str] = contrato['feature_order']
    cols = get_scaler_columns(scaler)

    desconocidas = [c for c in cols if c not in feature_order]
    if desconocidas:
        raise ValueError(
            f"El scaler espera columnas que no están en el contrato: {desconocidas[:5]}. "
            "Los artefactos de models_saved/ no son del mismo entrenamiento."
        )

    indices = [feature_order.index(c) for c in cols]
    vector = np.asarray(vector, dtype=float)
    if vector.ndim != 2 or vector.shape[1] != len(feature_order):
        raise ValueError(
            f"Se esperaba una matriz (n, {len(feature_order)}) y llegó {vector.shape}."
        )

    # DataFrame con nombres: sklearn valida el orden y no emite el aviso
    # "X does not have valid feature names".
    bloque = pd.DataFrame(vector[:, indices], columns=cols)

    escalado = vector.copy()
    escalado[:, indices] = scaler.transform(bloque)
    return escalado


def predict_from_fields(campos: Dict[str, Any], contrato: Dict[str, Any],
                        model, scaler) -> Dict[str, Any]:
    """
    Camino completo de inferencia: campos de Ames -> vector -> escalado -> precio.

    Devuelve también la confianza (dispersión entre los árboles del bosque) y
    los avisos de valores fuera del rango de entrenamiento.
    """
    salida = build_model_row(campos, contrato)
    vector = apply_scaler(salida['vector'], scaler, contrato) if scaler is not None else salida['vector']

    precio = float(model.predict(vector)[0])

    confianza = 0.85
    if hasattr(model, 'estimators_'):
        predicciones = np.array([arbol.predict(vector)[0] for arbol in model.estimators_])
        std = float(np.std(predicciones))
        if precio > 0:
            confianza = float(max(0.5, min(0.95, 1 - (std / precio))))

    salida['vector_escalado'] = vector
    salida['precio'] = precio
    salida['confianza'] = confianza
    salida['fuera_de_rango'] = validate_ranges(vector, contrato)
    return salida


# ============================================================
# AUTOCOMPROBACIÓN
# ============================================================

def self_check(contrato: Dict[str, Any] = None, model=None, scaler=None) -> Dict[str, Any]:
    """
    Comprueba que la vivienda mediana produce un vector de 213 valores y que
    ninguna característica se queda sin origen.

    Si se le pasan modelo y scaler, además valida que todos los valores estén
    dentro del rango de entrenamiento (ya en el espacio escalado).
    """
    contrato = contrato or load_contract()

    if model is not None and scaler is not None:
        salida = predict_from_fields({}, contrato, model, scaler)
        vector = salida['vector_escalado']
        fuera = salida['fuera_de_rango']
    else:
        salida = build_model_row({}, contrato)
        vector = salida['vector']
        fuera = []

    problemas = []
    if vector.shape != (1, len(contrato['feature_order'])):
        problemas.append(f'forma inesperada: {vector.shape}')
    if fuera:
        problemas.append(f'{len(fuera)} valores fuera de rango')

    return {
        'ok': not problemas,
        'problemas': problemas,
        'shape': vector.shape,
        'fuera_de_rango': fuera,
        'no_cero': int(np.count_nonzero(salida['vector'])),
    }
