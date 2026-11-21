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

# ecdsautils: Signieren des nodeplacer-Manifests (Konzept 4.5). Der
# Schluessel /etc/locator/nodeplacer.secret (root, 0600) entsteht nicht
# hier, sondern einmal von Hand (ecdsakeygen -s); er liegt nur auf der VM.
# Pubkey f7eb4b7d27de7c6ebe36978ef6df9f6865ce00df1cea046991e975bdbb33027d
# (20.11.2026), kommt in die Domain-Datei von 25_hvb.
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ecdsautils >/dev/null
install -d -m 0700 -o root -g root /etc/locator

id locator >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin locator

install -d -m 0755 "$LIB"
install -m 0644 "$HIER/ortung.py" "$HIER/meshids.conf" "$LIB/"
install -m 0755 "$HIER/annahme.py" "$HIER/auswertung.py" "$HIER/manifest.py" \
	"$HIER/orten.py" "$HIER/flaechen.py" "$LIB/"
printf '#!/bin/sh\nexec /usr/bin/python3 %s/auswertung.py "$@"\n' "$LIB" > /usr/local/sbin/locator-auswertung
chmod 0755 /usr/local/sbin/locator-auswertung
printf '#!/bin/sh\nexec /usr/bin/python3 %s/manifest.py "$@"\n' "$LIB" > /usr/local/sbin/locator-manifest
chmod 0755 /usr/local/sbin/locator-manifest
# Teil 2: Positionen (beaconDB, 14 Tage) und Domainflaechen, als Dienstnutzer
install -d -m 0700 -o locator -g locator /var/lib/locator/position
install -d -m 0755 -o locator -g locator /var/lib/locator/flaechen
for u in orten flaechen; do
	printf '#!/bin/sh\nsystemctl start locator-%s.service && journalctl -u locator-%s.service -n 20 -o cat --since -2min\n' "$u" "$u" > /usr/local/sbin/locator-$u
	chmod 0755 /usr/local/sbin/locator-$u
done
# Ausgeliefertes nodeplacer-Manifest (http, Konzept 4.5)
install -d -m 0755 /var/www/locator /var/www/locator/hvb /var/www/locator/hvb/nodeplacer

install -m 0644 "$HIER/locator.service" "$HIER/locator-aufraeumen.service" "$HIER/locator-aufraeumen.timer" \
	"$HIER/locator-manifest.service" "$HIER/locator-manifest.timer" \
	"$HIER/locator-orten.service" "$HIER/locator-flaechen.service" "$HIER/locator-flaechen.timer" \
	/etc/systemd/system/
systemctl daemon-reload
systemctl enable --now locator-aufraeumen.timer
systemctl start locator-flaechen.service
systemctl enable --now locator-flaechen.timer
# Manifest: ohne Schluessel kein Timer (Schluessel entsteht von Hand, s. o.)
if [ -f /etc/locator/nodeplacer.secret ]; then
	systemctl start locator-manifest.service
	systemctl enable --now locator-manifest.timer
fi
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
printf 'Probe GET /hvb/nodeplacer/nodeplacer.manifest: '
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: locator.ffnef.de' http://[::1]/hvb/nodeplacer/nodeplacer.manifest
