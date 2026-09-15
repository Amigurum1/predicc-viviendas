"""
Diagnóstico de los artefactos del modelo y del contrato de características.

Sustituye a `check_model.py` y `check_mapper.py`, que quedaron obsoletos:

* `check_model.py` hacía `scaler.transform()` sobre la matriz completa de 213
  columnas, que es exactamente el error que provocaba que el scaler nunca se
  aplicara (espera 23 columnas).
* `check_mapper.py` usaba el mapper antiguo, con distritos de Lima y campos que
  ya no existen.

Este script usa el camino real de producción (`src/data/model_row.py`), así que
si aquí sale bien, la API también.

Uso:
    python scripts/check_artifacts.py
"""

import logging
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# La consola de Windows usa cp1252 y no puede imprimir emojis.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, 'reconfigure'):
        try:
            _flujo.reconfigure(encoding='utf-8')
        except Exception:
            pass

import joblib  # noqa: E402
import sklearn  # noqa: E402

MODELS = PROJECT_ROOT / 'models_saved'
MODELO = MODELS / 'RandomForest_Tuned.pkl'
SCALER = MODELS / 'scaler.pkl'
CONTRATO = MODELS / 'feature_contract.json'

problemas = []


def titulo(texto):
    print('\n' + texto)
    print('-' * len(texto))


titulo('1. ARTEFACTOS EN models_saved/')
for ruta in (MODELO, SCALER, CONTRATO, MODELS / 'feature_names.txt',
             MODELS / 'feature_importance.csv'):
    if ruta.exists():
        print(f'  OK      {ruta.name:<26} {ruta.stat().st_size / 1024:>10,.1f} KB')
    else:
        print(f'  FALTA   {ruta.name}')
        problemas.append(f'falta {ruta.name}')

titulo('2. VERSIONES')
print(f'  scikit-learn instalado : {sklearn.__version__}')
import pandas as pd  # noqa: E402
import numpy as np  # noqa: E402
print(f'  pandas                 : {pd.__version__}')
print(f'  numpy                  : {np.__version__}')

with warnings.catch_warnings(record=True) as capturados:
    warnings.simplefilter('always')
    modelo = joblib.load(MODELO)
    scaler = joblib.load(SCALER)
    avisos_version = [str(w.message) for w in capturados
                      if 'InconsistentVersion' in type(w.message).__name__]

if avisos_version:
    print('  ⚠️  AVISO: los artefactos se serializaron con otra versión de scikit-learn.')
    print(f'      {avisos_version[0][:110]}')
    print('      No es un error fatal (las predicciones siguen saliendo), pero la')
    print('      versión canónica es la de requirements.txt. Para reproducirla:')
    print('        docker run --rm -v "$PWD:/app" -w /app predicc_viviendas-api \\')
    print('          python scripts/check_artifacts.py')
    print('      O regeneralos con: python src/models/train_model.py')
    # No se añade a `problemas`: se espera en una máquina de desarrollo que no
    # use el entorno fijado, y los tests pasan igualmente.
else:
    print('  ✅ Los artefactos son compatibles con la versión instalada')

titulo('3. MODELO')
print(f'  Tipo             : {type(modelo).__name__}')
print(f'  Características  : {modelo.n_features_in_}')
print(f'  Árboles          : {len(getattr(modelo, "estimators_", []))}')
print(f'  Scaler espera    : {scaler.n_features_in_} columnas (no todas: ver model_row.py)')

titulo('4. CONTRATO DE CARACTERÍSTICAS')
from src.data.feature_contract import load_contract  # noqa: E402
from src.data.model_row import (  # noqa: E402
    apply_scaler, build_model_row, get_scaler_columns, self_check,
)

contrato = load_contract()
print(f'  Dataset           : {contrato["dataset"]}')
print(f'  Moneda            : {contrato["moneda"]}')
print(f'  Características   : {len(contrato["feature_order"])}')
print(f'  Barrios           : {len(contrato["ui"]["neighborhoods"])}')
print(f'  Tipos MSSubClass  : {len(contrato["ui"]["ms_subclass"])}')
print(f'  Año de referencia : {contrato["reference_year"]}')
print(f'  Precio mediano    : ${contrato["precio_mediano"]:,.0f}')

columnas_scaler = get_scaler_columns(scaler)
print(f'  Columnas del scaler: {len(columnas_scaler)}')
if len(columnas_scaler) != 23:
    problemas.append(f'el scaler espera {len(columnas_scaler)} columnas, se esperaban 23')

# El contrato, feature_names.txt y el modelo deben describir lo mismo
n_features = len(contrato['feature_order'])
if n_features != modelo.n_features_in_:
    problemas.append(
        f'el contrato tiene {n_features} características y el modelo espera '
        f'{modelo.n_features_in_}: hay que regenerar el contrato'
    )
else:
    print(f'  ✅ Contrato y modelo coinciden en {n_features} características')

titulo('5. CAMINO DE PRODUCCIÓN (vivienda mediana -> precio)')
comprobacion = self_check(contrato, modelo, scaler)
print(f'  Vector            : {comprobacion["shape"]}')
print(f'  Valores no nulos  : {comprobacion["no_cero"]}/{n_features}')
print(f'  Fuera de rango    : {len(comprobacion["fuera_de_rango"])}')

salida = build_model_row({}, contrato)
escalado = apply_scaler(salida['vector'], scaler, contrato)
precio = float(modelo.predict(escalado)[0])
mediana = contrato['precio_mediano']
desviacion = abs(precio - mediana) / mediana * 100

print(f'  Precio predicho   : ${precio:,.0f}')
print(f'  Precio mediano    : ${mediana:,.0f}')
print(f'  Desviación        : {desviacion:.1f}%')
if desviacion > 20:
    problemas.append(f'la vivienda mediana se desvía un {desviacion:.1f}% del precio mediano')

titulo('6. UN EJEMPLO CONCRETO')
amostra = {
    'Neighborhood': 'NridgHt', 'MSSubClass': 60, 'GrLivArea': 2153.0,
    'LotArea': 10764.0, 'OverallQual': 8, 'YearBuilt': 1995,
    'BedroomAbvGr': 4, 'FullBath': 2, 'GarageCars': 3,
}
s = build_model_row(amostra, contrato)
x = apply_scaler(s['vector'], scaler, contrato)
p = float(modelo.predict(x)[0])
print(f'  Entrada  : {amostra}')
print(f'  Precio   : ${p:,.0f}')

titulo('RESUMEN')
if problemas:
    print(f'  ❌ {len(problemas)} problema(s):')
    for p_ in problemas:
        print(f'     - {p_}')
    sys.exit(1)

print('  ✅ Todo correcto: artefactos, contrato y camino de predicción')
