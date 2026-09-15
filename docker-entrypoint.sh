#!/bin/sh
# ============================================
# PUNTO DE ENTRADA DE LA API
# ============================================
# La aplicación se ejecuta como usuario SIN privilegios (`appuser`), pero el
# contenedor arranca como root por un motivo concreto:
#
#   Los volúmenes de Docker (la base de datos en /app/data y las subidas en
#   /app/uploads) pueden pertenecer a root si se crearon con una versión
#   anterior de la imagen, que corría como root. Solo root puede corregir esa
#   propiedad, y sin corregirla SQLite falla al escribir con:
#
#       sqlite3.OperationalError: attempt to write a readonly database
#
# Así que se ajusta la propiedad y se cede el control a `appuser` con `setpriv`
# (incluido en la imagen base; no hace falta instalar gosu ni su-exec).
#
# Si el contenedor ya arranca sin privilegios, no hace nada y ejecuta el comando
# tal cual.

set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data /app/uploads

    # `|| true` porque un volumen de solo lectura no debe impedir el arranque:
    # en ese caso el error real aparecerá al escribir, con un mensaje más claro.
    chown -R appuser:appuser /app/data /app/uploads 2>/dev/null || true

    exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi

exec "$@"
