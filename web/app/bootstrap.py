from __future__ import annotations

from . import config
from . import db as database
from .db import init_db
from .sync import write_dialplan


def bootstrap() -> None:
    config.ensure_dirs()
    init_db()
    with database.connect() as conn:
        exten = database.get_config(conn, "extension", config.DEFAULT_EXTEN) or config.DEFAULT_EXTEN
        n_turnos = conn.execute("SELECT COUNT(*) AS n FROM turnos").fetchone()["n"]
    if not config.DIALPLAN_PATH.exists():
        write_dialplan(exten)
    if n_turnos == 0:
        _importar_csv_legado()


def _importar_csv_legado() -> None:
    """Una sola vez: si hay un CSV viejo y el panel aún no tiene turnos."""
    path = config.CSV_PATH
    if not path.is_file() or path.stat().st_size < 24:
        return
    text = path.read_text(encoding="utf-8-sig")
    if "fecha" not in text.splitlines()[0].lower():
        return
    from .sync import import_csv_text

    import_csv_text(text)
