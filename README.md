# Predictor de precios de viviendas — Ames Housing

[![CI](https://github.com/Amigurum1/predicc-viviendas/actions/workflows/ci.yml/badge.svg)](https://github.com/Amigurum1/predicc-viviendas/actions/workflows/ci.yml)

Aplicación web completa que estima el precio de una vivienda con Machine
Learning: un Random Forest entrenado sobre el dataset Ames Housing, servido por
una API REST con autenticación JWT, con base de datos, historial, estadísticas e
interfaz visual con mapa y gráficos.

El interés del proyecto está en la **fase predictiva**: convertir la descripción
de una casa en un precio. Todo ese camino —los datos, la ingeniería de
características, el modelo, las métricas y el contrato de entrada que impide que
el entrenamiento y la inferencia se desincronicen— está documentado en detalle
más abajo, y se reproduce con un solo comando.

---

## ⚠️ Qué predice exactamente (léelo antes de nada)

El modelo está entrenado con **Ames Housing**, un dataset público de **Ames,
Iowa (Estados Unidos)**. En consecuencia:

- **Los precios están en dólares (USD), no en soles.**
- **Los "barrios" son barrios de Ames** (`NridgHt`, `CollgCr`, `OldTown`…), no
  distritos de Lima.
- No es un predictor del mercado inmobiliario peruano: son ventas reales de una
  ciudad universitaria de Iowa entre 2006 y 2010.

Todo lo que se muestra en la interfaz se corresponde con lo que el modelo
realmente hace: los barrios son los de Ames, la moneda es el dólar y las
métricas son las que aparecen en este documento.

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

## La fase predictiva

Es la parte central del proyecto: **de la descripción de una casa a un precio**.
El recorrido completo va de las 81 columnas del CSV a un único número en dólares,
y cada decisión de ese recorrido está tomada por una razón que se puede
comprobar.

### 1. Los datos

| | |
|---|---|
| Dataset | Ames Housing (Dean De Cock, 2011) |
| Viviendas | 1.460 |
| Columnas originales | 81 (79 explicativas, `Id` y `SalePrice`) |
| Variable objetivo | `SalePrice` (USD) |
| Precio mínimo | $34.900 |
| Precio mediano | $163.000 |
| Precio medio | $180.921 |
| Precio máximo | $755.000 |

Cada fila describe una venta real: superficie habitable, sótano, garaje,
porches, calidad de los materiales, año de construcción y de reforma, barrio,
tipo de vivienda, servicios… Es un dataset pequeño (1.460 filas) y muy limpio,
lo que permite entrenar en segundos y dedicar el esfuerzo al pipeline en lugar
de a la infraestructura.

### 2. De 81 columnas a 212 características

El modelo no ve el CSV: ve una matriz de **212 columnas numéricas**. Estos son
los pasos, en este orden exacto, tal y como están en `src/data/preprocess.py`.

**1. Columnas que se descartan.** `Id` (un identificador no dice nada del
precio) y las cuatro columnas más vacías del dataset: `PoolQC` (99,5 % de
valores ausentes), `MiscFeature` (96,3 %), `Alley` (93,8 %) y `Fence` (80,8 %).
Casi ninguna casa de Ames tiene piscina, callejón o valla, así que en esas
columnas hay más ruido que señal.

**2. Valores ausentes.** No se rellenan todos igual, porque un nulo no significa
lo mismo en cada columna:

- superficies y años → **mediana**;
- calidad y categorías → **moda**;
- recuentos (baños, dormitorios, chimeneas, plazas de garaje) → **0**, porque un
  nulo ahí significa "no hay", no "no se sabe";
- casos con significado propio: `LotFrontage` → mediana, `MasVnrArea` → 0 (sin
  revestimiento), `BsmtExposure` → `No`, y en el garaje `GarageFinish`/`Qual`/
  `Cond` → los valores que corresponden a "sin garaje".

En total, 19 de las 81 columnas traen algún nulo y todas quedan cubiertas.

**3. Ordinales a números.** Las calidades de Ames vienen como texto (`Po`, `Fa`,
`TA`, `Gd`, `Ex`) y tienen un orden real. Se convierten a 1-5, `BsmtFinType1/2` a
1-6 y `BsmtExposure` a 0-3, para que el modelo pueda aprovechar ese orden en vez
de tratarlas como categorías independientes.

**4. Fechas → edades.** `YearBuilt`, `YearRemodAdd` y `GarageYrBlt` se convierten
en `HouseAge`, `YearsSinceRemodel` y `GarageAge` restando el año de venta
(`YrSold`, que en el dataset va de 2006 a 2010), y se añade `IsRemodeled`. Para
un modelo de precios, "36 años" es una magnitud comparable entre casas; "1972"
no lo es.

**5. Interacciones.** El precio no es "metros más calidad": una casa grande y mal
acabada no vale lo mismo que una pequeña y bien acabada. Se construyen productos
que capturan esa idea:

| Característica | Fórmula |
|---|---|
| `LivArea_Qual` | `GrLivArea` × `OverallQual` |
| `Bsmt_Qual` | `TotalBsmtSF` × `OverallQual` |
| `TotalSF` | `GrLivArea` + `TotalBsmtSF` |
| `Qual_Cond` | `OverallQual` × `OverallCond` |
| `Age_Qual` | `HouseAge` × `OverallQual` |
| `TotalPorchSF` | suma de los tres tipos de porche |

`LivArea_Qual` acaba siendo **la característica más importante del modelo**: se
lleva el 62 % de la importancia total (ver la tabla más abajo).

**6. Cuadrados.** `GrLivArea_sq`, `OverallQual_sq`, `TotalBsmtSF_sq` y
`HouseAge_sq`. La relación entre superficie y precio no es lineal —el último
metro cuadrado de una casa de 300 m² no vale lo mismo que el de una de 80— y
estos términos se la dan ya construida al modelo. `OverallQual_sq` pesa por sí
sola un 2,4 %.

**7. La división train/test va ANTES de todo lo que aprende.** Es el punto más
importante del pipeline y es deliberado:

- 1.168 viviendas a entrenamiento y 292 a test (80/20, `random_state=42`);
- los umbrales de outliers, las categorías del one-hot y la media y desviación
  del escalado se calculan **solo con entrenamiento**, y después se aplican a
  test.

Si esos parámetros se calcularan con el conjunto completo, el modelo "sabría" de
antemano dónde están los valores extremos del test, qué categorías existen en él
y cuál es su escala, y las métricas de test saldrían más bonitas de lo que son.
Es la fuga de datos clásica, y es fácil de cometer sin notarlo.

**8. Outliers: solo en entrenamiento.** Con el criterio IQR × 2,0 se eliminan 54
de las 1.168 viviendas de entrenamiento y quedan 1.114. Las ventas atípicas
(mansiones de $700.000, casas de $35.000) desvían el ajuste de un modelo que, con
poco más de mil filas, no puede permitirse dedicar capacidad a unos pocos casos
extremos.

En test **no se toca nada**: el conjunto de test tiene que parecerse a lo que el
modelo verá después, extremos incluidos. Si se limpiara también, la métrica
estaría midiendo un problema más fácil que el real.

**9. One-hot encoding.** Las 27 columnas categóricas (barrio, zonificación,
estilo, cimentación, tipo de venta…) se convierten en columnas 0/1. Se elimina
una categoría por columna (`drop_first`) para no duplicar información: esa
categoría queda representada por "todos sus dummies a 0". Las categorías que
aparezcan en test pero no en entrenamiento se alinean a 0 en lugar de crear
columnas que el modelo no conoce.

**10. Escalado.** `StandardScaler` sobre las 23 columnas numéricas continuas
(superficies, años, las interacciones y los cuadrados): media 0 y desviación 1,
ajustado solo con entrenamiento. Los one-hot y las variables binarias no se
escalan, porque no tiene sentido. Un bosque de decisión no necesita escalado para
funcionar, pero el escalador forma parte del pipeline, y lo que importa es que
sea **exactamente el mismo** en entrenamiento y en inferencia.

Resultado: `X_train` de 1.114 × 212 y `X_test` de 292 × 212, ambos en el mismo
espacio.

### 3. El modelo

| | |
|---|---|
| Algoritmo | `RandomForestRegressor` |
| Árboles | 200 |
| Profundidad máxima | 15 |
| `min_samples_split` | 2 |
| `min_samples_leaf` | 1 |
| `random_state` | 42 |
| Tiempo de entrenamiento | ~2,4 s |

**Por qué un bosque aleatorio.** Los datos son tabulares, con relaciones no
lineales e interacciones entre variables, y solo hay 1.114 filas de
entrenamiento. Un bosque promedia 200 árboles entrenados sobre muestras
bootstrap y subconjuntos de variables: eso reduce la varianza de un árbol suelto,
tolera escalas dispares y valores extremos, permite leer la importancia de cada
variable y predice en milisegundos, que es lo que necesita una API.

**De dónde salen los hiperparámetros.** De una búsqueda en rejilla
(`GridSearchCV`, 108 combinaciones × 5 particiones = 540 entrenamientos) que
eligió 200 árboles y profundidad 15. La profundidad importa: sin límite, cada
árbol memoriza el conjunto de entrenamiento y la métrica de test se degrada. La
rejilla está en `src/models/train_model.py` y se puede volver a ejecutar con
`--retune`, que informa de los mejores parámetros y del R² de validación cruzada
obtenido.

### 4. Métricas, y cómo leerlas

| Conjunto | n | R² | RMSE | MAE | MAPE |
|---|---|---|---|---|---|
| Entrenamiento | 1.114 | 0,9856 | $8.387 | $5.662 | 3,5 % |
| **Test** | **292** | **0,8607** | **$32.687** | **$17.417** | **10,1 %** |

Qué significa cada una:

- **R² = 0,8607 en test**: el modelo explica el 86 % de por qué unas casas de
  Ames valen más que otras, comparado con predecir siempre el precio medio.
- **RMSE = $32.687**: error típico penalizando mucho los fallos grandes.
- **MAE = $17.417**: de media, el modelo se equivoca en unos $17.400.
- **MAPE = 10,1 %**: en términos relativos, el error medio es el 10 % del precio
  real. Sobre la vivienda mediana ($163.000), del orden de $16.500.

La diferencia entre entrenamiento (R² 0,9856) y test (0,8607) es el sobreajuste
esperable en un bosque profundo: el modelo reproduce muy bien lo que ha visto y
algo peor lo que no. **La cifra que importa es la de test**, porque es la única
medida sobre viviendas que el modelo no vio durante el entrenamiento.

Estas cifras describen ventas de Ames, no el mercado de ningún otro país.

### 5. Qué ha aprendido el modelo

Importancia de las 10 características principales (más la suma de los barrios):

| Característica | Importancia |
|---|---|
| `LivArea_Qual` (superficie × calidad) | 62,05 % |
| `Bsmt_Qual` (sótano × calidad) | 9,01 % |
| `BsmtQual` (calidad del sótano) | 4,81 % |
| `TotalSF` (superficie total) | 3,56 % |
| `OverallQual_sq` | 2,37 % |
| `BsmtFinSF1` (sótano terminado) | 1,45 % |
| `OverallQual` (calidad general) | 0,95 % |
| `HouseAge_sq` | 0,88 % |
| `YearBuilt` | 0,79 % |
| `GarageArea` | 0,75 % |
| Los 24 dummies de barrio, **juntos** | **0,47 %** |

El modelo es, en esencia, **superficie × calidad**, con el sótano y la edad como
matices. El barrio, que es la variable que más peso tiene en un anuncio
inmobiliario, aquí apenas aporta nada: la información que trae ya está absorbida
por `TotalSF` y `LivArea_Qual`, porque quienes construyeron las casas grandes y
buenas de Ames las construyeron juntas, en los mismos barrios.

Merece la pena comprobarlo con un experimento en lugar de darlo por supuesto:
quitando `LivArea_Qual` del modelo, el R² de test baja de 0,8607 a 0,8494 y el
MAPE sube del 10,1 % al 10,4 %, **y el barrio no gana peso** (0,0047 → 0,0038),
porque su importancia se traslada a `TotalSF`. Es una propiedad del dataset, no
un fallo del pipeline. Se reproduce con
`python scripts/experiment_without_feature.py`.

La consecuencia visible es que **dos casas idénticas en barrios distintos
obtienen casi el mismo precio**: los 25 barrios producen 14 precios distintos
para la vivienda mediana, y el abanico entero va de $164.253 a $167.145, un 1,8 %
de la mediana. Los precios medianos reales de esos mismos barrios van de $89.500
(MeadowV) a $309.000 (NridgHt). El modelo sabe que el barrio importa poco *dada
la casa*; lo que no puede hacer es convertir un barrio barato en caro por sí
solo. Está fijado en las pruebas para que no pase inadvertido.

### 6. El contrato de características

El modelo espera 212 columnas. El formulario ofrece 9 campos. Alguien tiene que
rellenar las otras 203 con valores legítimos, y ese alguien es
`models_saved/feature_contract.json` (32,7 KB), un fichero generado a partir del
conjunto de entrenamiento que describe **cómo se construye una fila válida**.

Contiene:

- **`reference_row`**: la vivienda mediana del dataset, columna a columna. Es el
  punto de partida: todo lo que el usuario no especifica se queda con ese valor.
  Es una casa real y típica de Ames (`NAmes`, tipo 20, 1.444 ft², calidad 6),
  no una fila de ceros.
- **`reference_year` = 2008**: el año de venta de referencia. Todas las edades se
  calculan contra él, para que ninguna característica se salga de la distribución
  de entrenamiento.
- **`categorical`**: para cada una de las 27 categóricas, sus valores posibles,
  cuál es la categoría base y la lista de dummies. La base no se deduce con una
  regla: se determina empíricamente como *el valor cuyo dummy no aparece entre
  las 212 características*. (`get_dummies(drop_first=True)` no elimina siempre la
  primera categoría por orden alfabético; en `RoofMatl` elimina `CompShg`.)
- **`raw_ranges`**: el rango real de cada campo del formulario, para validar la
  entrada y para que ni la API ni el frontend lleven números escritos a mano.
- **`ranges`**: el rango de las 212 características en el espacio escalado, para
  poder avisar cuando una predicción se sale de lo que el modelo conoce.
- **`garage_area_por_plaza`**: mediana de superficie de garaje para 0, 1, 2, 3 y
  4 plazas, de modo que `GarageCars` y `GarageArea` no se contradigan.
- **`neighborhood_median_price`**: precio mediano real de venta por barrio, que
  la interfaz muestra como contexto.
- **`ui`**: las etiquetas en español de los 25 barrios y los 15 tipos de
  vivienda, con una descripción de cada uno.

Rangos de los campos del formulario en el conjunto de **entrenamiento** (tras
eliminar los outliers), que es exactamente contra lo que valida la API. Las
superficies van en ft² porque es la unidad del dataset; el formulario las pide en
m² y la API las convierte con 1 m² = 10,7639 ft²:

| Campo | Mínimo | Máximo | Mediana |
|---|---|---|---|
| `GrLivArea` (ft²) | 334 | 3.082 | 1.444 |
| `LotArea` (ft²) | 1.300 | 19.900 | 9.444 |
| `OverallQual` | 1 | 10 | 6 |
| `YearBuilt` | 1.872 | 2.010 | 1.972 |
| `BedroomAbvGr` | 0 | 6 | 3 |
| `FullBath` | 0 | 3 | 2 |
| `GarageCars` | 0 | 4 | 2 |
| `MSSubClass` (tipo) | 20 | 190 | — |

Tres matices de esa tabla:

- `MSSubClass` no es una magnitud, es un **código** de tipo de vivienda (20 = una
  planta, 60 = dos plantas, 190 = convertida en dos familias…). Por eso no tiene
  mediana: la vivienda de referencia usa el tipo más frecuente del dataset, el 20.
- En el CSV original hay viviendas más extremas que ese rango (hasta 5.642 ft² de
  superficie y 215.245 ft² de parcela), pero quedaron fuera del entrenamiento al
  eliminar outliers. La API no rechaza esos valores: devuelve el precio y avisa de
  que la vivienda se sale de lo que el modelo conoce.
- El formulario limita el año de construcción al año de referencia (2008), porque
  las edades se calculan contra él.

Además, el contrato mantiene las coherencias internas que el dataset respeta y
que, si se rompen, alimentan al modelo con casas imposibles:

- `TotalBsmtSF` es la suma de sus tres componentes (`BsmtFinSF1`, `BsmtFinSF2`,
  `BsmtUnfSF`), así que al fijar el total se reparte entre ellas;
- `GrLivArea` = `1stFlrSF` + `2ndFlrSF` + `LowQualFinSF`; al fijarla se asume
  vivienda de una planta, que es lo que hace la mediana del dataset;
- la superficie del garaje se deriva de las plazas con la tabla anterior, y sin
  plazas el garaje es 0;
- `TotRmsAbvGrd` crece con los dormitorios, y `HalfBath` es 0 si no hay ningún
  baño completo.

Y pone límites a lo que se le puede pedir:

- rechaza campos que no existen (`CAMPOS_PERMITIDOS`) y campos derivados
  (`HouseAge`, `TotalSF`…): esos se calculan, no se fijan, y aceptarlos rompería
  las identidades internas del dataset;
- si alguna de las 212 características se queda sin origen conocido, **lanza un
  error en lugar de enviar un 0 al modelo**;
- avisa cuando un valor cae fuera del rango de entrenamiento.

Para la vivienda mediana, 71 de las 212 características son distintas de cero:
el resto son legítimamente 0 (dummies de categorías que no aplican, piscinas que
no existen).

### 7. De una petición HTTP a un precio

El camino completo, sin pasos escondidos:

1. **El formulario** envía 9 campos (`neighborhood`, `ms_subclass`,
   `gr_liv_area_m2`, `lot_area_m2`, `overall_qual`, `year_built`, `bedrooms`,
   `bathrooms`, `garage_cars`). Las superficies van en m².
2. **`api/feature_mapper.py`** valida que el barrio y el tipo existan, convierte
   las superficies a ft² y traduce los nombres del formulario a los del dataset.
3. **`src/data/model_row.py`** parte de la vivienda de referencia, sobrescribe los
   campos indicados, reconstruye las coherencias internas y ejecuta **las mismas
   funciones de ingeniería que el entrenamiento** (`create_temporal_features`,
   `create_interaction_features`, `create_polynomial_features`). El resultado es
   un vector de 212 valores.
4. **El escalado** se aplica únicamente a las 23 columnas que el escalador
   conoce, localizándolas por nombre dentro del vector.
5. **`model.predict()`** devuelve el precio: la media de las predicciones de los
   200 árboles.
6. **La confianza** se calcula con la dispersión entre esos 200 árboles:
   `1 − desviación / precio`, acotada entre 0,50 y 0,95. No es una probabilidad
   calibrada, sino una medida de cuánto se ponen de acuerdo los árboles: si todos
   predicen algo parecido, la confianza es alta.
7. **Los avisos de rango** se comprueban sobre el vector ya escalado, comparándolo
   con los mínimos y máximos vistos en entrenamiento.
8. **La predicción se guarda** en la base de datos con los campos de entrada, el
   precio y la confianza, que es lo que alimenta el historial y las estadísticas.

Ejemplo real, la vivienda mediana (sin especificar ningún campo):

```
$164.594     (precio mediano del dataset: $163.000, desviación del 1,0 %)
```

Ejemplo con los 9 campos:

```
Entrada: NridgHt · tipo 60 · 200 m² (2.153 ft²) · 1.000 m² de parcela
         calidad 8 · construida en 1995 · 4 dormitorios · 2 baños · 3 plazas
Precio:  $237.828
```

### 8. Cómo responde el modelo al mover cada campo

Estas tablas se obtienen cambiando un solo campo sobre la vivienda mediana, y
sirven para comprobar que el modelo se comporta con sentido. El resto de campos
se quedan en su valor de referencia.

**Superficie habitable** (`GrLivArea`), el campo con más efecto:

| Superficie | Precio |
|---|---|
| 800 ft² (74 m²) | $133.687 |
| 1.200 ft² (112 m²) | $154.811 |
| 1.444 ft² (134 m², mediana) | $164.511 |
| 1.600 ft² (149 m²) | $165.822 |
| 2.200 ft² (204 m²) | $201.570 |
| 3.000 ft² (279 m²) | $218.397 |

**Calidad general** (`OverallQual`, de 1 a 10):

| Calidad | Precio |
|---|---|
| 3 | $118.744 |
| 5 | $153.236 |
| 6 (mediana) | $164.594 |
| 7 | $166.495 |
| 9 | $214.627 |

**Año de construcción** (`YearBuilt`):

| Año | Precio |
|---|---|
| 1900 | $150.734 |
| 1950 | $153.938 |
| 1972 (mediana) | $162.530 |
| 1990 | $174.836 |
| 2010 | $183.919 |

**Plazas de garaje** (`GarageCars`): de 0 plazas ($160.073) a 4 ($169.052), con
saltos pequeños: el garaje influye, pero poco comparado con la superficie.

**Tipo de vivienda** (`MSSubClass`): de $162.324 (tipo 180) a $164.754 (tipo 60)
entre los 15 tipos, con 11 precios distintos. Prácticamente no mueve el precio de
la vivienda mediana, por la misma razón que el barrio.

En los cuatro primeros casos la respuesta es monótona: más superficie, más
calidad, más año de construcción y más plazas de garaje implican más precio. Hay
pruebas automáticas para la superficie, la calidad y el garaje; el año y el tipo
de vivienda se han medido para este documento.

### 9. Cómo reproducir toda esta fase

```bash
python src/models/train_model.py            # entrena y regenera todos los artefactos
python src/models/train_model.py --retune   # vuelve a ejecutar el GridSearchCV
python scripts/check_artifacts.py           # diagnóstico de artefactos y contrato
python scripts/experiment_without_feature.py  # el experimento sin LivArea_Qual
```

`train_model.py` hace el ciclo completo desde `data/raw/train.csv`: preprocesado,
entrenamiento, métricas, `models_saved/` (modelo, escalador, nombres de
características, importancias), `data/processed/` y el contrato de
características; al final autocomprueba que la vivienda mediana produce un vector
de 212 valores dentro de rango. Tarda unos 2,4 segundos.

`check_artifacts.py` comprueba además que el contrato y el modelo coincidan en
número de características, que el escalador espere las 23 columnas previstas y
que la vivienda mediana quede cerca del precio mediano.

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

Esa petición devuelve `$237.828` con una confianza de 0,844 (ver el ejemplo de la
sección 7).

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

Sobre el modelo en concreto comprueban que: la vivienda mediana predice un precio
cercano a la mediana real, el barrio y el tipo de vivienda influyen (sin exigir
que cualquier par de barrios dé precios distintos: un bosque es constante a
trozos y muchos barrios caen en la misma hoja), el barrio sigue pesando menos del
5 %, y que más superficie, más calidad y más garaje implican más precio.

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

Una ejecución completa tarda unos dos minutos (52 s de instalación de
dependencias, 4 s de entrenamiento y 57 s de pruebas).

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

- **El barrio apenas influye**, y es una propiedad del dataset, no del código:
  con la superficie, la calidad y la antigüedad conocidas, el barrio añade poco
  (0,47 % de la importancia). La consecuencia práctica es que la aplicación no
  distingue bien entre zonas caras y baratas de Ames. Está medido y explicado en
  la sección 5.
- **Precisión del ~10 % (MAPE)** describiendo la vivienda solo con 9 campos; el
  resto de características se asumen iguales a la vivienda mediana. Una casa con
  un sótano terminado, una reforma reciente o una piscina se describirá mal si
  esos datos no se indican, porque el formulario no los pide.
- **La "confianza" no es una probabilidad calibrada**, sino el acuerdo entre los
  200 árboles del bosque.
- **Sin subida de archivos**: ni endpoints ni configuración.
- **Sin envío de correo.** Dos consecuencias:
  - el flujo de "he olvidado mi contraseña" genera el token, pero no lo envía: en
    desarrollo se devuelve en la respuesta para poder probarlo, y en producción
    queda pendiente conectar un proveedor SMTP;
  - **no hay verificación de email**: los usuarios se crean directamente como
    activos. El campo `is_verified` de la tabla existe, pero hoy siempre es
    `false`.
- **El límite de peticiones es en memoria**, por proceso. Con varios workers o
  en un despliegue real hace falta Redis.
- **Sin migraciones de base de datos.** El esquema se crea con `create_all()` al
  arrancar; evolucionarlo sin perder datos exigiría añadir migraciones.
- **El frontend no se ha comprobado en un navegador real** dentro de la CI: hay
  pruebas estáticas de que el HTML y el JavaScript se corresponden, pero ninguna
  ejecución en un navegador.
- **La imagen Docker no se construye en la CI.**

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

El código se publica bajo licencia **MIT** (ver `LICENSE`). Es un proyecto con
fines educativos y de portafolio.

El dataset Ames Housing proviene del trabajo de Dean De Cock (2011) y se
distribuye públicamente con fines académicos: no es propiedad de este proyecto.
Los artefactos de `models_saved/` se derivan de él.
