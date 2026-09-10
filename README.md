# IVR de turnos

IVR para **telefonía IP** (SIP). Reproduce cada día un audio distinto según un calendario, y puede desviar la llamada (tecla 1) al teléfono de ese destino.

Sirve para **farmacia de turno** y para cualquier rotación diaria: guardia, sucursal, técnico de guardia, mensaje institucional, etc. En el panel los destinos se llaman «farmacias»: son solo etiquetas.

## Cómo funciona (telefonía IP)

En una central IP (Issabel, FreePBX, Asterisk) las llamadas no van por un IVR «de hardware»: viajan en **SIP**. Un teléfono, una línea urbana (DID) o un trunk entrega la llamada a Asterisk. El **dialplan** decide qué hacer: reproducir un WAV, esperar una tecla, marcar otro número.

Este proyecto encaja así:

```
Llamada SIP (DID, interno o IVR existente)
        |
        v
  Asterisk / Issabel
        |
        v
  contexto  farmacia-turno
        |
        +--> reproduce intro + audio del DIA
        +--> si hay telefono y marca 1: desvia (Dial Local hacia from-internal)
```

El calendario **no vive en Issabel**. Vive en el panel (SQLite). Un timer a las **00:05** copia «qué toca hoy» a Asterisk (`AstDB`). El dialplan solo lee eso: no calcula fechas.

Issabel no tiene que importar el mes a Grupos horarios. Solo manda la llamada a `farmacia-turno,s,1`.

## Instalar desde este repositorio

En la **central** (Issabel / CentOS 7 / Asterisk 11), como root:

```bash
yum install -y git
git clone https://github.com/emirovetto/IVRIPE.git /opt/src/IVRIPE
cd /opt/src/IVRIPE
EXTEN=8000 bash install.sh
```

`8000` es un ejemplo: usa un interno **libre**. No lo crees como extensión en la GUI de Issabel.

- Panel: `http://IP-DE-TU-CENTRAL:8787` — `admin` / `admin` (cambiarla)
- Destino Issabel: `farmacia-turno,s,1`
- Guía completa: [INSTALAR.txt](INSTALAR.txt)

La primera vez puede tardar (compila Python 3.9 en `/opt/python39` sin tocar el de Issabel).

## Uso

1. Alta de destinos (nombre, audio, teléfono opcional).
2. Calendario del mes.
3. **Publicar ahora** la primera vez; después el timer de las 00:05.
4. El teléfono de cada destino debe marcarse **como desde un interno** (con prefijo de salida si la central lo pide).

## Desarrollo (solo panel, sin Asterisk)

```powershell
cd web
.\run.ps1
```

`http://127.0.0.1:8787`
