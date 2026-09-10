#!/bin/bash
# Comprueba que IVR de turnos esté instalado y listo para atender.
set -u

SCRIPT="/etc/asterisk/farmacias/actualizar_turno.sh"
SOUNDS="/var/lib/asterisk/sounds/es/farmacias"
CRON="/etc/cron.d/farmacias-turno"
DB="/var/lib/ivr-farmacias/ivr.db"
PYTHON="/opt/ivr-farmacias/venv/bin/python"
WEB="/opt/ivr-farmacias/web"
HOY=$(date +%Y-%m-%d)
EXTEN="${IVR_EXTEN:-8000}"
if [[ -f /etc/ivr-farmacias.env ]]; then
    env_exten=$(grep -E '^IVR_EXTEN=' /etc/ivr-farmacias.env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '\r')
    [[ -n "$env_exten" ]] && EXTEN="$env_exten"
fi
if [[ -x "$PYTHON" && -d "$WEB" ]]; then
    db_exten=$(
        cd "$WEB" && IVR_ENV=production "$PYTHON" - 2>/dev/null <<'PY' || true
from app import db
from app.db import init_db
init_db()
with db.connect() as conn:
    print(db.get_config(conn, "extension") or "")
PY
    )
    db_exten=$(printf '%s' "$db_exten" | tr -d '\r' | tail -n 1)
    [[ -n "$db_exten" ]] && EXTEN="$db_exten"
fi
errores=0

ok() { echo "  [OK] $1"; }
fail() { echo "  [FALTA] $1"; errores=$((errores + 1)); }

echo "Verificación IVR de turnos — ${HOY} — interno ${EXTEN}"
echo

[[ -x "$SCRIPT" ]] && ok "script diario ${SCRIPT}" || fail "script diario ${SCRIPT}"
[[ -f "$CRON" ]] && ok "cron 00:05 ${CRON}" || fail "cron 00:05 ${CRON}"
if systemctl is-enabled ivr-farmacias-diario.timer >/dev/null 2>&1 \
    || systemctl is-active ivr-farmacias-diario.timer >/dev/null 2>&1; then
    ok "timer systemd 00:05"
else
    fail "timer ivr-farmacias-diario no esta activo"
fi
[[ -f "$DB" ]] && ok "base del panel ${DB}" || fail "base del panel ${DB} (¿se abrió el panel alguna vez?)"
[[ -x "$PYTHON" ]] && ok "intérprete del panel" || fail "intérprete ${PYTHON}"

for f in intro fallback; do
    if [[ -f "${SOUNDS}/${f}.wav" ]]; then
        ok "audio ${f}.wav"
    else
        fail "audio ${SOUNDS}/${f}.wav"
    fi
done

if ss -lntn 2>/dev/null | grep -q ':8787' || netstat -lnt 2>/dev/null | grep -q ':8787'; then
    ok "panel escuchando en TCP 8787"
else
    fail "panel no escucha 8787 — systemctl status ivr-farmacias"
fi

if [[ -x "$PYTHON" && -d "$WEB" ]]; then
    if ( cd "$WEB" && IVR_ENV=production "$PYTHON" -m app.cli tiene-hoy >/dev/null 2>&1 ); then
        ok "el panel tiene turno para hoy"
    else
        fail "el panel no tiene turno (con audio) para ${HOY} — cargalo en Turnos"
    fi
fi

if asterisk -rx "core show version" >/dev/null 2>&1; then
    ok "Asterisk responde"
    valor=$(asterisk -rx "database get farmacias hoy" 2>/dev/null | awk '{print $NF}')
    if [[ -n "$valor" && "$valor" != "Database" ]]; then
        ok "AstDB farmacias/hoy = ${valor}"
    else
        fail "AstDB farmacias/hoy vacío — se publica solo a las 00:05 o con Publicar hoy"
    fi
    if asterisk -rx "dialplan show farmacia-turno" 2>/dev/null | grep -qi "farmacia-turno"; then
        ok "contexto farmacia-turno cargado"
    else
        fail "contexto farmacia-turno no está en el dialplan (dialplan reload / #include)"
    fi
    if asterisk -rx "dialplan show farmacia-turno" 2>/dev/null | grep -q "$EXTEN"; then
        ok "interno ${EXTEN} en el dialplan"
    else
        fail "el interno ${EXTEN} no aparece en farmacia-turno — cambialo en el panel (Sistema) o reinstala con EXTEN=${EXTEN}"
    fi
    if asterisk -rx "core show function STAT" 2>/dev/null | grep -qi "STAT"; then
        ok "función STAT (Asterisk 11)"
    else
        fail "función STAT no cargada — pruebe: asterisk -rx 'module load func_stat.so'"
    fi
else
    fail "Asterisk no responde (¿el servicio está caído?)"
fi

echo
if [[ "$errores" -eq 0 ]]; then
    echo "Todo listo. El cambio de día es automático a las 00:05. Llame al interno ${EXTEN} para probar."
    exit 0
fi
echo "Hay ${errores} problema(s). Revise los ítems marcados FALTA."
exit 1
