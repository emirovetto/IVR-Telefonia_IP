from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from fastapi import UploadFile

from . import config

ALLOWED_SUFFIX = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".wma", ".gsm"}


def slugify(nombre: str) -> str:
    normalized = unicodedata.normalize("NFKD", nombre)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name.lower()).strip("_")
    if not slug:
        slug = "farmacia"
    if not slug.startswith("farmacia_"):
        slug = f"farmacia_{slug}"
    return slug[:80]


def sanitize_codigo(codigo: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", codigo.strip().lower())
    return cleaned[:80]


def sanitize_phone(value: str) -> str:
    """Dígitos como se marcarían desde un interno de Issabel."""
    digits = re.sub(r"[^0-9]", "", value or "")
    if len(digits) < 6:
        return ""
    return digits[:20]


def audio_path(codigo: str) -> Path:
    return config.SOUNDS_DIR / f"{codigo}.wav"


def audio_exists(codigo: str) -> bool:
    return audio_path(codigo).is_file()


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def sox_available() -> bool:
    return shutil.which("sox") is not None


def convert_to_asterisk_wav(source: Path, dest: Path) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if ffmpeg_available():
        completed = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ar",
                "8000",
                "-ac",
                "1",
                "-sample_fmt",
                "s16",
                str(dest),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "ffmpeg falló").strip()
            return False, err[-400:]
        return True, "convertido a WAV 8 kHz mono"

    # CentOS 7 / Issabel: sox suele estar; ffmpeg a menudo no
    if sox_available():
        completed = subprocess.run(
            ["sox", str(source), "-r", "8000", "-c", "1", "-b", "16", str(dest)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "sox falló").strip()
            if source.suffix.lower() == ".wav":
                shutil.copyfile(source, dest)
                return True, "sox no pudo convertir: se copió el WAV (grabe en 8 kHz mono si puede)"
            return False, err[-400:]
        return True, "convertido a WAV 8 kHz mono (sox)"

    if source.suffix.lower() == ".wav":
        shutil.copyfile(source, dest)
        return True, "sin ffmpeg/sox: se copió el WAV sin convertir"
    return False, "No hay ffmpeg ni sox. Suba un WAV 8 kHz mono o instale sox (yum install sox)."


async def save_upload(upload: UploadFile, codigo: str) -> tuple[bool, str]:
    if not upload.filename:
        return False, "No se eligió ningún archivo"
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        return False, f"Formato no permitido ({suffix or 'sin extensión'}). Use WAV, MP3, OGG o M4A."

    config.ensure_dirs()
    data = await upload.read()
    if not data:
        return False, "El archivo está vacío"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        ok, msg = convert_to_asterisk_wav(tmp_path, audio_path(codigo))
        return ok, msg
    finally:
        tmp_path.unlink(missing_ok=True)
