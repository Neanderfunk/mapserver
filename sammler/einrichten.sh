#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet den Sammler ein. Auf der Karten-VM als root: sudo ./einrichten.sh
# Setzt die Tunnelschicht voraus (../tunnel/einrichten.sh).
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
# Unser Fork: Upstream v1.9.0 plus je Funktion ein Commit, siehe
# NEANDERFUNK.md dort. Die frueheren Patchdateien sind darin aufgegangen.
YANIC_QUELLE=https://github.com/Neanderfunk/yanic
YANIC_ZWEIG=neanderfunk
BAU=/usr/local/src/yanic
WEB=/var/www/karte-en/sites

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[ -f /etc/karte-en/domains.conf ] || { echo "Erst die Tunnelschicht einrichten." >&2; exit 1; }

echo "== Pakete =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq golang-go git

echo "== yanic bauen ($YANIC_QUELLE, Zweig $YANIC_ZWEIG) =="
if [ ! -d "$BAU/.git" ]; then
	git clone -q -b "$YANIC_ZWEIG" "$YANIC_QUELLE" "$BAU"
fi
# Ein Baum von frueher zeigt noch auf Codeberg; auf den Fork umstellen.
git -C "$BAU" remote set-url origin "$YANIC_QUELLE"
# Ausdruecklicher Refspec: ein Klon mit nur einem Zweig legt sonst
# origin/<zweig> fuer andere Zweige nicht an.
git -C "$BAU" fetch -q origin "+refs/heads/$YANIC_ZWEIG:refs/remotes/origin/$YANIC_ZWEIG"
git -C "$BAU" checkout -q --force "origin/$YANIC_ZWEIG"
# Reste der frueheren Patchdateien (unversionierte neue Dateien) entfernen.
git -C "$BAU" clean -fdq
( cd "$BAU" && GOFLAGS=-mod=mod go test ./data/ ./database/influxdb/ ./runtime/ ./output/meshviewer-ffrgb/ )
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
# Adressbuch node_id -> Adressen fuer Sammler ausserhalb, bisher nur neander
install -m 0755 "$HIER/adressbuch.py" /usr/local/sbin/karte-adressbuch
# Clients je Domain aus der Uebersetzungstabelle, genauer als die Summe der
# respondd-Antworten (siehe clients-zaehlen.py)
install -m 0755 "$HIER/clients-zaehlen.py" /usr/local/sbin/karte-clients
[ -f /etc/karte-en/bekannte-macs.conf ] || install -m 0644 "$HIER/bekannte-macs.conf" /etc/karte-en/bekannte-macs.conf
# Einmalig nach dem Aufbau: Erstsichtung aus der aelteren Karte uebernehmen
install -m 0755 "$HIER/erstsichtung-uebernehmen.py" /usr/local/sbin/karte-erstsichtung
install -m 0644 "$HIER/systemd/karte-clients@.service" "$HIER/systemd/karte-clients@.timer" /etc/systemd/system/
install -m 0644 "$HIER/systemd/karte-adressbuch@.service" "$HIER/systemd/karte-adressbuch@.timer" /etc/systemd/system/
# Zeile je Domain alle fuenf Minuten in /var/lib/karte/verlauf.csv (verlauf.py).
# Lief seit 21.09.2026 von Hand installiert; seit 14.10.2026 hier, damit eine
# Neuinstallation es nicht verliert.
install -m 0755 "$HIER/verlauf.py" /usr/local/sbin/karte-verlauf
install -m 0644 "$HIER/systemd/karte-verlauf.service" "$HIER/systemd/karte-verlauf.timer" /etc/systemd/system/
install -d -m 0755 -o yanic -g www-data /var/lib/karte/adressbuch /var/www/karte-en/api
[ -f /etc/karte-en/sitecodes.conf ] || install -m 0644 "$HIER/sitecodes.conf" /etc/karte-en/sitecodes.conf
# Neanderfunk-Domains und site_codes aus den Stammdaten, taeglich (adorfer
# 29.10.2026, E2). Ueberschreibt die neander-Zeilen in domains.conf und die
# ganze sitecodes.conf, siehe stammdaten-uebernehmen.py.
install -m 0755 "$HIER/stammdaten-uebernehmen.py" /usr/local/sbin/karte-stammdaten
install -m 0644 "$HIER/systemd/karte-stammdaten.service" "$HIER/systemd/karte-stammdaten.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now karte-stammdaten.timer

# Communities im Standby (/etc/karte-en/standby.conf) bleiben aus; bis
# 25.10.2026 schaltete jeder Lauf yanic@en wieder ein.
ruhend=$(awk '!/^#/ && NF { print $1 }' /etc/karte-en/standby.conf 2>/dev/null | tr '\n' ' ')
communities=$(awk -v r=" $ruhend" '!/^#/ && NF && index(r, " " $1 " ") == 0 { print $1 }' /etc/karte-en/domains.conf | sort -u)
[ -n "$ruhend" ] && echo "  im Standby, bleiben aus: $ruhend"
for g in $communities; do
	/usr/local/sbin/karte-en-yanic-conf "$g" > "/etc/yanic-$g.conf"
	chmod 0644 "/etc/yanic-$g.conf"
	systemctl enable --now "yanic@$g.service"
done
systemctl enable --now karte-adressbuch@neander.timer karte-clients@neander.timer karte-verlauf.timer
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
