#!/bin/bash
# Genera audios de prueba en español (espeak-ng o espeak) para validar el IVR
# antes de tener las grabaciones reales de cada farmacia.
set -euo pipefail

DESTINO="${DESTINO:-/var/lib/asterisk/sounds/es/farmacias}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

if command -v espeak-ng >/dev/null 2>&1; then
    ESPEAK=espeak-ng
elif command -v espeak >/dev/null 2>&1; then
    ESPEAK=espeak
else
    echo "ERROR: instale espeak-ng (o espeak) y ffmpeg para generar audios de prueba"
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ERROR: ffmpeg no está instalado"
    exit 1
fi

sintetizar() {
    local codigo="$1"
    local texto="$2"
    local crudo="${TMPDIR}/${codigo}.wav"
    local final="${DESTINO}/${codigo}.wav"

    "$ESPEAK" -v es -s 130 -w "$crudo" "$texto"
    ffmpeg -y -loglevel error -i "$crudo" -ar 8000 -ac 1 -sample_fmt s16 "$final"
    echo "  ${final}"
}

mkdir -p "$DESTINO"

echo "Generando audios de prueba en ${DESTINO}..."
sintetizar "intro" "La farmacia de turno es."
sintetizar "fallback" "No hay información de turno cargada para hoy. Comuníquese con administración."
sintetizar "farmacia_central" "Farmacia Central. Calle San Martín 150. Teléfono 4 2 1 3 0 0 0."
sintetizar "farmacia_del_pueblo" "Farmacia del Pueblo. Avenida Belgrano 220. Teléfono 4 2 2 1 5 0 0."
sintetizar "farmacia_san_martin" "Farmacia San Martín. Calle Rivadavia 80. Teléfono 4 2 3 4 0 0 0."

if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "$DESTINO"
fi
chmod 644 "${DESTINO}"/*.wav

echo "Listo. Reemplace estos WAV por grabaciones reales cuando las tenga."
