#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Schreibt die Kennzahlen der Gesamtkarte als kleine JSON-Datei, fuer den
Kasten "Gerade im Netz" auf neanderfunk.de (Anfrage der Content-Session,
04.11.2026). Bis dahin hingen dort zwei Grafana-Bilder vom alten
Kartenserver.

Abrufbar unter https://karte.neanderfunk.de/nf/kennzahlen.json; der Ort /nf/ schickt
schon Access-Control-Allow-Origin * und Cache-Control no-cache. Ein paar
Kilobyte statt der knapp 2 MB meshviewer.json.

Router sind alle Knoten ohne die Supernodes, also Gluon und UniFi-APs, je
node_id einmal. Clients sind die Summe von clients.total dieser Knoten. Quelle
ist VictoriaMetrics, damit Zahl und Verlauf aus derselben Zeitreihe kommen.

Aufgerufen aus karte-kennzahlen.timer, alle fuenf Minuten.
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

QUELLE = 'http://127.0.0.1:8428/api/v1/'
ZIEL = '/var/www/karte-en/api/neander/kennzahlen.json'
KARTE = 'https://karte.neanderfunk.de/'
TAGE = 7
SCHRITT = 3600

ROUTER = ('count(count by (nodeid) '
          '(last_over_time(node_load{db="neander", is_gateway="false"}[10m])))')
CLIENTS = ('sum(max by (nodeid) (last_over_time('
           '{__name__="node_clients.total", db="neander", is_gateway="false"}[10m])))')


def abfrage(art, **param):
    url = QUELLE + art + '?' + urllib.parse.urlencode(param)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)['data']['result']


def jetzt(ausdruck, t):
    r = abfrage('query', query=ausdruck, time=t)
    return int(float(r[0]['value'][1])) if r else None


def verlauf(ausdruck, start, ende):
    r = abfrage('query_range', query=ausdruck, start=start, end=ende, step=SCHRITT)
    return {int(t): int(float(v)) for t, v in (r[0]['values'] if r else [])}


def main():
    t = int(time.time())
    # Raster auf volle Stunden, die letzte davon ist hoechstens eine Stunde alt
    ende = t - t % SCHRITT
    start = ende - TAGE * 86400
    router, clients = verlauf(ROUTER, start, ende), verlauf(CLIENTS, start, ende)
    stand = datetime.datetime.fromtimestamp(t).astimezone()
    daten = {
        'timestamp': stand.isoformat(timespec='seconds'),
        'nodes_online': jetzt(ROUTER, t),
        'clients': jetzt(CLIENTS, t),
        'map': KARTE,
        'series_step': SCHRITT,
        'series': [{'t': s, 'nodes_online': router.get(s), 'clients': clients.get(s)}
                   for s in range(start, ende + 1, SCHRITT)],
    }
    if daten['nodes_online'] is None:
        # Keine aktuellen Werte: die alte Datei bleibt stehen, ihr timestamp
        # zeigt der Seite, dass sie veraltet ist
        print('keine aktuellen Werte aus VictoriaMetrics', file=sys.stderr)
        return 1
    neu = ZIEL + '.neu'
    with open(neu, 'w', encoding='utf-8') as f:
        json.dump(daten, f, separators=(',', ':'))
    os.chmod(neu, 0o644)
    os.replace(neu, ZIEL)
    return 0


if __name__ == '__main__':
    sys.exit(main())
