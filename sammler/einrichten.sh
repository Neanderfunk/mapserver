#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet den Sammler ein. Auf der Karten-VM als root: sudo ./einrichten.sh
# Setzt die Tunnelschicht voraus (../tunnel/einrichten.sh).
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
YANIC_TAG=v1.9.0
BAU=/usr/local/src/yanic
WEB=/var/www/karte-en/sites

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[ -f /etc/karte-en/domains.conf ] || { echo "Erst die Tunnelschicht einrichten." >&2; exit 1; }

echo "== Pakete =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq golang-go git

echo "== yanic bauen ($YANIC_TAG) =="
if [ ! -d "$BAU/.git" ]; then
	git clone -q https://codeberg.org/FreifunkBremen/yanic.git "$BAU"
fi
git -C "$BAU" fetch -q --tags origin
git -C "$BAU" checkout -q --force "$YANIC_TAG"
# Unser einziger Eingriff in yanic: es fragt zusaetzlich Adressen aus einer
# Datei mit. Noetig fuer Netze, die unseren Rundruf nicht an ihre Knoten
# zustellen; siehe patches/yanic-seeds.patch und docs/hintergrund.md.
git -C "$BAU" apply "$HIER/patches/yanic-seeds.patch"
( cd "$BAU" && GOFLAGS=-mod=mod go build -o /usr/local/bin/yanic . )
/usr/local/bin/yanic --version 2>&1 | head -2 || true

echo "== Benutzer und Verzeichnisse =="
id -u yanic >/dev/null 2>&1 || useradd --system --home-dir /var/lib/yanic --shell /usr/sbin/nologin yanic
install -d -m 0755 -o yanic -g www-data /var/lib/yanic "$WEB"
hosts="alle $(awk '!/^#/ && NF { print $5 }' /etc/karte-en/domains.conf)"
for h in $hosts; do
	install -d -m 0755 -o yanic -g www-data "$WEB/$h" "$WEB/$h/data"
done

echo "== Konfiguration und Dienste, je Community einer =="
install -m 0755 "$HIER/yanic-conf.py" /usr/local/sbin/karte-en-yanic-conf
install -m 0755 "$HIER/sitecodes-ermitteln.py" /usr/local/sbin/karte-en-sitecodes
install -m 0755 "$HIER/warten.sh" /usr/local/sbin/karte-en-warten
install -m 0644 "$HIER/systemd/yanic@.service" /etc/systemd/system/
install -m 0755 "$HIER/ziele-ernten.py" /usr/local/sbin/karte-ziele-ernten
install -m 0644 "$HIER/systemd/karte-ziele.service" "$HIER/systemd/karte-ziele.timer" /etc/systemd/system/
[ -f /etc/karte-en/sitecodes.conf ] || install -m 0644 "$HIER/sitecodes.conf" /etc/karte-en/sitecodes.conf
systemctl daemon-reload

communities=$(awk '!/^#/ && NF { print $1 }' /etc/karte-en/domains.conf | sort -u)
for g in $communities; do
	/usr/local/sbin/karte-en-yanic-conf "$g" > "/etc/yanic-$g.conf"
	chmod 0644 "/etc/yanic-$g.conf"
	systemctl enable --now "yanic@$g.service"
done
sleep 20
for g in $communities; do
	printf '  %-10s %s, %s Schnittstellen\n' "$g" \
		"$(systemctl is-active "yanic@$g.service")" \
		"$(grep -c 'respondd.interfaces' "/etc/yanic-$g.conf")"
done
echo
echo "== erste Daten =="
for h in $hosts; do
	f="$WEB/$h/data/meshviewer.json"
	if [ -s "$f" ]; then
		printf '  %-14s %8s Byte\n' "$h" "$(stat -c %s "$f")"
	else
		printf '  %-14s noch nichts\n' "$h"
	fi
done
