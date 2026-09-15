"""
Recrea la tabla `predictions` con el nuevo esquema (bloque 2).

CONTEXTO
--------
La tabla antigua guardaba los campos del formulario antiguo (square_meters,
years_old, distance_to_center, has_parking, property_type, district...). El
formulario nuevo tiene 9 campos distintos (neighborhood, ms_subclass,
gr_liv_area_m2, lot_area_m2, overall_qual, year_built, bedrooms, bathrooms,
garage_cars), así que las columnas no coinciden y las 18 filas antiguas no son
recuperables: se generaron con un modelo que ignoraba el distrito y sin el
scaler aplicado.

QUÉ HACE
--------
1. Hace una copia de seguridad del fichero SQLite (por defecto app.db).
2. Elimina SOLO la tabla `predictions`.
3. La vuelve a crear con el esquema nuevo.
4. No toca `users`, `products`, `orders`, `reviews`, `categories` ni `order_items`.

Uso:
    python scripts/reset_predictions_table.py            # pide confirmación
    python scripts/reset_predictions_table.py --yes      # sin preguntar
    python scripts/reset_predictions_table.py --dry-run  # solo muestra el estado
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

# La consola de Windows usa cp1252 por defecto y no puede imprimir emojis ni
# acentos raros. Se fuerza UTF-8 en la salida.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, 'reconfigure'):
        try:
            _flujo.reconfigure(encoding='utf-8')
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect  # noqa: E402

from api.config import config  # noqa: E402
# Import necesario por EFECTO SECUNDARIO: registra los modelos en Base.metadata.
# Sin esta línea, Base.metadata.tables está vacío y el script falla con KeyError.
from api import models  # noqa: E402,F401
from api.database import Base, engine  # noqa: E402


TABLA = 'predictions'


def _estado() -> dict:
    """Filas actuales de cada tabla (para poder informar antes y después)."""
    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())
    conteo = {}
    if TABLA in existentes:
        with engine.connect() as conn:
            conteo[TABLA] = conn.exec_driver_sql(f'SELECT COUNT(*) FROM {TABLA}').scalar()
    return {
        'tablas': sorted(existentes),
        'tabla_existe': TABLA in existentes,
        'filas': conteo.get(TABLA),
    }


def _ruta_sqlite() -> Path | None:
    """Ruta del fichero SQLite, si la base de datos es SQLite."""
    url = config.get_database_url()
    if not url.startswith('sqlite'):
        return None
    fichero = url.split('sqlite:///')[-1].split('?')[0]
    return (PROJECT_ROOT / fichero).resolve() if fichero else None


def _backup(ruta: Path) -> Path:
    marca = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = ruta.with_name(f'{ruta.stem}.backup_{marca}{ruta.suffix}')
    shutil.copyfile(ruta, destino)
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yes', action='store_true', help='no pedir confirmación')
    parser.add_argument('--dry-run', action='store_true',
                        help='solo mostrar el estado actual, sin cambiar nada')
    args = parser.parse_args()

    print('=' * 68)
    print('RECREAR LA TABLA `predictions`')
    print('=' * 68)
    print(f'  Base de datos : {config.get_database_url()}')

    ruta = _ruta_sqlite()
    antes = _estado()
    print(f'  Tablas        : {", ".join(antes["tablas"])}')
    print(f'  Filas en {TABLA}: {antes["filas"] if antes["tabla_existe"] else "(la tabla no existe)"}')

    if args.dry_run:
        print('\n--dry-run: no se ha modificado nada.')
        return 0

    if not args.yes:
        print(f'\nSe van a eliminar las filas de `{TABLA}` y recrear la tabla.')
        print('Las tablas users, products, orders, reviews, categories y')
        print('order_items NO se tocan.')
        respuesta = input('\n¿Continuar? [s/N]: ').strip().lower()
        if respuesta not in ('s', 'si', 'sí', 'y', 'yes'):
            print('Cancelado.')
            return 1

    if ruta and ruta.exists():
        copia = _backup(ruta)
        print(f'\n💾 Copia de seguridad: {copia.name}')

    print(f'\n🗑️  Eliminando la tabla `{TABLA}`...')
    Base.metadata.tables[TABLA].drop(bind=engine, checkfirst=True)

    print('🔨 Recreando con el esquema nuevo...')
    Base.metadata.tables[TABLA].create(bind=engine, checkfirst=True)

    despues = _estado()
    columnas = [c['name'] for c in inspect(engine).get_columns(TABLA)]
    print(f'  Columnas nuevas: {", ".join(columnas)}')
    print(f'  Tablas         : {", ".join(despues["tablas"])}')

    print('\n' + '=' * 68)
    print(f'✅ Tabla `{TABLA}` recreada con 0 filas.')
    print('   Los usuarios y productos existentes siguen intactos.')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
