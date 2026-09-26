#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet das Service-Menue der neander-Karte ein (service.py). Auf der
# Karten-VM als root: sudo ./einrichten.sh
# Die Anmeldung davor erledigt nginx per auth_request beim Authentik-Outpost
# (web/konfig-erzeugen.py, nur der Vhost neander.map.freifunk.space).
set -euo pipefail
HIER=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

id -u karte-service >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --gid yanic karte-service
# Gemeinsames Verzeichnis mit yanic: der Dienst schreibt Aliase und
# Loeschauftraege, yanic liest die Aliase und loescht erledigte Auftraege.
install -d -m 2775 -o karte-service -g yanic /var/lib/karte/service /var/lib/karte/service/remove-neander
[ -f /var/lib/karte/service/aliases-neander.json ] || \
	install -m 0664 -o karte-service -g yanic /dev/null /var/lib/karte/service/aliases-neander.json
[ -s /var/lib/karte/service/aliases-neander.json ] || echo '{}' > /var/lib/karte/service/aliases-neander.json

install -d -m 0755 /usr/local/lib/karte-service
install -m 0644 "$HIER/service.py" /usr/local/lib/karte-service/service.py
install -m 0644 "$HIER/karte-service.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q karte-service
systemctl restart karte-service
sleep 2
systemctl is-active karte-service
