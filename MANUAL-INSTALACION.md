# Manual — IVR IP EMI&MAC

La guía de producción (Issabel / CentOS 7 / Asterisk 11) está en **[INSTALAR.txt](INSTALAR.txt)**.

Ahí está: copiar el proyecto, `bash install.sh`, destino `farmacia-turno,s,1`, panel, timer 00:05 y tecla 1.

Este archivo no duplica esos pasos para no desactualizarse.

## Recordatorio rápido

| Qué | Valor |
|---|---|
| Panel | `http://IP:8787` |
| Interno | 449700 (variable; no crear en la GUI) |
| Destino Issabel | `farmacia-turno,s,1` |
| Diario | `ivr-farmacias-diario.timer` a las 00:05 |
| Calendario | Panel Turnos → SQLite; no Grupos horarios |

## Docker

No es el despliegue de esta instalación. Si hiciera falta otro server, está `docker-compose.yml` + `.env.example`.
