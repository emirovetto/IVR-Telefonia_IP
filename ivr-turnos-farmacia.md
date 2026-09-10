# IVR de Turnos de Farmacia — Diseño e Implementación

Sistema para que, al llamar a un número interno de la central, se reproduzca automáticamente un audio informando qué farmacia está de turno ese día. Corre sobre la central Asterisk existente. Los audios se generan aparte (uno por farmacia) y el sistema solo decide **cuál** reproducir según la fecha.

---

## 1. Idea general

- Existe un **cronograma mensual** (un archivo de texto simple) que dice qué farmacia está de turno cada día del mes.
- Todos los días a la medianoche, un **script + cron** lee ese cronograma, busca la fila de "hoy" y guarda el resultado en la base de datos interna de Asterisk (AstDB).
- Cuando alguien llama al número del servicio, el **dialplan** simplemente lee ese valor de AstDB (operación instantánea, sin cálculos ni scripts durante la llamada) y reproduce: audio genérico de introducción + audio específico de la farmacia de turno.
- Si un día no está cargado en el cronograma, se reproduce un audio de fallback en vez de dejar la llamada en silencio o cortar.

Ventaja de este enfoque: la llamada en sí nunca depende de que un script corra bien en ese instante — todo el trabajo "pesado" (leer el cronograma, resolver la fecha) ya se hizo antes, a la madrugada. Si algo falla en el cron, se nota en los logs sin afectar llamadas en curso.

---

## 2. Estructura de archivos

```
/etc/asterisk/farmacias/
├── turnos_mensual.csv        # cronograma del mes, uno o varios meses cargados
└── actualizar_turno.sh       # script que corre por cron a la medianoche

/var/lib/asterisk/sounds/es/farmacias/
├── intro.wav                 # "La farmacia de turno es:"
├── fallback.wav              # "No hay información de turno cargada para hoy, comuníquese con..."
├── farmacia_central.wav      # audio propio de cada farmacia (nombre, dirección, teléfono)
├── farmacia_del_pueblo.wav
└── farmacia_san_martin.wav
```

Los nombres de archivo de audio (`farmacia_central`, etc.) son el **código** que se usa en el cronograma para identificar cada farmacia — tienen que coincidir exactamente.

---

## 3. Formato del cronograma mensual (`turnos_mensual.csv`)

Un archivo CSV simple, una fila por día:

```csv
fecha,farmacia
2026-09-01,farmacia_central
2026-09-02,farmacia_del_pueblo
2026-09-03,farmacia_del_pueblo
2026-09-04,farmacia_san_martin
2026-09-05,farmacia_central
...
2026-09-30,farmacia_del_pueblo
```

- `fecha`: formato `YYYY-MM-DD`.
- `farmacia`: nombre del archivo de audio correspondiente, **sin extensión**.

Para cargar el mes siguiente, se agregan filas nuevas al mismo archivo (o se genera un CSV nuevo por mes y se concatenan) — cualquiera de las dos formas funciona porque el script busca por fecha exacta, no por posición.

**Quién lo edita:** cualquiera con acceso a ese archivo (por ejemplo por la carpeta Samba que ya tenés armada) puede completar el mes con un editor de texto o Excel/LibreOffice guardando como CSV. No hace falta tocar Asterisk para nada de esto.

---

## 4. Script de actualización diaria (`actualizar_turno.sh`)

Corre una vez por día (cron a las 00:05) y deja el resultado de "hoy" listo en AstDB para que el dialplan lo lea sin esfuerzo.

```bash
#!/bin/bash
# actualizar_turno.sh
# Lee el cronograma mensual, busca la farmacia de turno de HOY,
# y la guarda en AstDB para que el dialplan la use.

CSV="/etc/asterisk/farmacias/turnos_mensual.csv"
HOY=$(date +%Y-%m-%d)

FARMACIA=$(awk -F',' -v hoy="$HOY" '$1==hoy {print $2}' "$CSV")

if [ -z "$FARMACIA" ]; then
    # No hay turno cargado para hoy: marcar fallback
    asterisk -rx "database put farmacias hoy fallback"
    logger "IVR farmacias: sin turno cargado para $HOY, usando fallback"
else
    asterisk -rx "database put farmacias hoy $FARMACIA"
    logger "IVR farmacias: turno de hoy ($HOY) = $FARMACIA"
fi
```

Dar permisos de ejecución:

```bash
chmod +x /etc/asterisk/farmacias/actualizar_turno.sh
```

### Cron

```cron
5 0 * * * /etc/asterisk/farmacias/actualizar_turno.sh
```

(Corre todos los días a las 00:05, con margen para que no coincida justo con el cambio de fecha.)

**Recomendado:** correr el script también manualmente una vez al instalar el sistema, para no depender de esperar hasta la medianoche para la primera prueba:

```bash
sudo /etc/asterisk/farmacias/actualizar_turno.sh
```

---

## 5. Dialplan (`extensions.conf`)

Asignale a este contexto el número/interno que la gente va a marcar (coordinar con quien administra la numeración):

```ini
[farmacia-turno]
exten => TU_NUMERO,1,Answer()
 same => n,Wait(1)
 same => n,Set(FARMACIA=${DB(farmacias/hoy)})
 same => n,GotoIf($["${FARMACIA}" = ""]?sin_dato:con_dato)

 same => n(con_dato),Playback(farmacias/intro)
 same => n,Playback(farmacias/${FARMACIA})
 same => n,Hangup()

 same => n(sin_dato),Playback(farmacias/fallback)
 same => n,Hangup()
```

Notas:
- `TU_NUMERO` es el número/interno real asignado (ej. un corto interno de 4 dígitos, o el DID completo según cómo lo dé de alta la central).
- El `GotoIf` cubre el caso de que ni siquiera exista la clave en AstDB (por ejemplo, primera instalación antes de correr el script una vez).
- Si el valor guardado es literalmente `fallback` (por día sin cronograma cargado), el archivo `farmacias/fallback.wav` también cubre ese caso porque `Playback(farmacias/fallback)` coincide con el nombre real del archivo — no hace falta lógica extra.

Después de editar, recargar el dialplan sin reiniciar Asterisk:

```
asterisk -rx "dialplan reload"
```

---

## 6. Formato de audio

Igual que cualquier IVR de Asterisk: WAV mono, 8kHz, 16-bit PCM. Conversión desde cualquier formato de origen:

```bash
ffmpeg -i original.mp3 -ar 8000 -ac 1 -sample_fmt s16 /var/lib/asterisk/sounds/es/farmacias/farmacia_central.wav
```

---

## 7. Agregar o dar de baja una farmacia

1. Generar el audio de esa farmacia (nombre, dirección, teléfono) y guardarlo en `/var/lib/asterisk/sounds/es/farmacias/` con un nombre único sin espacios (ej. `farmacia_nueva.wav`).
2. Usar ese mismo nombre (sin extensión) como código en el CSV del cronograma.
3. No hace falta tocar el dialplan ni reiniciar nada — el sistema ya lee dinámicamente lo que diga el CSV.

---

## 8. Prueba de punta a punta

```bash
# 1. Cargar manualmente el turno de hoy
sudo /etc/asterisk/farmacias/actualizar_turno.sh

# 2. Confirmar qué quedó guardado
asterisk -rx "database get farmacias hoy"

# 3. Recargar dialplan
asterisk -rx "dialplan reload"

# 4. Llamar al número asignado desde un teléfono real y verificar el audio
```

---

## 9. Mejoras futuras (opcional, no necesarias para la v1)

- Panel web simple para cargar el cronograma del mes sin tocar el CSV a mano (con validación de que todos los días del mes tengan farmacia asignada).
- Alerta automática (mail/Telegram) si el cron detecta un día sin turno cargado, en vez de esperar a que alguien llame y escuche el fallback.
- Extender el mismo patrón (`DB(...)` + cron) a otros anuncios configurables de la cooperativa (el mismo mecanismo sirve para cualquier "anuncio del día", no solo farmacias).
