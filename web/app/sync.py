from __future__ import annotations

from pathlib import Path

from . import asterisk, audio, config, db


def export_csv() -> Path:
    config.ensure_dirs()
    with db.connect() as conn:
        rows = db.all_turnos(conn)
    lines = ["fecha,farmacia"]
    for row in rows:
        lines.append(f"{row['fecha']},{row['farmacia_codigo']}")
    config.CSV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config.CSV_PATH


def apply_today() -> tuple[bool, str]:
    from datetime import date

    hoy = date.today().isoformat()
    with db.connect() as conn:
        turno = db.get_turno(conn, hoy)
    if turno is None:
        if asterisk.asterisk_available():
            asterisk.db_put("farmacias", "hoy_tel", "")
            ok, msg = asterisk.db_put("farmacias", "hoy", "fallback")
            return ok, "No hay turno para hoy: se publicó fallback en Asterisk" if ok else msg
        return True, "No hay turno para hoy. En la central se usará el audio de fallback."

    codigo = turno["farmacia_codigo"]
    telefono = audio.sanitize_phone(turno["telefono"] or "")
    if not audio.audio_exists(codigo):
        if asterisk.asterisk_available():
            asterisk.db_put("farmacias", "hoy_tel", "")
            ok, msg = asterisk.db_put("farmacias", "hoy", "fallback")
            return ok, f"La farmacia {codigo} no tiene audio: se publicó fallback" if ok else msg
        return True, f"La farmacia {codigo} no tiene audio. En la central se usaría fallback."

    if not asterisk.asterisk_available():
        extra = f" — desvío al {telefono} con tecla 1" if telefono else " — sin teléfono, no hay desvío"
        return True, f"Turno de hoy listo en el panel: {codigo}{extra}."

    asterisk.db_put("farmacias", "hoy_tel", telefono)
    ok, msg = asterisk.db_put("farmacias", "hoy", codigo)
    if ok:
        extra = f", tecla 1 llama al {telefono}" if telefono else ", sin teléfono (no hay desvío)"
        return True, f"Asterisk actualizado: hoy = {codigo}{extra}"
    return False, msg


def write_dialplan(exten: str) -> Path:
    config.ensure_dirs()
    sounds = "/var/lib/asterisk/sounds/es/farmacias"
    if config.PRODUCTION:
        sounds = config.SOUNDS_DIR.as_posix()
    content = f"""; Generado por {config.SYSTEM_NAME}
; Interno (variable): {exten}
; Issabel: Destino personalizado → farmacia-turno,s,1
[farmacia-turno]
exten => s,1,Goto({exten},1)

exten => {exten},1,NoOp(IVR IP EMI-MAC farmacia de turno)
 same => n,Set(CHANNEL(language)=es)
 same => n,Answer()
 same => n,Wait(1)
 same => n,Set(FARMACIA=${{DB(farmacias/hoy)}})
 same => n,GotoIf($["${{FARMACIA}}" = ""]?sin_dato)
 same => n,GotoIf($["${{FARMACIA}}" = "fallback"]?sin_dato)
 same => n,GotoIf($["${{STAT(e,{sounds}/${{FARMACIA}}.wav)}}" = "0"]?sin_dato)
 same => n,Set(TELEFONO=${{DB(farmacias/hoy_tel)}})
 same => n,Playback(farmacias/intro)
 same => n,Playback(farmacias/${{FARMACIA}})
 same => n,GotoIf($["${{TELEFONO}}" = ""]?fin)
 same => n,GotoIf($["${{STAT(e,{sounds}/opcion1.wav)}}" = "0"]?espera)
 same => n,Background(farmacias/opcion1)
 same => n,WaitExten(8)
 same => n(espera),WaitExten(8)
 same => n(fin),Hangup()

 same => n(sin_dato),Playback(farmacias/fallback)
 same => n,Hangup()

exten => 1,1,NoOp(IVR IP EMI-MAC desvio farmacia)
 same => n,GotoIf($["${{TELEFONO}}" = ""]?nodial)
 same => n,Dial(Local/${{TELEFONO}}@from-internal/n,60)
 same => n(nodial),Hangup()

exten => i,1,Hangup()
exten => t,1,Hangup()
"""
    config.DIALPLAN_PATH.write_text(content, encoding="utf-8")
    return config.DIALPLAN_PATH


def publish_extension(exten: str) -> tuple[bool, str]:
    try:
        write_dialplan(exten)
    except OSError as exc:
        return False, (
            f"No se pudo escribir {config.DIALPLAN_PATH}: {exc}. "
            "En la central: chown asterisk:asterisk /etc/asterisk/extensions_farmacias.conf"
        )
    if not asterisk.asterisk_available():
        return True, f"Dialplan escrito para el interno {exten} (se recargará en la central)."
    ok, msg = asterisk.reload_dialplan()
    if ok:
        return True, f"Interno {exten} publicado y dialplan recargado."
    return False, msg


def import_csv_text(text: str) -> tuple[int, list[str]]:
    """Importa fecha,farmacia. Crea farmacias faltantes. Devuelve (filas, avisos)."""
    avisos: list[str] = []
    imported = 0
    with db.connect() as conn:
        for raw in text.splitlines():
            line = raw.strip().lstrip("\ufeff").replace("\r", "")
            if not line or line.lower().startswith("fecha"):
                continue
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) < 2:
                continue
            fecha, codigo = parts[0], audio.sanitize_codigo(parts[1])
            if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
                avisos.append(f"Fecha inválida: {fecha}")
                continue
            if not codigo:
                avisos.append(f"Código vacío en {fecha}")
                continue
            if db.get_farmacia_by_codigo(conn, codigo) is None:
                nombre = codigo.replace("_", " ").title()
                db.insert_farmacia(conn, codigo, nombre, "", "")
                avisos.append(f"Se creó la farmacia {nombre} ({codigo})")
            db.set_turno(conn, fecha, codigo)
            imported += 1
    apply_today()
    return imported, avisos
