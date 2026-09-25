#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Baut meshviewer und richtet die neun Vhosts ein.
# Auf der Karten-VM als root: sudo ./einrichten.sh
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
# Unser Fork von freifunk/meshviewer, Zweig neanderfunk: Upstream-Stand plus
# unsere Aenderungen, je Funktion ein Commit (NEANDERFUNK.md im Fork). Bis
# 25.09.2026 war das eine Patchdatei in diesem Repo; mit Frontend-Code wurde
# daraus ein Fork, damit sich Aenderungen einzeln nachziehen lassen.
MV_QUELLE=https://github.com/Neanderfunk/meshviewer
MV_ZWEIG=neanderfunk
BILDER_QUELLE=https://github.com/freifunk/device-pictures
BAU=/usr/local/src/meshviewer
BILDER=/usr/local/src/device-pictures
WEB=/var/www/karte-en

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[ -f /etc/karte-en/domains.conf ] || { echo "Erst die Tunnelschicht einrichten." >&2; exit 1; }

echo "== Pakete =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nodejs npm git nginx
node --version

echo "== meshviewer bauen =="
if [ ! -d "$BAU/.git" ]; then
	git clone -q --depth 50 -b "$MV_ZWEIG" "$MV_QUELLE" "$BAU"
fi
# Ein Baum, der noch auf das Original zeigt, wird umgestellt
git -C "$BAU" remote set-url origin "$MV_QUELLE"
# Mit ausdruecklicher Zielreferenz: ein Baum, der als Einzelzweig geklont
# wurde, legt sonst fuer einen anderen Zweig kein origin/<zweig> an, und der
# Checkout scheitert (so am 25.09.2026 beim Umstieg von main auf neanderfunk).
git -C "$BAU" fetch -q origin "+refs/heads/$MV_ZWEIG:refs/remotes/origin/$MV_ZWEIG"
git -C "$BAU" checkout -q --force "origin/$MV_ZWEIG"
echo "  Stand: $(git -C "$BAU" log -1 --format='%h %ad %s' --date=short)"
( cd "$BAU" && npm install --no-audit --no-fund --loglevel=error && npm run build )
install -d -m 0755 "$WEB/meshviewer"
rsync -rlt --delete "$BAU/build/" "$WEB/meshviewer/"

# Eigene Regeln in die gebaute Seite einfuegen. Der Build wird dabei nicht
# angefasst, die Ergaenzung ueberlebt also jeden Neubau, und sie steht inline,
# damit kein zweiter Abruf noetig ist.
python3 - "$HIER/eigenes.css" "$WEB/meshviewer/index.html" <<'PY'
import sys
css, seite = open(sys.argv[1], encoding='utf-8').read(), sys.argv[2]
t = open(seite, encoding='utf-8').read()
marke = '<!-- mapserver:eigenes -->'
if marke not in t and '</head>' in t:
    t = t.replace('</head>', f'{marke}\n<style>\n{css}</style>\n</head>', 1)
    open(seite, 'w', encoding='utf-8').write(t)
    print('  eigene CSS-Regeln eingefuegt')
else:
    print('  eigene CSS-Regeln schon vorhanden oder kein </head>')
PY

echo "== Geraetebilder =="
# Lokal ausliefern statt von github.io: keine fremden Anfragen aus dem Browser.
if [ ! -d "$BILDER/.git" ]; then
	git clone -q --depth 1 "$BILDER_QUELLE" "$BILDER"
fi
git -C "$BILDER" pull -q --ff-only || true
if [ -d "$BILDER/pictures-svg" ]; then
	install -d -m 0755 "$WEB/pictures-svg"
	rsync -rlt --delete "$BILDER/pictures-svg/" "$WEB/pictures-svg/"
	echo "  $(find "$WEB/pictures-svg" -name '*.svg' | wc -l) Bilder"
fi

echo "== Konfigurationen =="
install -m 0755 "$HIER/konfig-erzeugen.py" /usr/local/sbin/karte-en-konfig
# Communities im Standby: nur anlegen, wenn es die Datei noch nicht gibt,
# sonst ueberschreibt ein Lauf den Betriebszustand.
[ -f /etc/karte-en/standby.conf ] || install -m 0644 "$HIER/standby.conf" /etc/karte-en/standby.conf
/usr/local/sbin/karte-en-konfig
chown -R yanic:www-data "$WEB/sites"
find "$WEB/sites" -name config.json -exec chmod 0644 {} +

echo "== nginx =="
install -m 0644 "$HIER/nginx-hash.conf" /etc/nginx/conf.d/karte-hash.conf
install -m 0644 "$HIER/nginx-geo.conf" /etc/nginx/conf.d/karte-geo.conf
install -d -m 0700 -o www-data /var/cache/nginx/karte-geo
ln -sf /etc/nginx/sites-available/karte-en.conf /etc/nginx/sites-enabled/karte-en.conf
nginx -t
systemctl reload nginx
echo
echo "== Probe =="
for h in en.map.freifunk.space witten.en.map.freifunk.space; do
	printf '  %-34s %s\n' "$h" \
		"$(curl -s -o /dev/null -w '%{http_code} %{size_download}B' -H "Host: $h" http://[::1]/)"
done
