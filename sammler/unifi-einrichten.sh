#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet unifi_respondd ein: UniFi-Accesspoints als Knoten auf der Karte.
# Auf der Karten-VM als root: sudo ./unifi-einrichten.sh
# Setzt den Sammler voraus (./einrichten.sh) und yanic aus dem Fork
# Neanderfunk/yanic, der die Clients der APs beim Router abzieht; mit einem
# anderen yanic zaehlen sie doppelt. Hintergrund: docs/unifi-sites.md.
#
# Vorher die Zugangsdaten ablegen (Lesekonto am Controller), drei Zeilen
# Benutzer, Passwort, Controller-URL:
#   install -d -m 0750 /etc/unifi_respondd
#   install -m 0600 /dev/stdin /etc/unifi_respondd/zugang < zugang
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
QUELLE=https://github.com/Neanderfunk/unifi_respondd
ZWEIG=neanderfunk
BAU=/opt/unifi_respondd
ETC=/etc/unifi_respondd

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[ -s "$ETC/zugang" ] || { echo "Erst $ETC/zugang anlegen (siehe Kopf)." >&2; exit 1; }
[ -f /etc/karte-en/sitecodes.conf ] || { echo "Erst den Sammler einrichten." >&2; exit 1; }

echo "== Pakete =="
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq python3-venv git batctl

echo "== Benutzer und Rechte =="
id -u unifi-respondd >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin unifi-respondd
chown root:unifi-respondd "$ETC"
chmod 0750 "$ETC"
chown root:root "$ETC/zugang"
chmod 0600 "$ETC/zugang"
install -d -m 0755 /var/lib/karte

echo "== unifi_respondd ($QUELLE, Zweig $ZWEIG) =="
if [ ! -d "$BAU/.git" ]; then
	git clone -q -b "$ZWEIG" "$QUELLE" "$BAU"
fi
git -C "$BAU" remote set-url origin "$QUELLE"
git -C "$BAU" fetch -q origin "+refs/heads/$ZWEIG:refs/remotes/origin/$ZWEIG"
git -C "$BAU" checkout -q --force "origin/$ZWEIG"
git -C "$BAU" log --oneline -1
[ -x "$BAU/venv/bin/python" ] || python3 -m venv "$BAU/venv"
"$BAU/venv/bin/pip" install -q --upgrade pip
"$BAU/venv/bin/pip" install -q -r "$BAU/requirements.txt"

echo "== Werkzeuge und Dienste =="
install -m 0755 "$HIER/unifi-respondd-conf.py" /usr/local/sbin/karte-unifi-respondd-conf
install -m 0755 "$HIER/../werkzeug/unifi-offloader.py" /usr/local/sbin/karte-unifi-offloader
install -m 0644 "$HIER/systemd/unifi-respondd.service" /etc/systemd/system/
install -m 0644 "$HIER/systemd/karte-unifi-zuordnung.service" "$HIER/systemd/karte-unifi-zuordnung.timer" /etc/systemd/system/
systemctl daemon-reload

# Erst die Zuordnung AP -> Router, sonst meldet unifi_respondd keinen AP
systemctl start karte-unifi-zuordnung.service
python3 -c "import json; print(len(json.load(open('/var/lib/karte/unifi-zuordnung.json'))['aps']), 'APs mit Router')"
systemctl enable --now karte-unifi-zuordnung.timer
systemctl enable unifi-respondd.service
systemctl restart unifi-respondd.service
sleep 3
systemctl is-active unifi-respondd.service
