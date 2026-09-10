#!/bin/bash
set -euo pipefail

ISSABEL_HOST="${ISSABEL_HOST:?Defina ISSABEL_HOST (IP de la central Issabel)}"
TRUNK_USER="${TRUNK_USER:-ivrturnos}"
TRUNK_SECRET="${TRUNK_SECRET:?Defina TRUNK_SECRET}"
AMI_USER="${AMI_USER:-ivr}"
AMI_SECRET="${AMI_SECRET:?Defina AMI_SECRET}"

replace() {
    local src="$1"
    local dst="$2"
    sed \
        -e "s|__ISSABEL_HOST__|${ISSABEL_HOST}|g" \
        -e "s|__TRUNK_USER__|${TRUNK_USER}|g" \
        -e "s|__TRUNK_SECRET__|${TRUNK_SECRET}|g" \
        -e "s|__AMI_USER__|${AMI_USER}|g" \
        -e "s|__AMI_SECRET__|${AMI_SECRET}|g" \
        "$src" > "$dst"
}

replace /opt/ivr-templates/pjsip.conf.template /etc/asterisk/pjsip.conf
replace /opt/ivr-templates/manager.conf.template /etc/asterisk/manager.conf

if ! grep -q '^languageprefix' /etc/asterisk/asterisk.conf 2>/dev/null; then
    printf '\n[options]\nlanguageprefix = yes\n' >> /etc/asterisk/asterisk.conf
fi

if ! grep -q 'noload => chan_sip.so' /etc/asterisk/modules.conf 2>/dev/null; then
    echo "noload => chan_sip.so" >> /etc/asterisk/modules.conf
fi

mkdir -p /var/lib/asterisk/sounds/es/farmacias /var/log/asterisk /var/run/asterisk
chown -R asterisk:asterisk /etc/asterisk /var/lib/asterisk /var/log/asterisk /var/run/asterisk /var/spool/asterisk || true

exec asterisk -f -vvv
