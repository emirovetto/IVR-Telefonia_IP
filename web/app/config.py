from __future__ import annotations

import os
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = WEB_ROOT.parent


def _truthy_dir(path: Path) -> bool:
    return path.is_dir()


def production() -> bool:
    env = os.environ.get("IVR_ENV", "").lower()
    if env in {"production", "prod"}:
        return True
    if env in {"development", "dev"}:
        return False
    return _truthy_dir(Path("/etc/asterisk/farmacias"))


PRODUCTION = production()
DATA_DIR = Path(os.environ.get("IVR_DATA_DIR", WEB_ROOT / "data")).resolve()

if PRODUCTION:
    CSV_PATH = Path(os.environ.get("IVR_CSV", "/etc/asterisk/farmacias/turnos_mensual.csv"))
    SOUNDS_DIR = Path(os.environ.get("IVR_SOUNDS", "/var/lib/asterisk/sounds/es/farmacias"))
    DIALPLAN_PATH = Path(os.environ.get("IVR_DIALPLAN", "/etc/asterisk/extensions_farmacias.conf"))
    DB_PATH = Path(os.environ.get("IVR_DB", "/var/lib/ivr-farmacias/ivr.db"))
else:
    CSV_PATH = DATA_DIR / "turnos_mensual.csv"
    SOUNDS_DIR = DATA_DIR / "sounds"
    DIALPLAN_PATH = DATA_DIR / "extensions_farmacias.conf"
    DB_PATH = DATA_DIR / "ivr.db"

SECRET_KEY = os.environ.get("IVR_SECRET", "ivr-farmacias-dev-cambiar")
HOST = os.environ.get("IVR_HOST", "0.0.0.0")
PORT = int(os.environ.get("IVR_PORT", "8787"))
SYSTEM_NAME = os.environ.get("IVR_SYSTEM_NAME", "IVR de turnos")
DEFAULT_EXTEN = os.environ.get("IVR_EXTEN", "8000")
DEFAULT_USER = os.environ.get("IVR_ADMIN_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("IVR_ADMIN_PASSWORD", "admin")
AMI_HOST = os.environ.get("ASTERISK_AMI_HOST", "")
AMI_PORT = int(os.environ.get("ASTERISK_AMI_PORT", "5038"))
AMI_USER = os.environ.get("ASTERISK_AMI_USER", "ivr")
AMI_SECRET = os.environ.get("ASTERISK_AMI_SECRET", "")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIALPLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
