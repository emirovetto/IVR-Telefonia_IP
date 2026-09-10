from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import asterisk, audio, config, db, security, sync
from .bootstrap import bootstrap
from .colors import normalize_color, text_on

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.globals["text_on"] = text_on
templates.env.globals["normalize_color"] = normalize_color

MESES = [
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def create_app() -> FastAPI:
    bootstrap()
    app = FastAPI(title=config.SYSTEM_NAME, docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SECRET_KEY,
        session_cookie="ivr_farmacias",
        same_site="lax",
        max_age=60 * 60 * 12,
    )
    register_routes(app)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
    return app


def flash(request: Request, mensaje: str, tipo: str = "ok") -> None:
    request.session["flash"] = {"mensaje": mensaje, "tipo": tipo}


def pop_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = security.new_csrf()
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, token: str) -> bool:
    expected = request.session.get("csrf", "")
    return security.csrf_ok(expected, token or "")


def require_login(request: Request) -> RedirectResponse | None:
    if request.session.get("user"):
        return None
    nxt = quote(str(request.url.path))
    return RedirectResponse(f"/login?next={nxt}", status_code=303)


def ctx(request: Request, **extra) -> dict:
    with db.connect() as conn:
        extension = db.get_config(conn, "extension", config.DEFAULT_EXTEN)
        password_changed = db.get_config(conn, "password_changed", "0") == "1"
    data = {
        "request": request,
        "user": request.session.get("user"),
        "flash": pop_flash(request),
        "csrf": csrf_token(request),
        "extension": extension,
        "password_changed": password_changed,
        "hoy": date.today().isoformat(),
        "asterisk_ok": asterisk.asterisk_available(),
        "system_name": config.SYSTEM_NAME,
        "nav": extra.pop("nav", ""),
    }
    data.update(extra)
    return data


def parse_month(value: str | None) -> date:
    today = date.today()
    if not value:
        return date(today.year, today.month, 1)
    try:
        year, month = value.split("-")[:2]
        return date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return date(today.year, today.month, 1)


def month_cells(year: int, month: int, asignados: dict) -> list[dict | None]:
    first_weekday, days = monthrange(year, month)
    # monthrange: Monday=0
    cells: list[dict | None] = [None] * first_weekday
    for day in range(1, days + 1):
        fecha = date(year, month, day).isoformat()
        row = asignados.get(fecha)
        color = normalize_color(row["color"]) if row else ""
        cells.append(
            {
                "dia": day,
                "fecha": fecha,
                "codigo": row["farmacia_codigo"] if row else "",
                "nombre": row["nombre"] if row else "",
                "color": color,
                "fg": text_on(color) if row else "",
                "es_hoy": fecha == date.today().isoformat(),
            }
        )
    while len(cells) % 7:
        cells.append(None)
    return cells


def register_routes(app: FastAPI) -> None:
    @app.get("/login", response_class=HTMLResponse)
    async def login_get(request: Request):
        if request.session.get("user"):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=ctx(request, nav="login"),
        )

    @app.post("/login")
    async def login_post(
        request: Request,
        usuario: str = Form(...),
        clave: str = Form(...),
        csrf: str = Form(...),
        next: str = Form("/"),
    ):
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida. Probá de nuevo.", "error")
            return RedirectResponse("/login", status_code=303)
        with db.connect() as conn:
            expected_user = db.get_config(conn, "admin_user", config.DEFAULT_USER)
            stored = db.get_config(conn, "admin_password_hash", "") or ""
        if usuario.strip() != expected_user or not security.verify_password(clave, stored):
            flash(request, "Usuario o contraseña incorrectos.", "error")
            return RedirectResponse("/login", status_code=303)
        request.session["user"] = usuario.strip()
        dest = next if next.startswith("/") else "/"
        return RedirectResponse(dest, status_code=303)

    @app.post("/logout")
    async def logout(request: Request, csrf: str = Form(...)):
        if check_csrf(request, csrf):
            request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def hoy(request: Request):
        denied = require_login(request)
        if denied:
            return denied
        hoy_iso = date.today().isoformat()
        with db.connect() as conn:
            turno = db.get_turno(conn, hoy_iso)
            farmacias = db.list_farmacias(conn)
            proximos = db.proximos(conn, 8)
            extension = db.get_config(conn, "extension", config.DEFAULT_EXTEN)
        astdb = asterisk.db_get("farmacias", "hoy") if asterisk.asterisk_available() else None
        publicado = (astdb or "").strip()
        codigo_hoy = turno["farmacia_codigo"] if turno else ""
        astdb_desfasado = bool(publicado and publicado != "fallback" and publicado != codigo_hoy)
        falta_intro = not audio.audio_exists("intro")
        falta_fallback = not audio.audio_exists("fallback")
        falta_audio_hoy = bool(turno) and not audio.audio_exists(turno["farmacia_codigo"])
        return templates.TemplateResponse(
            request=request,
            name="hoy.html",
            context=ctx(
                request,
                nav="hoy",
                turno=turno,
                farmacias=farmacias,
                proximos=proximos,
                astdb=astdb,
                astdb_desfasado=astdb_desfasado,
                falta_intro=falta_intro,
                falta_fallback=falta_fallback,
                falta_audio_hoy=falta_audio_hoy,
                fecha_larga=_fecha_larga(date.today()),
                extension=extension,
            ),
        )

    @app.post("/hoy/publicar")
    async def hoy_publicar(request: Request, csrf: str = Form(...)):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/", status_code=303)
        ok, msg = sync.apply_today()
        flash(request, msg, "ok" if ok else "error")
        return RedirectResponse("/", status_code=303)

    @app.get("/farmacias", response_class=HTMLResponse)
    async def farmacias(request: Request):
        denied = require_login(request)
        if denied:
            return denied
        with db.connect() as conn:
            items = db.list_farmacias(conn)
            counts = {row["codigo"]: db.count_turnos_farmacia(conn, row["codigo"]) for row in items}
            siguiente_color = db.next_color(conn)
        cards = []
        for row in items:
            color = normalize_color(row["color"] if "color" in row.keys() else None)
            cards.append(
                {
                    **dict(row),
                    "color": color,
                    "fg": text_on(color),
                    "tiene_audio": audio.audio_exists(row["codigo"]),
                    "turnos": counts.get(row["codigo"], 0),
                }
            )
        return templates.TemplateResponse(
            request=request,
            name="farmacias.html",
            context=ctx(request, nav="farmacias", farmacias=cards, siguiente_color=siguiente_color),
        )

    @app.post("/farmacias")
    async def farmacias_crear(
        request: Request,
        nombre: str = Form(...),
        direccion: str = Form(""),
        telefono: str = Form(""),
        codigo: str = Form(""),
        color: str = Form(""),
        csrf: str = Form(...),
        audio_file: UploadFile | None = File(None),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/farmacias", status_code=303)
        nombre = nombre.strip()
        if not nombre:
            flash(request, "El nombre es obligatorio.", "error")
            return RedirectResponse("/farmacias", status_code=303)
        code = audio.sanitize_codigo(codigo) if codigo.strip() else audio.slugify(nombre)
        with db.connect() as conn:
            if db.get_farmacia_by_codigo(conn, code):
                flash(request, f"Ya existe una farmacia con el código {code}.", "error")
                return RedirectResponse("/farmacias", status_code=303)
            db.insert_farmacia(conn, code, nombre, direccion.strip(), telefono.strip(), color)
        if audio_file and audio_file.filename:
            ok, msg = await audio.save_upload(audio_file, code)
            if not ok:
                flash(request, f"Farmacia creada, pero el audio falló: {msg}", "error")
                return RedirectResponse("/farmacias", status_code=303)
        flash(request, f"Farmacia «{nombre}» guardada ({code}).", "ok")
        return RedirectResponse("/farmacias", status_code=303)

    @app.post("/farmacias/{farmacia_id}/editar")
    async def farmacias_editar(
        request: Request,
        farmacia_id: int,
        nombre: str = Form(...),
        direccion: str = Form(""),
        telefono: str = Form(""),
        color: str = Form(""),
        csrf: str = Form(...),
        audio_file: UploadFile | None = File(None),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/farmacias", status_code=303)
        with db.connect() as conn:
            row = db.get_farmacia(conn, farmacia_id)
            if row is None:
                flash(request, "No se encontró esa farmacia.", "error")
                return RedirectResponse("/farmacias", status_code=303)
            db.update_farmacia(conn, farmacia_id, nombre.strip(), direccion.strip(), telefono.strip(), color)
            code = row["codigo"]
        if audio_file and audio_file.filename:
            ok, msg = await audio.save_upload(audio_file, code)
            if not ok:
                flash(request, f"Datos guardados, pero el audio falló: {msg}", "error")
                return RedirectResponse("/farmacias", status_code=303)
        flash(request, "Farmacia actualizada.", "ok")
        with db.connect() as conn:
            hoy = db.get_turno(conn, date.today().isoformat())
        if hoy and hoy["farmacia_codigo"] == code:
            sync.apply_today()
        return RedirectResponse("/farmacias", status_code=303)

    @app.post("/farmacias/{farmacia_id}/borrar")
    async def farmacias_borrar(request: Request, farmacia_id: int, csrf: str = Form(...)):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/farmacias", status_code=303)
        with db.connect() as conn:
            row = db.get_farmacia(conn, farmacia_id)
            if row is None:
                flash(request, "No se encontró esa farmacia.", "error")
                return RedirectResponse("/farmacias", status_code=303)
            db.delete_farmacia(conn, row["codigo"])
        wav = audio.audio_path(row["codigo"])
        wav.unlink(missing_ok=True)
        sync.apply_today()
        flash(request, f"Se eliminó {row['nombre']} y sus turnos.", "ok")
        return RedirectResponse("/farmacias", status_code=303)

    @app.get("/turnos", response_class=HTMLResponse)
    async def turnos(request: Request, mes: str | None = None):
        denied = require_login(request)
        if denied:
            return denied
        inicio = parse_month(mes)
        ultimo = date(inicio.year, inicio.month, monthrange(inicio.year, inicio.month)[1])
        prev_m = (inicio - timedelta(days=1)).replace(day=1)
        if inicio.month == 12:
            next_m = date(inicio.year + 1, 1, 1)
        else:
            next_m = date(inicio.year, inicio.month + 1, 1)
        with db.connect() as conn:
            farmacias = db.list_farmacias(conn)
            asignados = db.turnos_entre(conn, inicio.isoformat(), ultimo.isoformat())
        cells = month_cells(inicio.year, inicio.month, asignados)
        vacios = sum(1 for c in cells if c and not c["codigo"])
        return templates.TemplateResponse(
            request=request,
            name="turnos.html",
            context=ctx(
                request,
                nav="turnos",
                farmacias=farmacias,
                cells=cells,
                dias=DIAS_CORTO,
                mes_titulo=f"{MESES[inicio.month]} {inicio.year}",
                mes_valor=f"{inicio.year:04d}-{inicio.month:02d}",
                prev_mes=f"{prev_m.year:04d}-{prev_m.month:02d}",
                next_mes=f"{next_m.year:04d}-{next_m.month:02d}",
                vacios=vacios,
                dias_mes=monthrange(inicio.year, inicio.month)[1],
            ),
        )

    @app.post("/turnos/asignar")
    async def turnos_asignar(
        request: Request,
        fecha: str = Form(...),
        farmacia_codigo: str = Form(""),
        csrf: str = Form(...),
        mes: str = Form(""),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/turnos", status_code=303)
        back = f"/turnos?mes={mes}" if mes else "/turnos"
        with db.connect() as conn:
            if not farmacia_codigo:
                db.clear_turno(conn, fecha)
                flash(request, f"{fecha}: turno quitado.", "ok")
            elif db.get_farmacia_by_codigo(conn, farmacia_codigo) is None:
                flash(request, "Esa farmacia no existe.", "error")
                return RedirectResponse(back, status_code=303)
            else:
                db.set_turno(conn, fecha, farmacia_codigo)
                flash(request, f"{fecha}: {farmacia_codigo}", "ok")
        if fecha == date.today().isoformat():
            ok, msg = sync.apply_today()
            flash(request, msg, "ok" if ok else "error")
        return RedirectResponse(back, status_code=303)

    @app.post("/turnos/completar")
    async def turnos_completar(
        request: Request,
        mes: str = Form(...),
        farmacia_codigo: str = Form(...),
        csrf: str = Form(...),
        modo: str = Form("vacios"),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/turnos", status_code=303)
        inicio = parse_month(mes)
        days = monthrange(inicio.year, inicio.month)[1]
        with db.connect() as conn:
            if db.get_farmacia_by_codigo(conn, farmacia_codigo) is None:
                flash(request, "Elegí una farmacia válida.", "error")
                return RedirectResponse(f"/turnos?mes={mes}", status_code=303)
            n = 0
            for day in range(1, days + 1):
                fecha = date(inicio.year, inicio.month, day).isoformat()
                existente = db.get_turno(conn, fecha)
                if modo == "vacios" and existente is not None:
                    continue
                db.set_turno(conn, fecha, farmacia_codigo)
                n += 1
        sync.apply_today()
        flash(request, f"Se asignaron {n} días a esa farmacia.", "ok")
        return RedirectResponse(f"/turnos?mes={mes}", status_code=303)

    @app.post("/turnos/rotar")
    async def turnos_rotar(
        request: Request,
        mes: str = Form(...),
        csrf: str = Form(...),
        modo: str = Form("vacios"),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/turnos", status_code=303)
        inicio = parse_month(mes)
        days = monthrange(inicio.year, inicio.month)[1]
        with db.connect() as conn:
            farmacias = db.list_farmacias(conn)
            if not farmacias:
                flash(request, "Primero cargá al menos una farmacia.", "error")
                return RedirectResponse(f"/turnos?mes={mes}", status_code=303)
            n = 0
            for day in range(1, days + 1):
                fecha = date(inicio.year, inicio.month, day).isoformat()
                existente = db.get_turno(conn, fecha)
                if modo == "vacios" and existente is not None:
                    continue
                codigo = farmacias[(day - 1) % len(farmacias)]["codigo"]
                db.set_turno(conn, fecha, codigo)
                n += 1
        sync.apply_today()
        flash(request, f"Se rotaron {n} días entre las farmacias.", "ok")
        return RedirectResponse(f"/turnos?mes={mes}", status_code=303)

    @app.post("/turnos/importar")
    async def turnos_importar(
        request: Request,
        csrf: str = Form(...),
        archivo: UploadFile | None = File(None),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/turnos", status_code=303)
        if not archivo or not archivo.filename:
            flash(request, "Elegí un archivo CSV.", "error")
            return RedirectResponse("/turnos", status_code=303)
        raw = await archivo.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        imported, avisos = sync.import_csv_text(text)
        extra = (" " + "; ".join(avisos[:6])) if avisos else ""
        flash(request, f"Se importaron {imported} días.{extra}", "ok" if imported else "error")
        return RedirectResponse("/turnos", status_code=303)

    @app.get("/turnos/exportar.csv")
    async def turnos_exportar(request: Request):
        denied = require_login(request)
        if denied:
            return denied
        path = sync.export_csv()
        return FileResponse(path, filename="turnos_mensual.csv", media_type="text/csv")

    @app.get("/audios", response_class=HTMLResponse)
    async def audios(request: Request):
        denied = require_login(request)
        if denied:
            return denied
        with db.connect() as conn:
            farmacias = db.list_farmacias(conn)
        items = [
            {
                "codigo": "intro",
                "titulo": "Introducción",
                "detalle": "Se reproduce antes del nombre de la farmacia. Ej: «La farmacia de turno es».",
                "tiene_audio": audio.audio_exists("intro"),
            },
            {
                "codigo": "fallback",
                "titulo": "Sin datos (fallback)",
                "detalle": "Si un día no tiene turno o falta el audio de esa farmacia.",
                "tiene_audio": audio.audio_exists("fallback"),
            },
            {
                "codigo": "opcion1",
                "titulo": "Marque 1 (desvío)",
                "detalle": "Opcional. Después del anuncio: «Para comunicarse, marque 1». Si no está, igual se espera 8 segundos la tecla.",
                "tiene_audio": audio.audio_exists("opcion1"),
            },
        ]
        farm_items = [
            {
                **dict(row),
                "tiene_audio": audio.audio_exists(row["codigo"]),
            }
            for row in farmacias
        ]
        return templates.TemplateResponse(
            request=request,
            name="audios.html",
            context=ctx(request, nav="audios", sistema=items, farmacias=farm_items, ffmpeg=audio.ffmpeg_available()),
        )

    @app.post("/audios/{codigo}")
    async def audios_subir(
        request: Request,
        codigo: str,
        csrf: str = Form(...),
        audio_file: UploadFile | None = File(None),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/audios", status_code=303)
        code = audio.sanitize_codigo(codigo)
        if code not in {"intro", "fallback", "opcion1"}:
            with db.connect() as conn:
                if db.get_farmacia_by_codigo(conn, code) is None:
                    flash(request, "Código de audio no válido.", "error")
                    return RedirectResponse("/audios", status_code=303)
        if not audio_file or not audio_file.filename:
            flash(request, "Elegí un archivo de audio.", "error")
            return RedirectResponse("/audios", status_code=303)
        ok, msg = await audio.save_upload(audio_file, code)
        flash(request, msg if ok else msg, "ok" if ok else "error")
        if ok and code not in {"intro", "fallback", "opcion1"}:
            with db.connect() as conn:
                hoy = db.get_turno(conn, date.today().isoformat())
            if hoy and hoy["farmacia_codigo"] == code:
                sync.apply_today()
        return RedirectResponse("/audios", status_code=303)

    @app.get("/media/{filename}")
    async def media(request: Request, filename: str):
        denied = require_login(request)
        if denied:
            return denied
        name = Path(filename).name
        if not name.endswith(".wav") or ".." in name:
            return RedirectResponse("/", status_code=303)
        path = config.SOUNDS_DIR / name
        if not path.is_file():
            return RedirectResponse("/", status_code=303)
        return FileResponse(path, media_type="audio/wav")

    @app.get("/sistema", response_class=HTMLResponse)
    async def sistema(request: Request):
        denied = require_login(request)
        if denied:
            return denied
        with db.connect() as conn:
            extension = db.get_config(conn, "extension", config.DEFAULT_EXTEN)
            user = db.get_config(conn, "admin_user", config.DEFAULT_USER)
            password_changed = db.get_config(conn, "password_changed", "0") == "1"
        astdb = asterisk.db_get("farmacias", "hoy") if asterisk.asterisk_available() else None
        return templates.TemplateResponse(
            request=request,
            name="sistema.html",
            context=ctx(
                request,
                nav="sistema",
                extension=extension,
                admin_user=user,
                password_changed=password_changed,
                astdb=astdb,
                asterisk_version=asterisk.version() if asterisk.asterisk_available() else "No disponible (desarrollo)",
                context_ok=asterisk.context_loaded(extension or "") if asterisk.asterisk_available() else False,
                sounds_path=str(config.SOUNDS_DIR),
                db_path=str(config.DB_PATH),
                production=config.PRODUCTION,
                ffmpeg=audio.ffmpeg_available(),
            ),
        )

    @app.post("/sistema/extension")
    async def sistema_extension(
        request: Request,
        extension: str = Form(...),
        csrf: str = Form(...),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/sistema", status_code=303)
        digits = "".join(ch for ch in extension if ch.isdigit())
        if not digits:
            flash(request, "El interno solo puede tener números.", "error")
            return RedirectResponse("/sistema", status_code=303)
        try:
            with db.connect() as conn:
                db.set_config(conn, "extension", digits)
            ok, msg = sync.publish_extension(digits)
        except Exception as exc:
            flash(request, f"No se pudo guardar el interno: {exc}", "error")
            return RedirectResponse("/sistema", status_code=303)
        flash(request, msg, "ok" if ok else "error")
        return RedirectResponse("/sistema", status_code=303)

    @app.post("/sistema/clave")
    async def sistema_clave(
        request: Request,
        actual: str = Form(...),
        nueva: str = Form(...),
        repetir: str = Form(...),
        csrf: str = Form(...),
    ):
        denied = require_login(request)
        if denied:
            return denied
        if not check_csrf(request, csrf):
            flash(request, "Sesión vencida.", "error")
            return RedirectResponse("/sistema", status_code=303)
        if nueva != repetir:
            flash(request, "La clave nueva no coincide.", "error")
            return RedirectResponse("/sistema", status_code=303)
        if len(nueva) < 6:
            flash(request, "Usá al menos 6 caracteres.", "error")
            return RedirectResponse("/sistema", status_code=303)
        with db.connect() as conn:
            stored = db.get_config(conn, "admin_password_hash", "") or ""
            if not security.verify_password(actual, stored):
                flash(request, "La clave actual no es correcta.", "error")
                return RedirectResponse("/sistema", status_code=303)
            db.set_config(conn, "admin_password_hash", security.hash_password(nueva))
            db.set_config(conn, "password_changed", "1")
        flash(request, "Contraseña actualizada.", "ok")
        return RedirectResponse("/sistema", status_code=303)


def _fecha_larga(d: date) -> str:
    weekdays = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return f"{weekdays[d.weekday()]} {d.day} de {MESES[d.month]} de {d.year}"


app = create_app()
