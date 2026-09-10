#!/bin/bash
# Instala IVR IP EMI&MAC (panel web + dialplan) en una central Asterisk.
#   sudo bash install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AST_ETC="${AST_ETC:-/etc/asterisk}"
SOUNDS="${SOUNDS:-/var/lib/asterisk/sounds/es/farmacias}"
EXTEN="${EXTEN:-449700}"
WEB_DST="${WEB_DST:-/opt/ivr-farmacias}"
WEB_PORT="${WEB_PORT:-8787}"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: ejecute como root (sudo bash install.sh)"
    exit 1
fi

# Issabel / CentOS 7 + Asterisk 11: instalador dedicado
if [[ -f /etc/redhat-release ]] || [[ -f /etc/centos-release ]] || [[ -f /etc/issabel.conf ]]; then
    if [[ -x "${ROOT}/install-centos7.sh" || -f "${ROOT}/install-centos7.sh" ]]; then
        echo "Detectado CentOS/Issabel: usando install-centos7.sh"
        export EXTEN WEB_PORT AST_ETC SOUNDS WEB_DST
        exec bash "${ROOT}/install-centos7.sh"
    fi
fi

if ! command -v asterisk >/dev/null 2>&1; then
    echo "ERROR: no se encontró el comando asterisk en este servidor"
    exit 1
fi

echo "Instalando IVR IP EMI&MAC (interno ${EXTEN})..."

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
    echo "  Detectado FreePBX: usando extensions_custom.conf"
else
    DEST_CONF="${AST_ETC}/extensions.conf"
fi

if ! grep -q 'extensions_farmacias.conf' "$DEST_CONF" 2>/dev/null; then
    cat >> "$DEST_CONF" <<EOF

; IVR IP EMI&MAC — farmacia de turno
#include extensions_farmacias.conf
EOF
    echo "  Agregado #include en ${DEST_CONF}"
else
    echo "  #include ya presente en ${DEST_CONF}"
fi

if [[ -f "${AST_ETC}/extensions_custom.conf" ]]; then
    if ! grep -q 'include => farmacia-turno' "${AST_ETC}/extensions_custom.conf"; then
        cat >> "${AST_ETC}/extensions_custom.conf" <<'EOF'

[from-internal-custom]
include => farmacia-turno
EOF
        echo "  Agregado include => farmacia-turno en from-internal-custom"
    fi
elif grep -q '^\[from-internal\]' "${AST_ETC}/extensions.conf" 2>/dev/null; then
    if ! grep -q 'include => farmacia-turno' "${AST_ETC}/extensions.conf"; then
        echo "  AVISO: agregue esta línea dentro de [from-internal] en extensions.conf:"
        echo "         include => farmacia-turno"
    fi
fi

install -m 644 "${ROOT}/asterisk/cron/farmacias-turno" /etc/cron.d/farmacias-turno
sed -i 's/\r$//' /etc/cron.d/farmacias-turno
echo >> /etc/cron.d/farmacias-turno
chmod 644 /etc/cron.d/farmacias-turno
if [[ -f "${ROOT}/web/ivr-farmacias-diario.timer" ]]; then
    install -m 644 "${ROOT}/web/ivr-farmacias-diario.service" /etc/systemd/system/ivr-farmacias-diario.service
    install -m 644 "${ROOT}/web/ivr-farmacias-diario.timer" /etc/systemd/system/ivr-farmacias-diario.timer
    systemctl daemon-reload
    systemctl enable --now ivr-farmacias-diario.timer
fi

echo "  Instalando panel web..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y python3 python3-venv python3-pip ffmpeg >/dev/null
fi

mkdir -p "${WEB_DST}"
rm -rf "${WEB_DST}/web"
cp -a "${ROOT}/web" "${WEB_DST}/web"
rm -rf "${WEB_DST}/web/data" "${WEB_DST}/web/.venv" "${WEB_DST}/venv"
python3 -m venv "${WEB_DST}/venv"
"${WEB_DST}/venv/bin/pip" install --upgrade pip >/dev/null
"${WEB_DST}/venv/bin/pip" install -r "${WEB_DST}/web/requirements.txt"

if [[ ! -f /etc/ivr-farmacias.env ]]; then
    SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    cat > /etc/ivr-farmacias.env <<EOF
IVR_ADMIN_USER=admin
IVR_ADMIN_PASSWORD=admin
IVR_EXTEN=${EXTEN}
IVR_SECRET=${SECRET}
IVR_ENV=production
IVR_PORT=${WEB_PORT}
EOF
    chmod 640 /etc/ivr-farmacias.env
    echo "  Creado /etc/ivr-farmacias.env (usuario admin / admin — cambielo en el panel)"
fi

install -m 644 "${ROOT}/web/ivr-farmacias.service" /etc/systemd/system/ivr-farmacias.service
systemctl daemon-reload
systemctl enable --now ivr-farmacias.service

if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "${AST_ETC}/farmacias" "$SOUNDS" /var/lib/ivr-farmacias "${WEB_DST}"
    chown root:asterisk /etc/ivr-farmacias.env
fi

if [[ -z "$(ls -A "$SOUNDS"/*.wav 2>/dev/null || true)" ]]; then
    if command -v ffmpeg >/dev/null 2>&1 && { command -v espeak-ng >/dev/null 2>&1 || command -v espeak >/dev/null 2>&1; }; then
        echo "  No hay audios: generando voces de prueba..."
        DESTINO="$SOUNDS" bash "${AST_ETC}/farmacias/generar_audios_prueba.sh"
    else
        echo "  AVISO: no hay WAV en ${SOUNDS}. Cárguelos desde el panel web (Audios)."
    fi
fi

asterisk -rx "dialplan reload" >/dev/null
bash "${AST_ETC}/farmacias/actualizar_turno.sh" || true
bash "${AST_ETC}/farmacias/verificar.sh" || true

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Instalación de IVR IP EMI&MAC terminada."
echo "  Interno:     ${EXTEN}"
echo "  Panel web:   http://${IP:-IP}:${WEB_PORT}"
echo "  Usuario:     admin"
echo "  Contraseña:  admin  (cámbiela en Sistema)"
echo "  Calendario:  panel Turnos → /var/lib/ivr-farmacias/ivr.db"
echo "  Diario:      cron 00:05 (automático, no hay que publicar cada día)"
echo "  Audios:      ${SOUNDS}"
echo "Llame al ${EXTEN} desde un teléfono de la central para probar el IVR."
