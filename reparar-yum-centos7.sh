#!/bin/bash
# CentOS 7 ya no tiene mirrors. Este script apunta yum a vault.centos.org
# y, si hace falta, agrega DNS 8.8.8.8. No toca los repos de Issabel.
#   bash reparar-yum-centos7.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: ejecute como root"
    exit 1
fi

log() { echo "  $*"; }

if [[ ! -d /etc/yum.repos.d ]]; then
    echo "ERROR: no es un sistema yum"
    exit 1
fi

# Copia de seguridad una sola vez
if [[ ! -d /etc/yum.repos.d.bak-ivr ]]; then
    mkdir -p /etc/yum.repos.d.bak-ivr
    cp -a /etc/yum.repos.d/*.repo /etc/yum.repos.d.bak-ivr/ 2>/dev/null || true
    log "Backup de repos en /etc/yum.repos.d.bak-ivr"
fi

# DNS: mirrorlist.centos.org está muerto; a veces el resolver de la central no resuelve nada
if ! ping -c 1 -W 3 vault.centos.org >/dev/null 2>&1; then
    if ! grep -q '8.8.8.8' /etc/resolv.conf 2>/dev/null; then
        log "No resuelve vault.centos.org: agrego nameserver 8.8.8.8"
        echo "nameserver 8.8.8.8" >> /etc/resolv.conf
    fi
fi

# Solo archivos CentOS (no Issabel, EPEL propio, etc.)
shopt -s nullglob
for repo in /etc/yum.repos.d/CentOS-*.repo /etc/yum.repos.d/CentOS-SCLo-*.repo; do
    [[ -f "$repo" ]] || continue
    # Desactivar mirrorlist (ya no existe)
    sed -i -e 's/^mirrorlist=/#mirrorlist=/g' \
           -e 's/^#baseurl=/baseurl=/g' \
           -e 's|mirror.centos.org/centos/$releasever|vault.centos.org/centos/7|g' \
           -e 's|mirror.centos.org/centos/7|vault.centos.org/centos/7|g' \
           -e 's|mirror.centos.org|vault.centos.org|g' \
           -e 's|mirrorlist.centos.org|#mirrorlist.centos.org|g' \
           "$repo"
    log "Vault: $(basename "$repo")"
done
shopt -u nullglob

yum clean all >/dev/null 2>&1 || true

log "Probando yum contra Vault..."
if yum --disablerepo='*' --enablerepo=base,updates,extras makecache fast 2>/dev/null \
    || yum makecache fast; then
    echo
    echo "yum OK. Siguiente:"
    echo "  bash instalar-python39.sh"
    echo "  bash install-centos7.sh"
    exit 0
fi

echo
echo "ERROR: yum sigue sin poder bajar paquetes."
echo "Comprobá Internet desde la central:"
echo "  ping -c 2 8.8.8.8"
echo "  ping -c 2 vault.centos.org"
echo "  ping -c 2 www.python.org"
exit 1
