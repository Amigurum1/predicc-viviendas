# ============================================
# IMAGEN DE RUNTIME
# ============================================
# Se usa la variante "slim" de Python 3.12, que coincide con la versión fijada
# en requirements.txt (los artefactos del modelo se serializaron con ella).
FROM python:3.12-slim

# ============================================
# SIN COMPILADOR
# ============================================
# Antes se instalaban gcc y g++ con apt-get, pero NO hacen falta: todas las
# dependencias fijadas en requirements.txt (numpy, scipy, scikit-learn, pandas,
# psycopg2-binary, bcrypt, cryptography) traen ruedas precompiladas para
# CPython 3.12 en Linux. Quitarlos ahorra cientos de MB de imagen y acelera la
# construcción. Si algún día se añade una dependencia sin rueda, el fallo será
# evidente durante el `pip install` y habrá que volver a añadirlos.

# ============================================
# DIRECTORIO DE TRABAJO
# ============================================
WORKDIR /app

# ============================================
# DEPENDENCIAS DE PYTHON
# ============================================
# Se copia solo requirements.txt primero para aprovechar la caché de capas: si
# no cambian las dependencias, esta capa no se reconstruye al tocar el código.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ============================================
# CÓDIGO DE LA APLICACIÓN
# ============================================
# Lo que se copia está controlado por .dockerignore (fuera tests, notebooks,
# informes, salidas de pytest y cachés).
COPY . .

# ============================================
# USUARIO SIN PRIVILEGIOS
# ============================================
# La aplicación NO se ejecuta como root: el punto de entrada cede los
# privilegios a `appuser` con `setpriv` (ver docker-entrypoint.sh).
#
# Por eso aquí NO se declara `USER appuser`: si se declarara, el contenedor
# arrancaría directamente como appuser y el punto de entrada no podría corregir
# la propiedad de los volúmenes (que es de root si se crearon con una versión
# anterior de la imagen), y SQLite fallaría al escribir.
RUN mkdir -p data \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# ============================================
# PUERTO
# ============================================
EXPOSE 8000

# ============================================
# COMPROBACIÓN DE SALUD
# ============================================
# /health devuelve "degraded" (y por tanto falla aquí) si la base de datos no
# responde o si faltan tablas, que es justo el fallo silencioso que tenía el
# proyecto: el contenedor decía estar sano sin tener tablas.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# ============================================
# ARRANQUE
# ============================================
# El punto de entrada ajusta permisos y cede privilegios a appuser.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# Un solo worker: la app usa SQLite y un limitador de peticiones en memoria.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
