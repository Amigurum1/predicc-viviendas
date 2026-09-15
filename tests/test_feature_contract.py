"""
Validación del contrato de características y del conversor canónico.

Estas pruebas son el contrato de calidad del bloque B2/B3: garantizan que la
fila que recibe el modelo se construye igual que en entrenamiento, que ninguna
característica se queda a 0 por olvido y que barrio y tipo de vivienda SÍ
influyen en el precio (antes se ignoraban por completo).
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from src.data.feature_contract import (
    CONTRACT_PATH, FEATURE_NAMES, RAW_TRAIN, load_contract,
)
from src.data.model_row import (
    build_model_row, predict_from_fields, get_scaler_columns, self_check,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCALER_PATH = PROJECT_ROOT / 'models_saved' / 'scaler.pkl'
MODEL_PATH = PROJECT_ROOT / 'models_saved' / 'RandomForest_Tuned.pkl'


@pytest.fixture(scope='module')
def contrato():
    return load_contract()


@pytest.fixture(scope='module')
def artefactos():
    return joblib.load(MODEL_PATH), joblib.load(SCALER_PATH)


# ============================================================
# El contrato
# ============================================================

def test_contrato_y_modelo_estan_de_acuerdo(contrato, artefactos):
    """
    El contrato, `feature_names.txt` y el modelo deben describir el mismo
    espacio de características.

    El número exacto no se fija a mano: depende del reparto train/test, porque
    una categoría poco frecuente puede caer solo en test y desaparecer del
    one-hot (le pasó a `Electrical_Mix`, que dejó 212 en vez de 213).
    """
    model, _ = artefactos
    features_fichero = [l.strip() for l in open(FEATURE_NAMES, encoding='utf-8') if l.strip()]

    assert contrato['feature_order'] == features_fichero
    assert len(contrato['feature_order']) == model.n_features_in_
    assert len(contrato['feature_order']) > 100


def test_contrato_cubre_todos_los_barrios_y_tipos(contrato):
    raw = pd.read_csv(RAW_TRAIN)
    assert len(contrato['ui']['neighborhoods']) == raw['Neighborhood'].nunique() == 25
    assert len(contrato['ui']['ms_subclass']) == raw['MSSubClass'].nunique() == 15


def test_la_categoria_base_es_la_primera_alfabeticamente(contrato):
    """pd.get_dummies(drop_first=True) elimina la primera categoría ordenada."""
    for col, info in contrato['categorical'].items():
        assert info['base'] == info['valores'][0], col
        assert info['dummies'] == [f'{col}_{v}' for v in info['valores'][1:]], col


def test_la_categoria_base_es_la_que_pandas_elimina(contrato):
    """
    Verifica la deducción contra el comportamiento REAL de pd.get_dummies.

    No se asume ninguna regla: se codifica el dataset limpio y se comprueba
    que las filas cuyo valor es la base declarada tienen todos sus dummies a 0,
    y que el resto tiene exactamente un dummy a 1 con el nombre esperado.
    """
    from src.data.feature_contract import build_pipeline_frame
    from src.data.preprocess import encode_categorical_features

    raw = pd.read_csv(RAW_TRAIN)
    clean = build_pipeline_frame(raw)
    encoded = encode_categorical_features(clean)

    comprobadas = 0
    for col, info in contrato['categorical'].items():
        dummies = info['dummies']
        for dummy in dummies:
            assert dummy in encoded.columns, f'{dummy} no lo genera pandas'

        suma = encoded[dummies].sum(axis=1)
        es_base = clean[col].astype(str) == info['base']

        assert (suma[es_base] == 0).all(), f'{col}: la base {info["base"]} no da todo ceros'
        assert (suma[~es_base] == 1).all(), f'{col}: hay filas sin exactamente un dummy'
        comprobadas += 1

    assert comprobadas == len(contrato['categorical'])


def test_los_dummies_del_contrato_existen_en_el_modelo(contrato):
    feature_order = set(contrato['feature_order'])
    for col, info in contrato['categorical'].items():
        for dummy in info['dummies']:
            assert dummy in feature_order, f'{dummy} no está entre las características del modelo'


# ============================================================
# El conversor: nada de ceros silenciosos
# ============================================================

def test_autocomprobacion_ok(contrato, artefactos):
    model, scaler = artefactos
    resultado = self_check(contrato, model, scaler)
    assert resultado['ok'], resultado['problemas']
    assert resultado['shape'] == (1, len(contrato['feature_order']))
    print(f'\n  características no nulas: {resultado["no_cero"]}/'
          f'{len(contrato["feature_order"])}')


def test_las_features_derivadas_se_calculan_y_no_son_cero(contrato):
    """
    Antes, estas 12 columnas iban a 0 en lugar de calcularse. Es la comprobación
    directa del train/serve skew que rompía las predicciones.
    """
    vector = build_model_row({}, contrato)['vector'][0]
    indice = {nombre: i for i, nombre in enumerate(contrato['feature_order'])}

    derivadas = ['TotalSF', 'LivArea_Qual', 'Bsmt_Qual', 'Qual_Cond', 'Age_Qual',
                 'HouseAge', 'YearsSinceRemodel', 'GrLivArea_sq', 'OverallQual_sq',
                 'TotalBsmtSF_sq', 'HouseAge_sq', 'TotalPorchSF']
    for col in derivadas:
        assert vector[indice[col]] != 0, f'{col} sigue a 0'


def test_las_columnas_invalidas_en_cero_ahora_tienen_valor_real(contrato):
    """MSSubClass, LotFrontage, YrSold y las ordinales estaban fuera de rango."""
    vector = build_model_row({}, contrato)['vector'][0]
    indice = {nombre: i for i, nombre in enumerate(contrato['feature_order'])}

    assert vector[indice['MSSubClass']] >= 20, 'MSSubClass sigue fuera de rango'
    assert vector[indice['LotFrontage']] >= 21, 'LotFrontage sigue fuera de rango'
    assert 2006 <= vector[indice['YrSold']] <= 2010, 'YrSold sigue fuera de rango'
    assert vector[indice['HouseAge']] > 0, 'HouseAge salía negativa con YrSold=0'
    for cualidad in ['ExterQual', 'BsmtQual', 'KitchenQual', 'HeatingQC']:
        assert vector[indice[cualidad]] >= 1, f'{cualidad} sigue fuera de rango'


def test_todos_los_valores_estan_en_el_rango_de_entrenamiento(contrato, artefactos):
    """
    La validación se hace sobre el vector ESCALADO, que es el espacio de
    X_train.csv (las 23 columnas del scaler están en z-scores).
    """
    model, scaler = artefactos
    salida = predict_from_fields({}, contrato, model, scaler)
    assert salida['fuera_de_rango'] == [], salida['fuera_de_rango']


def test_el_rango_no_se_valida_sobre_el_vector_sin_escalar(contrato, artefactos):
    """
    Regresión: antes se comparaba el vector crudo contra rangos escalados, lo
    que daba 18 falsos positivos. Comprobar que la distinción es real.
    """
    from src.data.model_row import validate_ranges
    model, _ = artefactos
    crudo = build_model_row({}, contrato)['vector']
    assert validate_ranges(crudo, contrato), 'el vector crudo no debería pasar la validación'


def test_campo_desconocido_o_derivado_se_rechaza(contrato):
    with pytest.raises(ValueError, match='no soportados'):
        build_model_row({'precio_deseado': 1}, contrato)
    with pytest.raises(ValueError, match='se calculan a partir de otros campos'):
        build_model_row({'TotalSF': 3000}, contrato)


def test_barrio_desconocido_se_rechaza(contrato):
    with pytest.raises(ValueError, match='Valor desconocido'):
        build_model_row({'Neighborhood': 'Miraflores'}, contrato)


def test_el_scaler_espera_23_columnas_y_todas_existen(contrato, artefactos):
    _, scaler = artefactos
    cols = get_scaler_columns(scaler)
    assert len(cols) == 23
    for col in cols:
        assert col in contrato['feature_order'], col


# ============================================================
# El modelo responde de forma sensata
# ============================================================

def _precio(campos, contrato, artefactos):
    model, scaler = artefactos
    return predict_from_fields(campos, contrato, model, scaler)['precio']


def test_vivienda_mediana_predice_un_precio_cercano_a_la_mediana(contrato, artefactos):
    """
    Prueba de coherencia global: la vivienda mediana del dataset debe predecir
    un precio parecido al precio mediano real ($163.000). Antes daba $58.907.
    """
    mediana = contrato['precio_mediano']
    precio = _precio({}, contrato, artefactos)
    desviacion = abs(precio - mediana) / mediana
    print(f'\n  vivienda mediana -> ${precio:,.0f} (real ${mediana:,.0f}, '
          f'desviación {desviacion:.1%})')
    assert desviacion < 0.20, f'desviación {desviacion:.1%} respecto a la mediana'


def test_el_barrio_cambia_el_precio(contrato, artefactos):
    """
    Acceptance de B2: antes Miraflores, Callao y San Isidro daban EXACTAMENTE
    el mismo precio porque el mapper apuntaba a columnas inexistentes.

    Ahora el barrio entra en el modelo, pero el invariante NO es "cualquier par de
    barrios da precios distintos": un bosque aleatorio es una función constante a
    trozos y, para la vivienda mediana, muchos barrios acaban en la misma hoja
    (NridgHt, MeadowV y NoRidge dan el mismo precio). Lo que sí debe cumplirse es
    que el barrio influya en ALGUNOS casos, es decir, que el conjunto de barrios
    produzca más de un precio.
    """
    precios = {
        b['valor']: _precio({'Neighborhood': b['valor']}, contrato, artefactos)
        for b in contrato['ui']['neighborhoods']
    }
    distintos = sorted({round(p, 2) for p in precios.values()})
    minimo, maximo = min(precios.values()), max(precios.values())

    print(f'\n  {len(precios)} barrios -> {len(distintos)} precios distintos '
          f'(de ${minimo:,.0f} a ${maximo:,.0f})')
    print('  los 3 más baratos:', ', '.join(
        f'{k} ${v:,.0f}' for k, v in sorted(precios.items(), key=lambda x: x[1])[:3]))

    assert len(distintos) > 1, 'el barrio se sigue ignorando por completo'
    assert maximo > minimo, 'ningún barrio cambia el precio'


def test_el_barrio_es_poco_relevante_para_este_modelo(contrato, artefactos):
    """
    Documenta una limitación real del modelo entrenado, no del conversor: la
    información del barrio está casi toda absorbida por LivArea_Qual (62% de la
    importancia por sí sola). Si algún día se reentrena y el barrio pasa a pesar,
    esta prueba avisará.
    """
    model, _ = artefactos
    importancias = dict(zip(model.feature_names_in_, model.feature_importances_))
    total_barrios = sum(v for k, v in importancias.items() if k.startswith('Neighborhood_'))
    print(f'\n  importancia total de los 24 barrios: {total_barrios:.4f} '
          f'| LivArea_Qual: {importancias["LivArea_Qual"]:.4f}')
    assert total_barrios > 0, 'el barrio ha dejado de usarse por completo'
    assert total_barrios < 0.05, 'el barrio ha pasado a pesar mucho: revisar este supuesto'


def test_el_tipo_de_vivienda_cambia_el_precio(contrato, artefactos):
    """Acceptance de B2 para MSSubClass (antes intentaba MSSubClass_1, que no existe)."""
    precios = {t: _precio({'MSSubClass': t}, contrato, artefactos)
               for t in (20, 60, 90, 120)}
    print(f'\n  por MSSubClass: ' + ', '.join(f'{k}->${v:,.0f}' for k, v in precios.items()))
    assert len(set(round(v, 2) for v in precios.values())) > 1, 'el tipo no influye'


def test_mas_superficie_implica_mas_precio(contrato, artefactos):
    precios = [_precio({'GrLivArea': ft2}, contrato, artefactos)
               for ft2 in (800, 1200, 1600, 2200, 3000)]
    print(f'\n  por superficie (ft²): ' + ', '.join(f'${p:,.0f}' for p in precios))
    assert precios == sorted(precios), f'no es monótono: {precios}'
    assert precios[-1] > precios[0] * 1.5


def test_mas_calidad_implica_mas_precio(contrato, artefactos):
    precios = [_precio({'OverallQual': q}, contrato, artefactos) for q in (3, 5, 7, 9)]
    print(f'\n  por OverallQual: ' + ', '.join(f'${p:,.0f}' for p in precios))
    assert precios == sorted(precios), f'no es monótono: {precios}'


def test_un_garaje_mayor_implica_mas_precio(contrato, artefactos):
    precios = [_precio({'GarageCars': c}, contrato, artefactos) for c in (0, 1, 2, 3)]
    print(f'\n  por plazas de garaje: ' + ', '.join(f'${p:,.0f}' for p in precios))
    assert precios == sorted(precios), f'no es monótono: {precios}'


# ============================================================
# Fidelidad sobre casas reales
# ============================================================

def test_fidelidad_al_reproducir_casas_reales(contrato, artefactos):
    """
    Se cogen casas reales del dataset, se describen SOLO con los campos que la
    aplicación expone y se compara el precio predicho con el real. Mide la
    fidelidad real de la app, no la del modelo en su conjunto.
    """
    model, scaler = artefactos
    raw = pd.read_csv(RAW_TRAIN).sample(200, random_state=7)

    errores = []
    for _, fila in raw.iterrows():
        campos = {
            'Neighborhood': fila['Neighborhood'],
            'MSSubClass': int(fila['MSSubClass']),
            'GrLivArea': float(fila['GrLivArea']),
            'LotArea': float(fila['LotArea']),
            'OverallQual': float(fila['OverallQual']),
            'YearBuilt': float(fila['YearBuilt']),
            'BedroomAbvGr': float(fila['BedroomAbvGr']),
            'FullBath': float(fila['FullBath']),
            'GarageCars': float(fila['GarageCars']),
        }
        predicho = predict_from_fields(campos, contrato, model, scaler)['precio']
        real = float(fila['SalePrice'])
        errores.append(abs(predicho - real) / real)

    mape = float(np.mean(errores))
    mediana = float(np.median(errores))
    print(f'\n  MAPE sobre 200 casas reales: {mape:.1%} (mediana {mediana:.1%})')

    # Umbral honesto: describiendo la casa solo con 9 campos se pierde
    # información (calidades, sótano, porches...), así que se acepta hasta 25%.
    assert mape < 0.25, f'MAPE {mape:.1%} demasiado alto'
