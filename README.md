# Predictor de precios de viviendas — Ames Housing

Aplicación web completa que predice el precio de una vivienda con Machine
Learning: modelo entrenado, API REST con autenticación JWT, base de datos,
historial, estadísticas e interfaz visual con mapas y gráficos.

---

## ⚠️ Qué predice exactamente (léelo antes de nada)

El modelo está entrenado con **Ames Housing**, un dataset público de **Ames,
Iowa (Estados Unidos)**. En consecuencia:

- **Los precios están en dólares (USD), no en soles.**
- **Los "barrios" son barrios de Ames** (`NridgHt`, `CollgCr`, `OldTown`…), no
  distritos de Lima.
- No es un predictor del mercado inmobiliario peruano. Es una aplicación
  completa y honesta construida sobre un dataset estadounidense.

Se decidió así de forma deliberada: la alternativa era un modelo de Iowa
etiquetado como Lima, con distritos que el modelo ignoraba por completo. Aquí
todo lo que se muestra se corresponde con lo que el modelo realmente hace.

---

## Arquitectura

```
  Navegador  http://localhost:5500
      │
      ▼
  Frontend (HTML + CSS + JS)          nginx
  ├── Formulario de 9 campos (opciones cargadas de la API)
  ├── Mapa Leaflet centrado en Ames
  ├── Historial y dashboard con Chart.js
  └── Exportación a PDF
      │  HTTP + JWT
      ▼
  API REST (FastAPI)                  http://localhost:8000
  ├── /api/auth          registro, login, refresh, perfil
  ├── /api/predictions   predicción, historial, estadísticas, opciones
  ├── /api/products      CRUD de propiedades
  ├── /api/orders, /api/reviews, /api/categories, /api/users
  └── Middlewares: CORS, logging, límite de peticiones
      │
      ▼
  Capa de Machine Learning
  ├── models_saved/feature_contract.json   ← qué campos y en qué rango
  ├── src/data/model_row.py                ← construye la fila del modelo
  ├── models_saved/scaler.pkl              ← escalado (23 columnas)
  └── models_saved/RandomForest_Tuned.pkl  ← 200 árboles
      │
      ▼
  Base de datos (SQLite en desarrollo, PostgreSQL en producción)
```

---

## Puesta en marcha

### Con Docker (recomendado)

```bash
docker compose up -d --build
```

- Interfaz: <http://localhost:5500>
- API y documentación interactiva: <http://localhost:8000/docs>

La base de datos vive en el volumen `predicc_viviendas_predicc_db`, así que
sobrevive a los `--build`.

### En local

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate          # Linux/macOS

pip install -r requirements-dev.txt   # incluye las de runtime

copy .env.example .env                # y edita SECRET_KEY
python -m uvicorn main:app --reload
```

En otra terminal, sirve el frontend (por ejemplo `python -m http.server 5500`
desde `frontend/`) o usa cualquier servidor estático.

> **Entorno canónico:** `requirements.txt` fija las versiones exactas
> (`scikit-learn==1.5.0`, `sqlalchemy==2.0.23`…). Son las que usa Docker y con
> las que se generaron los artefactos de `models_saved/`. Si instalas otras
> versiones, scikit-learn avisará de que el modelo se serializó con otra versión.
> Comprueba el estado con `python scripts/check_artifacts.py`.

---

## El modelo

| | |
|---|---|
| Algoritmo | Random Forest (200 árboles, `max_depth=15`) |
| Dataset | Ames Housing: 1.460 viviendas, 81 columnas |
| Características de entrada | 9 (el resto se completan con la vivienda mediana) |
| Características del modelo | 212 columnas tras codificación y ingeniería |
| Precio mediano del dataset | $163.000 |

### Métricas reales

| Conjunto | n | R² | RMSE | MAE | MAPE |
|---|---|---|---|---|---|
| Entrenamiento | 1.114 | 0,9856 | $8.387 | $5.662 | 3,5 % |
| **Test** | **292** | **0,8607** | **$32.687** | **$17.417** | **10,1 %** |

> Estas cifras son **peores** que las que había antes, y es una buena noticia:
> el pipeline anterior escalaba los datos antes de dividir train/test, lo que
> filtraba información del conjunto de test (fuga de datos) y daba un R² de
> 0,8984 que no era real. Corregido en `src/data/preprocess.py`.

### Reentrenar

```bash
python src/models/train_model.py            # usa los hiperparámetros ya ajustados
python src/models/train_model.py --retune   # vuelve a ejecutar GridSearchCV
```

Regenera el modelo, el escalador, los nombres de características, las
importancias, `data/processed/` y el contrato de características.

### Qué es el contrato de características

`models_saved/feature_contract.json` describe cómo se construye la fila que
recibe el modelo: la vivienda mediana de referencia, las columnas one-hot y su
categoría base, los rangos válidos y las etiquetas de barrios y tipos.

Existe porque la versión anterior construía el vector a mano y se equivocaba en
tres cosas a la vez: escalaba 213 columnas con un escalador de 23, dejaba 12
características derivadas a 0 en vez de calcularlas y enviaba valores inválidos
(`YrSold = 0`, `MSSubClass = 0`). Ahora la fila se construye reutilizando
literalmente las mismas funciones que el entrenamiento
(`src/data/model_row.py` → `src/data/preprocess.py`), así que no puede divergir.

---

## API

Documentación interactiva completa en `/docs`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/register` | Crear cuenta |
| POST | `/api/auth/login` | Iniciar sesión (devuelve access + refresh) |
| POST | `/api/auth/refresh` | Renovar tokens |
| GET/PUT | `/api/auth/me` | Ver / actualizar el perfil propio |
| POST | `/api/auth/change-password` | Cambiar contraseña |
| GET | `/api/predictions/options` | Barrios y tipos disponibles (público) |
| POST | `/api/predictions/` | Predecir el precio |
| GET | `/api/predictions/history` | Historial paginado |
| GET | `/api/predictions/stats/me` | Estadísticas propias |
| GET | `/api/predictions/info/model` | Información del modelo cargado |
| GET | `/health` | Estado de la API y de la base de datos |

Las rutas sensibles (`/api/auth/*` y los `POST` de `/api/predictions/`) tienen un
límite de peticiones configurable (100 por minuto y por IP, con respuesta 429 y
cabecera `Retry-After`). Las de solo lectura no lo tienen, para no estorbar al
propio frontend.

Ejemplo de predicción:

```bash
curl -X POST http://localhost:8000/api/predictions/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"neighborhood":"NridgHt","ms_subclass":60,"gr_liv_area_m2":200,
       "lot_area_m2":1000,"overall_qual":8,"year_built":1995,
       "bedrooms":4,"bathrooms":2,"garage_cars":3}'
```

---

## Pruebas

```bash
python -m pytest                      # 224 pruebas
```

En el entorno canónico (mismas versiones que producción):

```bash
docker build -f Dockerfile.dev -t predicc_viviendas-dev .
docker run --rm -v "$PWD:/app" -w /app predicc_viviendas-dev python -m pytest
```

Las pruebas cubren autenticación y permisos, el contrato de características, la
consistencia train/serve, la paginación, el aislamiento de datos entre usuarios,
la política de contraseñas, el límite de peticiones y la coherencia entre el
HTML y el JavaScript del frontend.

### Integración continua

`.github/workflows/ci.yml` se ejecuta en cada `push` a `main`, en cada pull
request y a mano (`workflow_dispatch`). Hace, en este orden:

1. Instala `requirements-dev.txt` sobre Python 3.12 en una máquina limpia.
2. Regenera los artefactos: `python src/models/train_model.py`.
3. Comprueba artefactos y contrato: `python scripts/check_artifacts.py`.
4. Lanza la suite: `python -m pytest`.

El entrenamiento va **antes** de las pruebas a propósito. Los `.pkl` de
`models_saved/` no están versionados (son binarios de varios MB), así que en un
clon recién hecho no existen y 13 pruebas fallan al cargar el modelo. Una vez
entrenado, el clon pasa las 224.

El flujo define `ENVIRONMENT=testing` y una `SECRET_KEY` de usar y tirar: el
`.env` real no se versiona, y con los valores por defecto la configuración
avisaría de un secreto de ejemplo.

Lo que la CI **no** comprueba: el frontend en un navegador real (solo hay
comprobaciones estáticas de HTML y JavaScript) ni la imagen Docker.

---

## Estructura

```
├── .github/workflows/        CI (pruebas en cada push y pull request)
├── api/                      API REST
│   ├── config.py             configuración por entorno
│   ├── database.py           conexión y ciclo de vida de la base de datos
│   ├── models.py             modelos SQLAlchemy
│   ├── schemas.py            esquemas Pydantic (incluye la política de contraseñas)
│   ├── crud.py               operaciones de base de datos
│   ├── auth.py               JWT, permisos y contraseñas
│   ├── feature_mapper.py     adaptador: formulario -> campos del dataset
│   └── routers/              endpoints por recurso
├── src/
│   ├── data/
│   │   ├── preprocess.py         limpieza e ingeniería de características
│   │   ├── feature_contract.py   genera el contrato desde el dataset
│   │   ├── model_row.py          construye la fila del modelo (inferencia)
│   │   └── make_dataset.py       genera data/processed/
│   └── models/train_model.py     entrenamiento reproducible
├── frontend/                 HTML + CSS + JS
├── notebooks/                EDA y entrenamiento exploratorio
├── scripts/                  utilidades (diagnóstico, migración de la BD)
├── tests/                    suite de pruebas
├── models_saved/             artefactos del modelo
└── data/                     datos crudos y procesados
```

---

## Limitaciones conocidas

- **El barrio apenas influye.** La interacción `GrLivArea × OverallQual` se lleva
  el 62 % de la importancia del modelo, y los 24 barrios suman un 0,5 %. Para la
  vivienda mediana, de los 24 barrios solo 16 dan un precio distinto, y el rango
  entre el más barato y el más caro es de unos $2.900 (1,8 % de la mediana).
  Está fijado en las pruebas para que no pase inadvertido.

  Se comprobó que **no es culpa de esa interacción**: quitándola el modelo
  empeora (R² test 0,8607 → 0,8494; MAPE 10,1 % → 10,4 %) y el barrio ni siquiera
  gana peso (0,0047 → 0,0038), porque su importancia se traslada a `TotalSF`. Es
  una propiedad del dataset: una vez que se conoce el tamaño, la calidad y la
  antigüedad de la vivienda, el barrio aporta poco. Reproducible con
  `python scripts/experiment_without_feature.py`.
- **Precisión del 10 % (MAPE)** describiendo la vivienda solo con 9 campos; el
  resto de características se asumen iguales a la vivienda mediana.
- **No hay subida de archivos**: ni endpoints ni configuración (se retiró por ser
  código muerto).
- **Sin envío de correo.** Dos consecuencias:
  - el flujo de "he olvidado mi contraseña" genera el token, pero en producción no
    se envía (en desarrollo se devuelve en la respuesta para poder probarlo);
  - **no hay verificación de email**: los usuarios se crean directamente como
    activos. El campo `is_verified` de la tabla se conserva como reservado, pero
    hoy siempre es `false`. El andamiaje a medias que existía (token, endpoint
    `/verify-email`, dependencia `get_current_verified_user`) se retiró para no
    aparentar una función que no se puede completar.
- **El límite de peticiones es en memoria**, por proceso. Con varios workers o
  en un despliegue real hace falta Redis.
- **Sin migraciones de base de datos.** `alembic` estaba declarado pero no había
  ni configuración ni migraciones, así que se retiró. Hoy el esquema se crea con
  `create_all()` al arrancar; para evolucionarlo sin perder datos habría que
  añadir migraciones.

---

## Seguridad

- Contraseñas con bcrypt y política única (8+, mayúscula, minúscula, número y
  carácter especial) aplicada en registro, cambio y reseteo.
- Tokens JWT con `jti` y rotación del refresh token.
- **El rol solo lo cambia un administrador**: los esquemas de entrada no aceptan
  `role`, `status`, `is_active` ni `is_verified`.
- Las contraseñas viajan en el cuerpo de la petición, nunca en la URL.
- En producción, una `SECRET_KEY` débil o de ejemplo **impide el arranque**.

## Licencia

Proyecto con fines educativos y de portafolio. El dataset Ames Housing es de
dominio público (Dean De Cock, 2011).
