#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# HVB-Ortung (locator.ffnef.de) auf map6 einrichten, Prototyp.
# Als root: sudo ./locator/einrichten.sh
#
# Annahme (annahme.py) als Dienst locator an 127.0.0.1:8781, nginx davor
# (nginx-locator.conf), Ablage /var/lib/locator/eingang (0700), Loeschen
# nach 14 Tagen per Timer, Auswertung: sudo locator-auswertung
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
LIB=/usr/local/lib/locator

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

id locator >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin locator

install -d -m 0755 "$LIB"
install -m 0644 "$HIER/ortung.py" "$HIER/meshids.conf" "$LIB/"
install -m 0755 "$HIER/annahme.py" "$HIER/auswertung.py" "$LIB/"
printf '#!/bin/sh\nexec /usr/bin/python3 %s/auswertung.py "$@"\n' "$LIB" > /usr/local/sbin/locator-auswertung
chmod 0755 /usr/local/sbin/locator-auswertung

install -m 0644 "$HIER/locator.service" "$HIER/locator-aufraeumen.service" "$HIER/locator-aufraeumen.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now locator-aufraeumen.timer
systemctl enable locator.service
systemctl restart locator.service
install -d -m 0700 -o locator -g locator /var/lib/locator/eingang

install -m 0644 "$HIER/nginx-locator-log.conf" /etc/nginx/conf.d/karte-locator-log.conf
install -m 0644 "$HIER/nginx-locator.conf" /etc/nginx/sites-available/locator.conf
ln -sf /etc/nginx/sites-available/locator.conf /etc/nginx/sites-enabled/locator.conf
nginx -t
systemctl reload nginx

sleep 1
systemctl is-active locator.service
printf 'Probe GET /hvb/locate: '
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: locator.ffnef.de' http://[::1]/hvb/locate
