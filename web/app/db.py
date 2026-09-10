from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from . import config
from .colors import PALETTE, normalize_color
from .security import hash_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farmacias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    direccion TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#2f6b54',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turnos (
    fecha TEXT PRIMARY KEY,
    farmacia_codigo TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (farmacia_codigo) REFERENCES farmacias(codigo)
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@contextmanager
def connect():
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_config(conn, "extension", config.DEFAULT_EXTEN)
        _ensure_config(conn, "admin_user", config.DEFAULT_USER)
        if get_config(conn, "admin_password_hash") is None:
            set_config(conn, "admin_password_hash", hash_password(config.DEFAULT_PASSWORD))
            set_config(conn, "password_changed", "0")
        _ensure_config(conn, "password_changed", "0")
        _migrate_farmacia_color(conn)


def _ensure_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO config(key, value) VALUES (?, ?)", (key, value))


def get_config(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    # INSERT ... ON CONFLICT no existe en el SQLite 3.7 de CentOS 7 / Issabel
    conn.execute("INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)", (key, value))


def _migrate_farmacia_color(conn: sqlite3.Connection) -> None:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(farmacias)")]
    if "color" not in cols:
        conn.execute("ALTER TABLE farmacias ADD COLUMN color TEXT NOT NULL DEFAULT '#2f6b54'")
    if get_config(conn, "colors_backfilled") == "1":
        return
    rows = list(conn.execute("SELECT id FROM farmacias ORDER BY id"))
    for index, row in enumerate(rows):
        conn.execute(
            "UPDATE farmacias SET color = ? WHERE id = ?",
            (PALETTE[index % len(PALETTE)], row["id"]),
        )
    set_config(conn, "colors_backfilled", "1")


def next_color(conn: sqlite3.Connection) -> str:
    used = {
        normalize_color(row["color"])
        for row in conn.execute("SELECT color FROM farmacias")
        if row["color"]
    }
    for color in PALETTE:
        if color not in used:
            return color
    return PALETTE[len(used) % len(PALETTE)]


def list_farmacias(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM farmacias ORDER BY nombre COLLATE NOCASE"))


def get_farmacia(conn: sqlite3.Connection, farmacia_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM farmacias WHERE id = ?", (farmacia_id,)).fetchone()


def get_farmacia_by_codigo(conn: sqlite3.Connection, codigo: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM farmacias WHERE codigo = ?", (codigo,)).fetchone()


def insert_farmacia(
    conn: sqlite3.Connection,
    codigo: str,
    nombre: str,
    direccion: str,
    telefono: str,
    color: str | None = None,
) -> int:
    stamp = now_iso()
    chosen = normalize_color(color) if color else next_color(conn)
    cur = conn.execute(
        """
        INSERT INTO farmacias (codigo, nombre, direccion, telefono, color, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (codigo, nombre, direccion, telefono, chosen, stamp, stamp),
    )
    return int(cur.lastrowid)


def update_farmacia(
    conn: sqlite3.Connection,
    farmacia_id: int,
    nombre: str,
    direccion: str,
    telefono: str,
    color: str | None = None,
) -> None:
    chosen = normalize_color(color)
    conn.execute(
        """
        UPDATE farmacias
        SET nombre = ?, direccion = ?, telefono = ?, color = ?, updated_at = ?
        WHERE id = ?
        """,
        (nombre, direccion, telefono, chosen, now_iso(), farmacia_id),
    )


def delete_farmacia(conn: sqlite3.Connection, codigo: str) -> None:
    conn.execute("DELETE FROM turnos WHERE farmacia_codigo = ?", (codigo,))
    conn.execute("DELETE FROM farmacias WHERE codigo = ?", (codigo,))


def count_turnos_farmacia(conn: sqlite3.Connection, codigo: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM turnos WHERE farmacia_codigo = ?", (codigo,)
    ).fetchone()
    return int(row["n"]) if row else 0


def get_turno(conn: sqlite3.Connection, fecha: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT t.fecha, t.farmacia_codigo, t.updated_at, f.nombre, f.direccion, f.telefono, f.color
        FROM turnos t
        LEFT JOIN farmacias f ON f.codigo = t.farmacia_codigo
        WHERE t.fecha = ?
        """,
        (fecha,),
    ).fetchone()


def set_turno(conn: sqlite3.Connection, fecha: str, codigo: str) -> None:
    # INSERT ... ON CONFLICT no existe en el SQLite 3.7 de CentOS 7 / Issabel
    conn.execute(
        """
        INSERT OR REPLACE INTO turnos (fecha, farmacia_codigo, updated_at)
        VALUES (?, ?, ?)
        """,
        (fecha, codigo, now_iso()),
    )


def clear_turno(conn: sqlite3.Connection, fecha: str) -> None:
    conn.execute("DELETE FROM turnos WHERE fecha = ?", (fecha,))


def turnos_entre(conn: sqlite3.Connection, desde: str, hasta: str) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT t.fecha, t.farmacia_codigo, f.nombre, f.color
        FROM turnos t
        LEFT JOIN farmacias f ON f.codigo = t.farmacia_codigo
        WHERE t.fecha >= ? AND t.fecha <= ?
        """,
        (desde, hasta),
    ).fetchall()
    return {row["fecha"]: row for row in rows}


def all_turnos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT t.fecha, t.farmacia_codigo, f.nombre
            FROM turnos t
            LEFT JOIN farmacias f ON f.codigo = t.farmacia_codigo
            ORDER BY t.fecha
            """
        )
    )


def proximos(conn: sqlite3.Connection, dias: int = 7) -> list[sqlite3.Row]:
    hoy = date.today().isoformat()
    return list(
        conn.execute(
            """
            SELECT t.fecha, t.farmacia_codigo, f.nombre, f.color
            FROM turnos t
            LEFT JOIN farmacias f ON f.codigo = t.farmacia_codigo
            WHERE t.fecha >= ?
            ORDER BY t.fecha
            LIMIT ?
            """,
            (hoy, dias),
        )
    )
