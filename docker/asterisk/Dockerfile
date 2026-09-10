FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        asterisk \
        asterisk-config \
        ca-certificates \
        tzdata \
        adduser \
    && rm -rf /var/lib/apt/lists/*

COPY docker/asterisk/config/extensions.conf /etc/asterisk/extensions.conf
COPY docker/asterisk/config/rtp.conf /etc/asterisk/rtp.conf
COPY docker/asterisk/config/logger.conf /etc/asterisk/logger.conf
COPY asterisk/extensions_farmacias.conf /etc/asterisk/extensions_farmacias.conf
COPY docker/asterisk/config/pjsip.conf.template /opt/ivr-templates/pjsip.conf.template
COPY docker/asterisk/config/manager.conf.template /opt/ivr-templates/manager.conf.template
COPY docker/asterisk/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p /var/lib/asterisk/sounds/es/farmacias

EXPOSE 5060/udp 5060/tcp 5038/tcp 10000-10100/udp

ENTRYPOINT ["/entrypoint.sh"]
