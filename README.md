# IVR IP EMI&MAC

IVR de farmacia de turno para **Issabel (CentOS 7 + Asterisk 11)**.
El calendario se carga en el panel web; la central solo manda la llamada.

**Producción:** instalar **en la misma Issabel**. Guía: [INSTALAR.txt](INSTALAR.txt)

```bash
cd /root/IVRIP-IVRIPE
bash install.sh
```

- Panel: `http://IP-DE-LA-CENTRAL:8787` (`admin` / `admin` — cambiarla)
- Interno de prueba: **449700** (no crearlo en la GUI)
- Destino Issabel: `farmacia-turno,s,1`
- Todos los días a las **00:05** un timer publica el turno
- Tecla **1** al final del anuncio: desvío al teléfono de esa farmacia

## Qué hay en este repo

| Ruta | Para qué |
|---|---|
| `install.sh` | Punto de entrada (en Issabel llama a `install-centos7.sh`) |
| `web/` | Panel FastAPI |
| `asterisk/` | Dialplan y scripts de la central |
| `INSTALAR.txt` | Instalación y operación en producción |

## Desarrollo (esta PC, sin Asterisk)

```powershell
cd web
.\run.ps1
```

`http://127.0.0.1:8787`
