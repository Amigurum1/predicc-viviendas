# src/models/train_model.py
"""
Entrenamiento reproducible del modelo de precios de Ames Housing.

QUÉ RESUELVE (B5)
-----------------
Hasta ahora los artefactos que usa la API (`RandomForest_Tuned.pkl`,
`scaler.pkl`, `feature_names.txt`, `feature_importance.csv`) solo se podían
regenerar ejecutando a mano `notebooks/02_model_training_ames.ipynb`, que además
necesitaba `matplotlib`, `seaborn` y `xgboost`, ausentes de `requirements.txt`.

Este script hace el ciclo completo desde `data/raw/train.csv`:

    datos crudos -> preprocesado -> entrenamiento -> métricas -> artefactos
                 -> contrato de características -> autocomprobación

Los hiperparámetros por defecto son EXACTAMENTE los que encontró el GridSearchCV
del notebook (`max_depth=15, min_samples_leaf=1, min_samples_split=2,
n_estimators=200`), para que el modelo resultante sea el mismo que ya estaba en
producción y solo cambie la versión de las librerías. Con `--retune` se vuelve a
ejecutar el GridSearch (tarda bastante más).

PENDIENTE CONOCIDO (B4): `src/data/preprocess.py` escala ANTES de dividir
train/test, así que el scaler se ajusta con el dataset completo (fuga de datos)
y las métricas de test salen optimistas. Se reproduce tal cual a propósito, para
no cambiar el modelo en el mismo paso en que se arregla el entorno; está
planificado como mejora aparte.

Uso:
    python src/models/train_model.py
    python src/models/train_model.py --retune
    python src/models/train_model.py --no-contract   # no regenerar el contrato
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.make_dataset import load_data, save_processed_data  # noqa: E402
from src.data.preprocess import process_data  # noqa: E402

logger = logging.getLogger(__name__)

RAW_TRAIN = PROJECT_ROOT / 'data' / 'raw' / 'train.csv'
MODELS_DIR = PROJECT_ROOT / 'models_saved'
MODEL_PATH = MODELS_DIR / 'RandomForest_Tuned.pkl'
IMPORTANCE_PATH = MODELS_DIR / 'feature_importance.csv'

# Hiperparámetros ganadores del GridSearchCV del notebook (CV R² = 0.8893)
PARAMS_POR_DEFECTO = {
    'n_estimators': 200,
    'max_depth': 15,
    'min_samples_split': 2,
    'min_samples_leaf': 1,
    'random_state': 42,
    'n_jobs': -1,
}

PARAM_GRID = {
    'n_estimators': [50, 100, 200],
    'max_depth': [10, 15, 20, None],
    'min_samples_split': [2, 5, 10],
    'min_samples_leaf': [1, 2, 4],
}


def _metricas(y_real, y_pred, etiqueta: str) -> dict:
    """R², RMSE, MAE y MAPE de un conjunto."""
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    m = {
        'conjunto': etiqueta,
        'n': int(len(y_real)),
        'r2': float(r2_score(y_real, y_pred)),
        'rmse': float(np.sqrt(mean_squared_error(y_real, y_pred))),
        'mae': float(mean_absolute_error(y_real, y_pred)),
        'mape': float(np.mean(np.abs((y_real - y_pred) / y_real))),
    }
    logger.info(
        f'  {etiqueta:<6} n={m["n"]:<5} R²={m["r2"]:.4f}  '
        f'RMSE=${m["rmse"]:>10,.0f}  MAE=${m["mae"]:>10,.0f}  MAPE={m["mape"]:.1%}'
    )
    return m


def entrenar(retune: bool = False, regenerar_contrato: bool = True) -> dict:
    """Ejecuta el pipeline completo y devuelve el resumen de métricas."""
    inicio = time.time()

    logger.info('=' * 68)
    logger.info('🏠 ENTRENAMIENTO DEL MODELO DE AMES HOUSING')
    logger.info('=' * 68)
    logger.info(f'  scikit-learn : {sklearn.__version__}')
    logger.info(f'  pandas       : {pd.__version__}')
    logger.info(f'  numpy        : {np.__version__}')

    # ------------------------------------------------------------------
    # 1. Preprocesado (reutiliza el pipeline del proyecto)
    # ------------------------------------------------------------------
    df_raw = load_data(str(RAW_TRAIN))
    resultado = process_data(
        df=df_raw,
        target_col='SalePrice',
        handle_outliers_flag=True,
        encode_categorical=True,
        scale=True,
        test_size=0.2,
        random_state=42,
    )

    X_train = resultado['X_train']
    X_test = resultado['X_test']
    y_train = resultado['y_train']
    y_test = resultado['y_test']
    scaler = resultado['scaler']

    logger.info(f'\n  X_train={X_train.shape}  X_test={X_test.shape}')

    # ------------------------------------------------------------------
    # 2. Entrenamiento
    # ------------------------------------------------------------------
    if retune:
        logger.info('\n🔧 Re-ejecutando GridSearchCV (puede tardar varios minutos)...')
        busqueda = GridSearchCV(
            RandomForestRegressor(random_state=42, n_jobs=-1),
            PARAM_GRID, cv=5, scoring='r2', n_jobs=-1, verbose=1,
        )
        busqueda.fit(X_train, y_train)
        modelo = busqueda.best_estimator_
        logger.info(f'  Mejores parámetros: {busqueda.best_params_}')
        logger.info(f'  Mejor R² de validación cruzada: {busqueda.best_score_:.4f}')
    else:
        logger.info(f'\n🌲 Entrenando RandomForest con los parámetros ajustados...')
        logger.info(f'  {PARAMS_POR_DEFECTO}')
        modelo = RandomForestRegressor(**PARAMS_POR_DEFECTO)
        modelo.fit(X_train, y_train)

    # ------------------------------------------------------------------
    # 3. Métricas
    # ------------------------------------------------------------------
    logger.info('\n📊 MÉTRICAS')
    metricas = [
        _metricas(y_train, modelo.predict(X_train), 'train'),
        _metricas(y_test, modelo.predict(X_test), 'test'),
    ]

    # ------------------------------------------------------------------
    # 4. Guardar artefactos
    # ------------------------------------------------------------------
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Duplicado con distinto uso de mayúsculas: en Windows conviven como dos
    # ficheros de 18 MB byte a byte idénticos. Tras regenerar dejarían de serlo,
    # así que se avisa (y se retira si existe).
    duplicado = MODELS_DIR / 'random_forest_tuned.pkl'
    if duplicado.exists() and duplicado.resolve() != MODEL_PATH.resolve():
        duplicado.unlink()
        logger.info(f'  🗑️  Eliminado el duplicado obsoleto {duplicado.name}')

    # Datos procesados + scaler + nombres de features (mismo código que antes,
    # para que data/processed y models_saved sigan siendo consistentes).
    save_processed_data(X_train, X_test, y_train, y_test, scaler)

    joblib.dump(modelo, MODEL_PATH)
    logger.info(f'\n💾 Modelo guardado en {MODEL_PATH.relative_to(PROJECT_ROOT)}')

    importancias = (
        pd.DataFrame({
            'Feature': X_train.columns,
            'Importance': modelo.feature_importances_,
        })
        .sort_values('Importance', ascending=False)
        .reset_index(drop=True)
    )
    importancias.to_csv(IMPORTANCE_PATH, index=False)
    logger.info(f'💾 Importancias guardadas en {IMPORTANCE_PATH.relative_to(PROJECT_ROOT)}')
    logger.info('\n  Top 10 características:')
    for i, fila in importancias.head(10).iterrows():
        logger.info(f'   {i + 1:2d}. {fila["Feature"]:<22} {fila["Importance"]:.4f}')

    # ------------------------------------------------------------------
    # 5. Regenerar el contrato de características y autocomprobar
    # ------------------------------------------------------------------
    contrato_ok = None
    if regenerar_contrato:
        from src.data.feature_contract import build_contract, save_contract
        from src.data.model_row import self_check

        logger.info('\n📋 Regenerando el contrato de características...')
        contrato = build_contract()
        save_contract(contrato)
        logger.info('   models_saved/feature_contract.json actualizado')

        comprobacion = self_check(contrato, modelo, scaler)
        contrato_ok = comprobacion['ok']
        n_features = len(contrato['feature_order'])
        if comprobacion['ok']:
            logger.info(
                f'   ✅ Autocomprobación OK ({comprobacion["no_cero"]}/{n_features} '
                f'características no nulas, todo dentro de rango)'
            )
        else:
            logger.error(f'   ❌ Autocomprobación FALLIDA: {comprobacion["problemas"]}')

    duracion = time.time() - inicio
    logger.info('\n' + '=' * 68)
    logger.info(f'✅ ENTRENAMIENTO COMPLETADO en {duracion:.1f}s')
    logger.info('=' * 68)

    return {
        'metricas': metricas,
        'n_features': int(X_train.shape[1]),
        'n_estimators': int(modelo.n_estimators),
        'duracion_segundos': round(duracion, 2),
        'contrato_autocomprobado': contrato_ok,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retune', action='store_true',
                        help='volver a ejecutar GridSearchCV en vez de usar los parámetros ajustados')
    parser.add_argument('--no-contract', dest='no_contract', action='store_true',
                        help='no regenerar models_saved/feature_contract.json')
    argumentos = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    resumen = entrenar(
        retune=argumentos.retune,
        regenerar_contrato=not argumentos.no_contract,
    )
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
