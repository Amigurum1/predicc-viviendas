"""
Experimento: ¿mejora el modelo si se quita la interacción `LivArea_Qual`?

CONTEXTO
--------
El modelo desplegado da a `LivArea_Qual` (= GrLivArea × OverallQual) un 62 % de
la importancia, y a los 24 barrios solo un 0,5 %. La consecuencia práctica es que
cambiar de barrio apenas mueve el precio: para la vivienda mediana, varios
barrios dan exactamente el mismo resultado.

La hipótesis es que esa única interacción absorbe casi toda la señal y deja al
barrio sin margen. Este script entrena la misma configuración con y sin ella y
compara, para decidir con datos en vez de por intuición.

Uso:
    python scripts/experiment_without_feature.py
"""

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, 'reconfigure'):
        try:
            _flujo.reconfigure(encoding='utf-8')
        except Exception:
            pass

from src.data.preprocess import process_data  # noqa: E402

# Los mismos hiperparámetros que el modelo desplegado, para que la única
# diferencia entre las dos variantes sea la característica eliminada.
PARAMS = {
    'n_estimators': 200,
    'max_depth': 15,
    'min_samples_split': 2,
    'min_samples_leaf': 1,
    'random_state': 42,
    'n_jobs': -1,
}

FEATURE_A_QUITAR = 'LivArea_Qual'


def metricas(y_real, y_pred, etiqueta):
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        'conjunto': etiqueta,
        'r2': r2_score(y_real, y_pred),
        'rmse': float(np.sqrt(mean_squared_error(y_real, y_pred))),
        'mae': float(mean_absolute_error(y_real, y_pred)),
        'mape': float(np.mean(np.abs((y_real - y_pred) / y_real))),
    }


def influencia_del_barrio(modelo, x_train, columnas):
    """
    Cuánto se mueve el precio al cambiar SOLO el barrio, partiendo de la vivienda
    mediana del conjunto de entrenamiento.

    Devuelve (número de precios distintos, diferencia entre el máximo y el mínimo).
    """
    barrios = [c for c in columnas if c.startswith('Neighborhood_')]
    if not barrios:
        return 0, 0.0

    fila = x_train.median().to_frame().T
    base = fila.copy()
    # La mediana de los dummies no es 0/1: hay que dejar el barrio base (todo 0)
    for col in barrios:
        base[col] = 0.0

    precios = []
    for col in barrios:
        variante = base.copy()
        variante[col] = 1.0
        precios.append(float(modelo.predict(variante[columnas])[0]))

    return len(set(round(p, 2) for p in precios)), max(precios) - min(precios)


def entrenar_variante(X_train, X_test, y_train, y_test, quitar=None):
    columnas = [c for c in X_train.columns if c != quitar] if quitar else list(X_train.columns)

    modelo = RandomForestRegressor(**PARAMS)
    modelo.fit(X_train[columnas], y_train)

    met = [
        metricas(y_train, modelo.predict(X_train[columnas]), 'train'),
        metricas(y_test, modelo.predict(X_test[columnas]), 'test'),
    ]

    importancias = pd.Series(modelo.feature_importances_, index=columnas)
    total_barrios = float(importancias[[c for c in columnas
                                        if c.startswith('Neighborhood_')]].sum())
    distintos, rango = influencia_del_barrio(modelo, X_train, columnas)

    return {
        'etiqueta': f'sin {quitar}' if quitar else 'modelo actual',
        'n_features': len(columnas),
        'metricas': met,
        'importancia_barrios': total_barrios,
        'importancia_maxima': float(importancias.max()),
        'feature_dominante': str(importancias.idxmax()),
        'barrios_distintos': distintos,
        'rango_barrio': rango,
    }


def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
    warnings.simplefilter('ignore', UserWarning)

    print('=' * 76)
    print('EXPERIMENTO: QUITAR LivArea_Qual')
    print('=' * 76)

    import pandas as pd  # noqa: F811
    df = pd.read_csv(PROJECT_ROOT / 'data' / 'raw' / 'train.csv')
    r = process_data(df, target_col='SalePrice', handle_outliers_flag=True,
                     encode_categorical=True, scale=True, test_size=0.2, random_state=42)
    X_train, X_test = r['X_train'], r['X_test']
    y_train, y_test = r['y_train'], r['y_test']

    print(f'  Train: {X_train.shape}   Test: {X_test.shape}')
    print(f'  Característica a quitar: {FEATURE_A_QUITAR}\n')

    resultados = [
        entrenar_variante(X_train, X_test, y_train, y_test),
        entrenar_variante(X_train, X_test, y_train, y_test, quitar=FEATURE_A_QUITAR),
    ]

    # --- Tabla comparativa ---
    print('-' * 76)
    print(f"{'variante':<22}{'nº feat':>9}{'R² test':>10}{'RMSE test':>12}{'MAPE test':>11}")
    print('-' * 76)
    for res in resultados:
        test = res['metricas'][1]
        print(f"{res['etiqueta']:<22}{res['n_features']:>9}{test['r2']:>10.4f}"
              f"{test['rmse']:>12,.0f}{test['mape']:>10.1%}")
    print('-' * 76)

    print()
    print('-' * 76)
    print(f"{'variante':<22}{'peso barrios':>14}{'feature top':>26}{'su peso':>9}")
    print('-' * 76)
    for res in resultados:
        print(f"{res['etiqueta']:<22}{res['importancia_barrios']:>13.4f}  "
              f"{res['feature_dominante']:>24}{res['importancia_maxima']:>9.4f}")
    print('-' * 76)

    print()
    print('-' * 76)
    print(f"{'variante':<22}{'barrios distintos':>20}{'rango de precio':>18}")
    print('-' * 76)
    for res in resultados:
        print(f"{res['etiqueta']:<22}{res['barrios_distintos']:>20}"
              f"{res['rango_barrio']:>17,.0f}")
    print('-' * 76)

    # --- Conclusión ---
    base, variante = resultados
    r2_base, r2_var = base['metricas'][1]['r2'], variante['metricas'][1]['r2']
    mape_base, mape_var = base['metricas'][1]['mape'], variante['metricas'][1]['mape']

    print()
    print('CONCLUSIÓN')
    print('-' * 76)
    print(f'  R² test   : {r2_base:.4f} -> {r2_var:.4f}  ({r2_var - r2_base:+.4f})')
    print(f'  MAPE test : {mape_base:.1%} -> {mape_var:.1%}  ({mape_var - mape_base:+.1%})')
    print(f'  Peso de los barrios: {base["importancia_barrios"]:.4f} -> '
          f'{variante["importancia_barrios"]:.4f}')
    print(f'  Barrios que dan un precio distinto: {base["barrios_distintos"]} -> '
          f'{variante["barrios_distintos"]}')

    mejora_precision = r2_var > r2_base + 0.005
    mejora_barrio = variante['importancia_barrios'] > base['importancia_barrios'] * 2

    if mejora_precision:
        print('\n  ✅ La variante predice MEJOR: merece la pena adoptarla.')
    elif mejora_barrio:
        print('\n  ⚠️  La variante NO predice mejor, pero el barrio gana peso.')
        print('      Es un intercambio: se pierde precisión a cambio de que el')
        print('      barrio influya. Decisión de producto, no técnica.')
    else:
        print('\n  ❌ Quitar LivArea_Qual NO mejora la precisión ni le da peso al')
        print('      barrio. Se descarta: el modelo actual se queda como está.')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
