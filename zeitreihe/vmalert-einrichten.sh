#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# vmalert mit den Aufzeichnungsregeln fuer die Karte (vmalert-regeln.yml,
# karte-vmalert.service). Einzeln aufrufbar, sudo ./vmalert-einrichten.sh;
# zeitreihe/einrichten.sh ruft es am Ende auf. Setzt VictoriaMetrics voraus.
#
# Gibt es die vorberechnete Reihe noch gar nicht, rechnet vmalert die letzten
# acht Tage einmal nach (Replay), damit die Diagramme nicht leer anfangen.
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
REGELN=/etc/victoria-metrics/vmalert-regeln.yml
VM=http://127.0.0.1:8428

echo "== vmalert =="
install -d -m 0755 /etc/victoria-metrics
install -m 0644 "$HIER/vmalert-regeln.yml" "$REGELN"
/usr/bin/vmalert -rule="$REGELN" -dryRun -loggerLevel=ERROR
install -m 0644 "$HIER/karte-vmalert.service" /etc/systemd/system/karte-vmalert.service
systemctl daemon-reload

anzahl=$(curl -sf --get "$VM/api/v1/series" --data-urlencode 'match[]=nf_netz:verkehr_bps' \
	--data-urlencode "start=$(( $(date +%s) - 30 * 86400 ))" \
	| python3 -c 'import json, sys; print(len(json.load(sys.stdin)["data"]))')
if [ "$anzahl" = 0 ]; then
	echo "  nf_netz:verkehr_bps neu, rechne acht Tage nach"
	/usr/bin/vmalert -rule="$REGELN" -datasource.url="$VM" -remoteWrite.url="$VM" \
		-replay.timeFrom="$(date -u -d '8 days ago' +%Y-%m-%dT%H:%M:%SZ)" \
		-replay.timeTo="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		-replay.disableProgressBar -loggerLevel=WARN
else
	echo "  nf_netz:verkehr_bps vorhanden ($anzahl Reihen), kein Nachrechnen"
fi

systemctl enable --quiet karte-vmalert.service
systemctl restart karte-vmalert.service
systemctl is-active karte-vmalert.service
