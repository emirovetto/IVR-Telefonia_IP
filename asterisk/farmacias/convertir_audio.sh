#!/bin/bash
# Convierte un audio de origen a WAV Asterisk: mono, 8 kHz, 16-bit PCM.
# Uso: ./convertir_audio.sh origen.mp3 farmacia_central
set -euo pipefail

ORIGEN="${1:-}"
CODIGO="${2:-}"
DESTINO_DIR="${DESTINO_DIR:-/var/lib/asterisk/sounds/es/farmacias}"

if [[ -z "$ORIGEN" || -z "$CODIGO" ]]; then
    echo "Uso: $0 <archivo_origen> <codigo_farmacia>"
    echo "Ejemplo: $0 grabacion.mp3 farmacia_central"
    exit 1
fi

if [[ ! -f "$ORIGEN" ]]; then
    echo "ERROR: no existe ${ORIGEN}"
    exit 1
fi

CODIGO="${CODIGO%.wav}"
CODIGO="${CODIGO//[^a-zA-Z0-9_]/}"
mkdir -p "$DESTINO_DIR"

SALIDA="${DESTINO_DIR}/${CODIGO}.wav"
if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -y -i "$ORIGEN" -ar 8000 -ac 1 -sample_fmt s16 "$SALIDA"
elif command -v sox >/dev/null 2>&1; then
    sox "$ORIGEN" -r 8000 -c 1 -b 16 "$SALIDA"
else
    echo "ERROR: instale ffmpeg o sox (en CentOS 7: yum install sox)"
    exit 1
fi

if id asterisk >/dev/null 2>&1; then
    chown asterisk:asterisk "$SALIDA"
fi
chmod 644 "$SALIDA"

echo "Listo: ${SALIDA}"
