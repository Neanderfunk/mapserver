#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Schreibt die Bandbreite je Neanderfunk-Domain als JSON-Datei, damit ein
Skript die Domains nach Last auf die Supernodes verteilen kann, ohne Zugang
zu Checkmk (Anfrage der Supernode-Session, 04.11.2026; adorfer gab die
Veroeffentlichung frei, das Grafana zeigt dieselben Werte ohnehin oeffentlich).

Abrufbar unter https://map.ffnef.de/nf/traffic-domaenen.json.

Quelle sind die Batman-Zaehler traffic.rx.bytes und traffic.tx.bytes, die die
Gateway-Instanzen der Supernodes per respondd melden (yanic sammelt sie alle
fuenf Minuten nach VictoriaMetrics). Die Domain kommt aus der node_id
f2beef00<NN><SS>, NN = Domain, SS = Supernode; die Labels domain und hostname
haben ihr Format mehrfach gewechselt, die node_id nicht.

Je Domain: rx+tx in Mbit/s, summiert ueber alle Gateway-Instanzen, je
30-Minuten-Raster die Spitze der 5-Minuten-Werte (nicht das Mittel), 14 Tage
rueckwaerts. Ein Punkt mit Zeitstempel t deckt (t-30min, t] ab. Fehlende
Werte stehen als null.

Aufgerufen aus karte-traffic-domaenen.timer, taeglich. Mit Argument "-" geht
die Ausgabe auf stdout statt in die Datei.
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

QUELLE = 'http://127.0.0.1:8428/api/v1/'
ZIEL = '/var/www/karte-en/api/neander/traffic-domaenen.json'
TAGE = 14
SCHRITT = 1800

# Summe je Domain im 5-Minuten-Takt, davon das Maximum je 30 Minuten
GW = 'db="neander", is_gateway="true", nodeid=~"f2beef00[0-9]{4}"'
SUMME = ('sum by (nn) (label_replace('
         'rate({__name__="node_traffic.rx.bytes", %(gw)s}[5m]) + '
         'rate({__name__="node_traffic.tx.bytes", %(gw)s}[5m]), '
         '"nn", "$1", "nodeid", "f2beef00([0-9]{2})[0-9]{2}"))') % {'gw': GW}
AUSDRUCK = 'max_over_time((%s)[%ds:300s]) * 8 / 1e6' % (SUMME, SCHRITT)


def abfrage(art, **param):
    url = QUELLE + art + '?' + urllib.parse.urlencode(param)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)['data']['result']


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime(
        '%Y-%m-%dT%H:%M:%SZ')


def main():
    t = int(time.time())
    ende = t - t % SCHRITT
    start = ende - TAGE * 86400
    raster = range(start, ende + 1, SCHRITT)
    domains = {}
    for reihe in abfrage('query_range', query=AUSDRUCK, start=start, end=ende,
                         step=SCHRITT):
        nn = reihe['metric'].get('nn')
        if not nn:
            continue
        werte = {int(float(s)): round(float(v), 1) for s, v in reihe['values']}
        domains[nn] = {'step': SCHRITT, 'start': iso(start),
                       'mbit': [werte.get(s) for s in raster]}
    if not domains:
        # Keine Werte: die alte Datei bleibt stehen, "erzeugt" zeigt ihr Alter
        print('keine Werte aus VictoriaMetrics', file=sys.stderr)
        return 1
    daten = {
        'erzeugt': iso(t),
        'quelle': ('respondd der Supernode-Gateways, traffic.rx+tx.bytes, '
                   'Summe je Domain, Spitze der 5-min-Werte je 30 min, Mbit/s'),
        **{nn: domains[nn] for nn in sorted(domains)},
    }
    if sys.argv[1:] == ['-']:
        json.dump(daten, sys.stdout, separators=(',', ':'))
        return 0
    neu = ZIEL + '.neu'
    with open(neu, 'w', encoding='utf-8') as f:
        json.dump(daten, f, separators=(',', ':'))
    os.chmod(neu, 0o644)
    os.replace(neu, ZIEL)
    return 0


if __name__ == '__main__':
    sys.exit(main())
