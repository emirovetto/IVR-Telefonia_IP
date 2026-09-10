#!/bin/bash
# Instala Python 3.9 en /opt/python39 SIN tocar el Python de Issabel (2.7).
# En CentOS 7 / Issabel no hace falta tener python3 de antemano.
#   bash instalar-python39.sh
set -euo pipefail

PYTHON_PREFIX="${PYTHON_PREFIX:-/opt/python39}"
PYTHON_VER="${PYTHON_VER:-3.9.21}"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: ejecute como root (bash instalar-python39.sh)"
    exit 1
fi

log() { echo "  $*" >&2; }

python_is_ok() {
    local bin="$1"
    [[ -x "$bin" ]] || return 1
    # 3.8+ Y módulo ssl (si se compiló sin openssl-devel, pip no habla con PyPI)
    "$bin" -c 'import sys, ssl; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null
}

find_python() {
    local c
    for c in \
        "${PYTHON_PREFIX}/bin/python3.9" \
        /opt/python39/bin/python3.9 \
        /opt/rh/rh-python38/root/usr/bin/python3.8 \
        /opt/rh/rh-python39/root/usr/bin/python3.9 \
        python3.9 python3.8
    do
        if command -v "$c" >/dev/null 2>&1 && python_is_ok "$(command -v "$c")"; then
            command -v "$c"
            return 0
        fi
        if python_is_ok "$c"; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

yum_quiet() {
    yum install -y "$@"
}

_yum_vault_done="${_yum_vault_done:-0}"
ensure_yum_vault() {
    [[ "${_yum_vault_done}" = 1 ]] && return 0
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "${here}/reparar-yum-centos7.sh" ]]; then
        bash "${here}/reparar-yum-centos7.sh" || true
    fi
    _yum_vault_done=1
}

ensure_repos_basicos() {
    log "Instalando herramientas para compilar (gcc, openssl, wget)..."
    yum_quiet ca-certificates curl wget tar gzip which sed
    yum_quiet gcc make openssl-devel bzip2-devel libffi-devel zlib-devel \
        readline-devel sqlite-devel xz-devel
}

try_scl_python() {
    ensure_yum_vault
    log "Intentando Python 3.8 de Software Collections (si el repo responde)..."
    yum_quiet centos-release-scl 2>/dev/null || true
    if yum_quiet rh-python38 rh-python38-python-devel rh-python38-python-pip \
        rh-python38-python-virtualenv 2>/dev/null; then
        python_is_ok /opt/rh/rh-python38/root/usr/bin/python3.8
        return $?
    fi
    return 1
}

compile_python39() {
    local tgz="Python-${PYTHON_VER}.tgz"
    local src="/usr/src/Python-${PYTHON_VER}"
    local url="https://www.python.org/ftp/python/${PYTHON_VER}/${tgz}"

    if python_is_ok "${PYTHON_PREFIX}/bin/python3.9"; then
        return 0
    fi

    log "Compilando Python ${PYTHON_VER} en ${PYTHON_PREFIX} (10-20 min, una sola vez)..."
    ensure_yum_vault
    ensure_repos_basicos
    if ! rpm -q openssl-devel >/dev/null 2>&1; then
        echo "ERROR: no está openssl-devel. Sin eso Python no tiene ssl y pip no funciona."
        echo "Corra primero:  bash reparar-yum-centos7.sh && yum install -y openssl-devel"
        exit 1
    fi
    mkdir -p /usr/src
    if [[ ! -f "/usr/src/${tgz}" ]]; then
        log "Descargando ${url}"
        if ! wget -O "/usr/src/${tgz}" "$url"; then
            echo "ERROR: no se pudo bajar ${url}"
            echo "En una PC con Internet bajá ese archivo y copialo con WinSCP a:"
            echo "  /usr/src/${tgz}"
            echo "Después volvé a correr: bash instalar-python39.sh"
            exit 1
        fi
    fi
    rm -rf "$src" "$PYTHON_PREFIX"
    tar -C /usr/src -xzf "/usr/src/${tgz}"
    (
        cd "$src"
        export CPPFLAGS="-I/usr/include"
        export LDFLAGS="-L/usr/lib64"
        ./configure --prefix="$PYTHON_PREFIX" --with-ensurepip=install --with-openssl=/usr
        make -j"$(nproc 2>/dev/null || echo 2)"
        make altinstall
    )
    if ! python_is_ok "${PYTHON_PREFIX}/bin/python3.9"; then
        echo "ERROR: Python 3.9 quedó sin módulo ssl. Falta openssl-devel al compilar."
        echo "yum install -y openssl-devel   y vuelva a correr este script."
        exit 1
    fi
    log "ssl OK: $("${PYTHON_PREFIX}/bin/python3.9" -c 'import ssl; print(ssl.OPENSSL_VERSION)')"
}

ensure_python() {
    if PYBIN=$(find_python); then
        log "Python OK: $PYBIN ($("$PYBIN" -c 'import sys; print("%d.%d"%sys.version_info[:2])'))"
        echo "$PYBIN"
        return 0
    fi
    log "No hay Python 3.8+ (es normal en Issabel). Se instala uno propio en /opt/python39."
    if try_scl_python && PYBIN=$(find_python); then
        log "Python SCL: $PYBIN"
        echo "$PYBIN"
        return 0
    fi
    compile_python39
    PYBIN=$(find_python) || {
        echo "ERROR: no se pudo instalar Python 3.8+"
        exit 1
    }
    log "Python compilado: $PYBIN"
    echo "$PYBIN"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "IVR IP EMI&MAC — instalar Python 3.9 (no toca el Python de Issabel)"
    echo
    if command -v python >/dev/null 2>&1; then
        log "python del sistema (dejarlo): $(python --version 2>&1)"
    else
        log "No hay 'python' en PATH. yum tiene que seguir funcionando igual."
    fi
    PYBIN="$(ensure_python)"
    echo
    echo "============================================================"
    echo " Python listo: $PYBIN"
    "$PYBIN" --version
    "$PYBIN" -c 'import ssl; print(" ssl:", ssl.OPENSSL_VERSION)'
    echo " No uses /usr/bin/python ni yum install python3."
    echo " Siguiente paso:  bash install-centos7.sh"
    echo "============================================================"
fi
