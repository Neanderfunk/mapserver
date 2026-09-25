#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet mesh-announce ein: der Kartenserver beantwortet respondd in jedem
# Mesh, in dem er haengt, als eigener Knoten (map-neanderfunk-<code>, Kontakt
# projekt@neanderfunk.de). Sonst ist er fuer andere Karten ein dunkler Knoten.
# Auf der Karten-VM als root: sudo ./mesh-announce-einrichten.sh
#
# Teilt sich Port 1001 mit unifi_respondd; beide setzen SO_REUSEADDR (unser
# Fork ab ff9999c).
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
QUELLE=https://github.com/ffnord/mesh-announce
STAND=40be9a18ee91fa058478bc04105cbd79fd70279e   # ffnord master, 26.09.2026
BAU=/opt/mesh-announce

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq python3-psutil lsb-release batctl git

if [ ! -d "$BAU/.git" ]; then
	git clone -q "$QUELLE" "$BAU"
fi
git -C "$BAU" fetch -q origin
git -C "$BAU" checkout -q --force "$STAND"
git -C "$BAU" log --oneline -1

install -d -m 0755 /etc/mesh-announce
install -m 0755 "$HIER/mesh-announce-conf.py" /usr/local/sbin/karte-mesh-announce-conf
install -m 0644 "$HIER/systemd/mesh-announce.service" /etc/systemd/system/
install -m 0755 "$HIER/../tunnel/waechter.sh" /usr/local/sbin/karte-en-waechter
systemctl daemon-reload
systemctl enable mesh-announce.service
systemctl restart mesh-announce.service
sleep 3
systemctl is-active mesh-announce.service
grep -c '^\[' /etc/mesh-announce/respondd.conf | sed 's/^/Abschnitte (mit Defaults): /'
