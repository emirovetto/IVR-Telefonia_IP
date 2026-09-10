#!/bin/bash
# Todos los días a las 00:05: lee el calendario del panel (SQLite)
# y publica en AstDB la farmacia de HOY. No usa CSV.
set -u

ENVFILE="${ENVFILE:-/etc/ivr-farmacias.env}"
WEB="${WEB:-/opt/ivr-farmacias/web}"
PYTHON="${PYTHON:-/opt/ivr-farmacias/venv/bin/python}"

log() {
    logger -t ivr-farmacias "$1"
    echo "$(date '+%F %T') $1"
    echo "$(date '+%F %T') $1" >> /var/log/ivr-farmacias.log 2>/dev/null || true
}

if [[ -f "$ENVFILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENVFILE"
    set +a
fi
export IVR_ENV="${IVR_ENV:-production}"

if [[ ! -x "$PYTHON" ]]; then
    log "ERROR: no está el intérprete del panel (${PYTHON}). ¿Se corrió install.sh?"
    exit 1
fi

if [[ ! -d "$WEB" ]]; then
    log "ERROR: no está el panel en ${WEB}"
    exit 1
fi

cd "$WEB" || exit 1
out="$("$PYTHON" -m app.cli actualizar-hoy 2>&1)"
status=$?
log "$out"
exit "$status"
