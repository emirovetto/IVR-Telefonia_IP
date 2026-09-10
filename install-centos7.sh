#!/bin/bash
# Instala IVR IP EMI&MAC en Issabel / CentOS 7 / Asterisk 11.
#   sudo bash install-centos7.sh
#   sudo EXTEN=449700 bash install-centos7.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AST_ETC="${AST_ETC:-/etc/asterisk}"
SOUNDS="${SOUNDS:-/var/lib/asterisk/sounds/es/farmacias}"
EXTEN="${EXTEN:-449700}"
WEB_DST="${WEB_DST:-/opt/ivr-farmacias}"
WEB_PORT="${WEB_PORT:-8787}"
PYTHON_PREFIX="${PYTHON_PREFIX:-/opt/python39}"
PYTHON_VER="${PYTHON_VER:-3.9.21}"
REQ="${ROOT}/requirements-centos7.txt"

log() { echo "  $*" >&2; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: ejecute como root (sudo bash install-centos7.sh)"
    exit 1
fi

if ! command -v asterisk >/dev/null 2>&1; then
    echo "ERROR: no se encontró el comando asterisk. Este script se corre EN LA CENTRAL."
    exit 1
fi

# WinSCP desde Windows deja CRLF y bash falla con $'\r'
find "$ROOT" -type f \( -name '*.sh' -o -name '*.service' -o -name '*.timer' -o -name 'farmacias-turno' \) \
    -exec sed -i 's/\r$//' {} + 2>/dev/null || true

echo "IVR IP EMI&MAC — instalación CentOS 7 / Asterisk 11 (interno ${EXTEN})"
echo

AST_VER=$(asterisk -rx "core show version" 2>/dev/null | head -n 1 || true)
log "Asterisk: ${AST_VER:-no respondió}"
if [[ "$AST_VER" != *11.* && "$AST_VER" != *"11 "* ]]; then
    log "AVISO: este paquete está pensado para Asterisk 11. Sigue igual si la versión es otra."
fi

# Python 3.8+ (Issabel suele no tener python3). No toca /usr/bin/python.
# shellcheck source=instalar-python39.sh
source "${ROOT}/instalar-python39.sh"

yum_quiet() {
    yum install -y "$@"
}

# ---------------------------------------------------------------------------
# Paquetes del sistema
# ---------------------------------------------------------------------------
if [[ -f "${ROOT}/reparar-yum-centos7.sh" ]]; then
    bash "${ROOT}/reparar-yum-centos7.sh" || true
fi
log "Instalando paquetes (sox, cronie, ffmpeg si existe)..."
yum_quiet sox cronie 2>/dev/null || true
yum_quiet ffmpeg 2>/dev/null || true
if ! command -v ffmpeg >/dev/null 2>&1; then
    log "ffmpeg no está en yum. El panel usará sox para WAV. MP3 conviene convertirlos antes o instalar ffmpeg (nux-dextop)."
fi

# ---------------------------------------------------------------------------
# Dialplan Asterisk 11
# ---------------------------------------------------------------------------
log "Instalando dialplan y scripts..."
mkdir -p "${AST_ETC}/farmacias" "$SOUNDS" /var/lib/ivr-farmacias
install -m 755 "${ROOT}/asterisk/farmacias/actualizar_turno.sh" "${AST_ETC}/farmacias/actualizar_turno.sh"
install -m 755 "${ROOT}/asterisk/farmacias/convertir_audio.sh" "${AST_ETC}/farmacias/convertir_audio.sh"
install -m 755 "${ROOT}/asterisk/farmacias/generar_audios_prueba.sh" "${AST_ETC}/farmacias/generar_audios_prueba.sh"
install -m 755 "${ROOT}/asterisk/farmacias/verificar.sh" "${AST_ETC}/farmacias/verificar.sh"

DIALPLAN_SRC="${ROOT}/asterisk/extensions_farmacias.conf"
DIALPLAN_DST="${AST_ETC}/extensions_farmacias.conf"
sed "s/__IVR_EXTEN__/${EXTEN}/g" "$DIALPLAN_SRC" > "$DIALPLAN_DST"
chmod 664 "$DIALPLAN_DST"
if id asterisk >/dev/null 2>&1; then
    chown asterisk:asterisk "$DIALPLAN_DST"
fi

if [[ -f "${AST_ETC}/extensions_custom.conf" ]]; then
    DEST_CONF="${AST_ETC}/extensions_custom.conf"
    log "Issabel/FreePBX: usando extensions_custom.conf"
else
    DEST_CONF="${AST_ETC}/extensions.conf"
fi

if ! grep -q 'extensions_farmacias.conf' "$DEST_CONF" 2>/dev/null; then
    cat >> "$DEST_CONF" <<EOF

; IVR IP EMI&MAC — farmacia de turno (no borrar: Issabel no regenera este archivo)
#include extensions_farmacias.conf
EOF
    log "Agregado #include en ${DEST_CONF}"
else
    log "#include ya presente en ${DEST_CONF}"
fi

if [[ -f "${AST_ETC}/extensions_custom.conf" ]]; then
    if ! grep -q 'include => farmacia-turno' "${AST_ETC}/extensions_custom.conf"; then
        cat >> "${AST_ETC}/extensions_custom.conf" <<'EOF'

[from-internal-custom]
include => farmacia-turno
EOF
        log "Agregado include => farmacia-turno en from-internal-custom"
    fi
fi

install -m 644 "${ROOT}/asterisk/cron/farmacias-turno" /etc/cron.d/farmacias-turno
sed -i 's/\r$//' /etc/cron.d/farmacias-turno
# vixie-cron ignora el archivo si no termina en newline o si hay UTF-8
echo >> /etc/cron.d/farmacias-turno
chown root:root /etc/cron.d/farmacias-turno
chmod 644 /etc/cron.d/farmacias-turno

if asterisk -rx "core show function STAT" 2>/dev/null | grep -qi "STAT"; then
    log "Función STAT disponible (chequeo de audio)"
else
    asterisk -rx "module load func_stat.so" >/dev/null 2>&1 || true
    if asterisk -rx "core show function STAT" 2>/dev/null | grep -qi "STAT"; then
        log "Cargado func_stat.so"
    else
        log "AVISO: STAT no está. El IVR igual atiende; si falta el WAV irá a fallback solo si el archivo no existe y Playback falla a la siguiente prio."
    fi
fi

# ---------------------------------------------------------------------------
# Panel web
# ---------------------------------------------------------------------------
log "Instalando panel web..."
PYBIN="$(ensure_python)"
if ! "$PYBIN" -c 'import ssl' 2>/dev/null; then
    echo "ERROR: $PYBIN no tiene módulo ssl (se compiló sin openssl-devel)."
    echo "  yum install -y openssl-devel"
    echo "  rm -rf /opt/python39 /opt/ivr-farmacias/venv"
    echo "  bash instalar-python39.sh"
    echo "  bash install-centos7.sh"
    exit 1
fi

mkdir -p "${WEB_DST}"
rm -rf "${WEB_DST}/web"
cp -a "${ROOT}/web" "${WEB_DST}/web"
rm -rf "${WEB_DST}/web/data" "${WEB_DST}/web/.venv" "${WEB_DST}/venv"

"$PYBIN" -m venv "${WEB_DST}/venv"
# pip de CentOS 7 a veces falla el TLS la primera vez
PIP="${WEB_DST}/venv/bin/pip"
if ! "$PIP" install --upgrade pip; then
    log "Reintentando pip con trusted-host (certificados viejos)..."
    "$PIP" install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi
if ! "$PIP" install -r "$REQ"; then
    "$PIP" install -r "$REQ" --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi

if [[ ! -f /etc/ivr-farmacias.env ]]; then
    SECRET=$("$PYBIN" -c 'import secrets; print(secrets.token_urlsafe(32))')
    cat > /etc/ivr-farmacias.env <<EOF
IVR_ADMIN_USER=admin
IVR_ADMIN_PASSWORD=admin
IVR_EXTEN=${EXTEN}
IVR_SECRET=${SECRET}
IVR_ENV=production
IVR_PORT=${WEB_PORT}
TZ=America/Argentina/Buenos_Aires
EOF
    chmod 640 /etc/ivr-farmacias.env
    log "Creado /etc/ivr-farmacias.env (admin / admin — cámbielo en el panel)"
fi

install -m 644 "${ROOT}/web/ivr-farmacias.service" /etc/systemd/system/ivr-farmacias.service
if [[ "$WEB_PORT" != "8787" ]]; then
    sed -i "s/--port 8787/--port ${WEB_PORT}/" /etc/systemd/system/ivr-farmacias.service
fi

if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "${AST_ETC}/farmacias" "$SOUNDS" /var/lib/ivr-farmacias "${WEB_DST}"
    chown asterisk:asterisk "$DIALPLAN_DST" 2>/dev/null || true
    chown root:asterisk /etc/ivr-farmacias.env
    chmod 640 /etc/ivr-farmacias.env
fi

systemctl daemon-reload
systemctl enable ivr-farmacias.service
systemctl restart ivr-farmacias.service

install -m 644 "${ROOT}/web/ivr-farmacias-diario.service" /etc/systemd/system/ivr-farmacias-diario.service
install -m 644 "${ROOT}/web/ivr-farmacias-diario.timer" /etc/systemd/system/ivr-farmacias-diario.timer
sed -i 's/\r$//' /etc/systemd/system/ivr-farmacias-diario.service /etc/systemd/system/ivr-farmacias-diario.timer
systemctl daemon-reload
systemctl enable ivr-farmacias-diario.timer
systemctl start ivr-farmacias-diario.timer
systemctl enable crond.service 2>/dev/null || systemctl enable cron.service 2>/dev/null || true
systemctl start crond.service 2>/dev/null || systemctl start cron.service 2>/dev/null || true

# ---------------------------------------------------------------------------
# Firewall 8787 (Issabel suele usar iptables; a veces firewalld)
# ---------------------------------------------------------------------------
abrir_8787() {
    if systemctl is-active --quiet firewalld 2>/dev/null; then
        firewall-cmd --permanent --add-port="${WEB_PORT}/tcp" >/dev/null 2>&1 || true
        firewall-cmd --reload >/dev/null 2>&1 || true
        log "firewalld: abierto TCP ${WEB_PORT}"
        return
    fi
    if command -v iptables >/dev/null 2>&1; then
        if ! iptables -C INPUT -p tcp --dport "$WEB_PORT" -j ACCEPT 2>/dev/null; then
            iptables -I INPUT -p tcp --dport "$WEB_PORT" -j ACCEPT
            if command -v service >/dev/null 2>&1; then
                service iptables save 2>/dev/null || true
            fi
            log "iptables: abierto TCP ${WEB_PORT}"
        else
            log "iptables: TCP ${WEB_PORT} ya estaba abierto"
        fi
    fi
}
abrir_8787

# ---------------------------------------------------------------------------
# Audios de prueba si no hay ninguno
# ---------------------------------------------------------------------------
if [[ -z "$(ls -A "$SOUNDS"/*.wav 2>/dev/null || true)" ]]; then
    if command -v ffmpeg >/dev/null 2>&1 && { command -v espeak-ng >/dev/null 2>&1 || command -v espeak >/dev/null 2>&1; }; then
        log "No hay audios: generando voces de prueba..."
        DESTINO="$SOUNDS" bash "${AST_ETC}/farmacias/generar_audios_prueba.sh" || true
    else
        log "AVISO: no hay WAV en ${SOUNDS}. Cárguelos desde el panel (Audios): intro, fallback y cada farmacia."
    fi
fi

asterisk -rx "dialplan reload" >/dev/null || true
bash "${AST_ETC}/farmacias/actualizar_turno.sh" || true
bash "${AST_ETC}/farmacias/verificar.sh" || true

sleep 1
if systemctl is-active --quiet ivr-farmacias; then
    log "Servicio ivr-farmacias: activo"
else
    echo "ERROR: el panel no arrancó. Vea: journalctl -u ivr-farmacias -n 50 --no-pager"
    systemctl status ivr-farmacias --no-pager || true
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "============================================================"
echo " Instalación terminada — IVR IP EMI&MAC"
echo "============================================================"
echo "  Interno:      ${EXTEN}"
echo "  Panel web:    http://${IP:-IP-DE-LA-CENTRAL}:${WEB_PORT}"
echo "  Usuario:      admin"
echo "  Contraseña:   admin   (cámbiela en Sistema)"
echo "  Calendario:   /var/lib/ivr-farmacias/ivr.db"
echo "  Diario:       systemd timer 00:05 (y cron.d de respaldo)"
echo "  Audios:       ${SOUNDS}"
echo
echo "  NO cree el interno ${EXTEN} en la GUI de Issabel."
echo "  En Issabel, UNA VEZ:"
echo "    PBX -> Destinos personalizados"
echo "      Descripcion: IVR IP EMI&MAC"
echo "      Destino:     farmacia-turno,s,1"
echo "    Aplicar cambios."
echo "    Ruta de entrada o tecla de IVR -> ese destino."
echo "    Prueba: marcar ${EXTEN} desde un telefono interno."
echo "  Guia: INSTALAR.txt"
echo "============================================================"
