#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Zeitreihen der respondd-Werte: yanic -> VictoriaMetrics, lesend per
# Prometheus-API unter https://<community>.map.freifunk.space/nf/prom/.
# Auf der Karten-VM als root: sudo ./einrichten.sh
# Setzt Sammler und Web voraus. Welche Community schreibt, steht in
# sammler/yanic-conf.py (ZEITREIHE).
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

echo "== VictoriaMetrics =="
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq victoria-metrics
install -d -m 0755 /etc/victoria-metrics
install -m 0644 "$HIER/relabel.yml" /etc/victoria-metrics/relabel.yml
install -m 0644 "$HIER/victoria-metrics.default" /etc/default/victoria-metrics
# Schluessel fuer die Verwaltungsfunktionen, einmal erzeugt und dann behalten
if [ ! -f /etc/victoria-metrics/geheim.env ]; then
	schluessel=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)
	geheim=''
	for f in deleteAuthKey flagsAuthKey metricsAuthKey pprofAuthKey reloadAuthKey \
		snapshotAuthKey forceMergeAuthKey forceFlushAuthKey configAuthKey \
		search.resetCacheAuthKey; do
		geheim="$geheim -$f=$schluessel"
	done
	( umask 077; printf 'GEHEIM="%s"\n' "${geheim# }" > /etc/victoria-metrics/geheim.env )
fi
install -d -m 0755 /etc/systemd/system/victoria-metrics.service.d
install -m 0644 "$HIER/victoria-metrics-schluessel.conf" /etc/systemd/system/victoria-metrics.service.d/schluessel.conf
systemctl daemon-reload
systemctl enable victoria-metrics
systemctl restart victoria-metrics
for i in $(seq 1 20); do
	curl -sf http://127.0.0.1:8428/ping >/dev/null 2>&1 && break
	curl -sf -o /dev/null http://127.0.0.1:8428/health && break
	sleep 1
done
curl -sf -o /dev/null http://127.0.0.1:8428/health && echo "  laeuft auf 127.0.0.1:8428"

echo "== Grafana =="
# Nur die Vertiefung hinter dem Link im Knotenfenster. Die Karte selbst
# zeichnet ihre Diagramme ohne Grafana.
if ! dpkg -s grafana >/dev/null 2>&1; then
	install -d -m 0755 /etc/apt/keyrings
	curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
	echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
		> /etc/apt/sources.list.d/grafana.list
	apt-get update -qq
	apt-get install -y -qq grafana
fi
install -d -m 0755 /etc/systemd/system/grafana-server.service.d /var/lib/grafana/dashboards
install -m 0644 "$HIER/grafana/systemd-dropin.conf" /etc/systemd/system/grafana-server.service.d/neanderfunk.conf
install -m 0644 "$HIER/grafana/datasource.yaml" /etc/grafana/provisioning/datasources/victoriametrics.yaml
install -m 0644 "$HIER/grafana/dashboards.yaml" /etc/grafana/provisioning/dashboards/neanderfunk.yaml
python3 "$HIER/grafana/dashboard-erzeugen.py" > /var/lib/grafana/dashboards/knoten.json
python3 "$HIER/grafana/dashboard-erzeugen.py" supernode > /var/lib/grafana/dashboards/supernode.json
python3 "$HIER/grafana/dashboard-erzeugen.py" domain > /var/lib/grafana/dashboards/domain.json
python3 "$HIER/grafana/dashboard-erzeugen.py" community > /var/lib/grafana/dashboards/community.json
chown -R grafana:grafana /var/lib/grafana/dashboards
systemctl daemon-reload
systemctl enable grafana-server
systemctl restart grafana-server

echo "== nginx =="
install -d -m 0755 /etc/nginx/karte-en
for g in $(python3 -c "import sys; sys.path.insert(0, '$HIER/../sammler'); exec(open('$HIER/../sammler/yanic-conf.py').read().split('def gemeldete_codes')[0]); print(' '.join(ZEITREIHE))"); do
	install -m 0644 "$HIER/nginx-prom.conf" "/etc/nginx/karte-en/prom-$g.conf"
	echo "  /nf/prom/ fuer $g"
done
nginx -t
systemctl reload nginx

echo "== yanic neu, damit er den Influx-Ausgang aufnimmt =="
install -m 0755 "$HIER/../sammler/yanic-conf.py" /usr/local/sbin/karte-en-yanic-conf
install -m 0644 "$HIER/../sammler/systemd/yanic@.service" /etc/systemd/system/
systemctl daemon-reload
for d in $(systemctl list-units --no-legend 'yanic@*.service' | awk '{ print $1 }'); do
	systemctl restart "$d"
done
