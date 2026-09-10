from __future__ import annotations

"""Tareas de consola. El cron diario llama: python -m app.cli actualizar-hoy

Lee el calendario del panel (SQLite), no un CSV.
"""

import sys
from datetime import date

from . import audio, config, db
from .db import init_db
from .sync import apply_today


def _syslog(msg: str) -> None:
    try:
        import syslog

        syslog.syslog(syslog.LOG_INFO, f"IVR de turnos: {msg}")
    except Exception:
        pass


def actualizar_hoy() -> int:
    config.ensure_dirs()
    init_db()
    ok, msg = apply_today()
    line = f"{date.today().isoformat()} {msg}"
    print(line)
    _syslog(line)
    return 0 if ok else 1


def tiene_hoy() -> int:
    config.ensure_dirs()
    init_db()
    hoy = date.today().isoformat()
    with db.connect() as conn:
        turno = db.get_turno(conn, hoy)
    if turno is None:
        print(f"sin turno en el panel para {hoy}")
        return 1
    codigo = turno["farmacia_codigo"]
    if not audio.audio_exists(codigo):
        print(f"turno {codigo} sin audio")
        return 1
    print(f"turno de hoy en el panel: {codigo}")
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "actualizar-hoy"
    if cmd in {"actualizar-hoy", "hoy"}:
        raise SystemExit(actualizar_hoy())
    if cmd in {"tiene-hoy", "verificar-hoy"}:
        raise SystemExit(tiene_hoy())
    print("Uso: python -m app.cli actualizar-hoy|tiene-hoy", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
