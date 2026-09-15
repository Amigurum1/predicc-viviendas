# src/data/make_dataset.py
"""
Script para generar el dataset procesado de Ames Housing
Se ejecuta: python src/data/make_dataset.py
"""

import sys
from pathlib import Path

# Añadir raíz del proyecto al path para importaciones
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import joblib
import logging
from pathlib import Path

# Importar el pipeline de preprocesamiento
from src.data.preprocess import process_data

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_data(filepath: str) -> pd.DataFrame:
    """
    Carga los datos desde CSV
    """
    logger.info(f"📂 Cargando datos desde {filepath}...")
    df = pd.read_csv(filepath)
    logger.info(f"✅ Cargados {len(df)} registros con {len(df.columns)} columnas")
    return df


def save_processed_data(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    scaler: object,
    output_dir: str = 'data/processed/'
):
    """
    Guarda todos los archivos procesados
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path('models_saved').mkdir(parents=True, exist_ok=True)
    
    # Guardar datos
    X_train.to_csv(f'{output_dir}/X_train.csv', index=False)
    X_test.to_csv(f'{output_dir}/X_test.csv', index=False)
    y_train.to_csv(f'{output_dir}/y_train.csv', index=False)
    y_test.to_csv(f'{output_dir}/y_test.csv', index=False)
    
    # Guardar scaler
    if scaler is not None:
        joblib.dump(scaler, 'models_saved/scaler.pkl')
        logger.info("✅ Scaler guardado en models_saved/scaler.pkl")
    
    # Guardar nombres de features (útil para la API)
    feature_names = X_train.columns.tolist()
    with open('models_saved/feature_names.txt', 'w') as f:
        f.write('\n'.join(feature_names))
    
    logger.info(f"✅ Datos guardados en {output_dir}")
    logger.info(f"✅ {len(feature_names)} features guardadas en models_saved/feature_names.txt")


def main():
    """
    Función principal - Orquesta todo el pipeline
    """
    logger.info("="*60)
    logger.info("🏠 PIPELINE DE DATOS - AMES HOUSING")
    logger.info("="*60)
    
    # 1. Cargar datos
    df_raw = load_data('data/raw/train.csv')
    
    # 2. Ejecutar pipeline de preprocesamiento
    result = process_data(
        df=df_raw,
        target_col='SalePrice',
        handle_outliers_flag=True,
        encode_categorical=True,
        scale=True,
        test_size=0.2,
        random_state=42
    )
    
    # 3. Extraer resultados
    X_train = result['X_train']
    X_test = result['X_test']
    y_train = result['y_train']
    y_test = result['y_test']
    scaler = result['scaler']
    feature_names = result['feature_names']
    
    # 4. Guardar datos procesados
    save_processed_data(X_train, X_test, y_train, y_test, scaler)
    
    # 5. Resumen final
    logger.info("\n" + "="*60)
    logger.info("🎯 RESUMEN FINAL DEL PIPELINE:")
    logger.info(f"  - Train shape: {X_train.shape}")
    logger.info(f"  - Test shape: {X_test.shape}")
    logger.info(f"  - Features: {len(feature_names)}")
    logger.info(f"  - Target: SalePrice")
    logger.info(f"  - Precio medio train: ${y_train.mean():,.2f}")
    logger.info(f"  - Precio medio test: ${y_test.mean():,.2f}")
    logger.info("="*60)
    logger.info("✅ PIPELINE COMPLETADO EXITOSAMENTE!")


if __name__ == "__main__":
    main()