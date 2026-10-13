#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Zeitreihen der alten Karte (map.eulenfunk.de) in unser VictoriaMetrics.

  altkarte-uebernehmen.py [--jobs nef01vel,...] [--trocken]

Die alte Karte sammelt seit Jahren per Prometheus; ihr Grafana reicht
lesende Abfragen ohne Anmeldung durch (Datasource-Proxy, nur query und
query_range). Prometheus haelt dort rund 98 Tage vor. Unsere eigenen
Zeitreihen beginnen am 22.09.2026; alles davor holt dieses Skript, soweit es
noch da ist (adorfer 14.10.2026). An der alten Karte aendert es nichts.

Uebernommen wird nur Neanderfunk (Jobs nef*), umgerechnet auf unsere Namen
und Einheiten, mit dem Label quelle="altkarte". Damit lassen sich die Reihen
restlos wieder entfernen, ohne eigene Daten zu beruehren:

  curl -X POST -H "Authorization: ..." \\
    'http://127.0.0.1:8428/api/v1/admin/tsdb/delete_series?match[]={quelle="altkarte"}'

Schritt 5 Minuten wie unser collect_interval. Ende ist ENDE, der Beginn
unserer eigenen Reihen; davor gibt es keine Ueberschneidung.

Nicht uebertragbar: Speicher und Flash (alt nur als Anteil), alles aus
neanderfunk-respondd und der Clientzaehlung aus batman (gab es vorher nicht).
"""
import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request

ALT = 'https://map.eulenfunk.de/stats/api/datasources/proxy/1/api/v1'
NEU = 'http://127.0.0.1:8428/api/v1/import'
ENDE = 1790094300            # erster Wert in unserem VictoriaMetrics, 22.09.2026
SCHRITT = 300
STUECK = 30 * 86400          # query_range liefert hoechstens 11000 Punkte je Reihe
PAUSE = 1.0                  # zwischen zwei Abfragen; die alte Karte ist in Betrieb

KNOTEN = ('nodeid', 'hostname', 'model', 'site')
BEI = 'nodeid,hostname,model,site'


def reihen(job):
    """(neuer Name, PromQL gegen die alte Karte, Labelumbenennung)"""
    j = f'job="{job}"'
    r = [
        ('node_clients.total', f'statistics_clients_total{{{j}}}', None),
        ('node_clients.wifi', f'statistics_clients_wifi{{{j}}}', None),
        ('node_clients.wifi24', f'statistics_clients_wifi24{{{j}}}', None),
        ('node_clients.wifi5', f'statistics_clients_wifi5{{{j}}}', None),
        ('node_load', f'statistics_loadavg{{{j}}}', None),
        ('node_time.up', f'statistics_uptime{{{j}}}', None),
        ('node_traffic.rx.bytes', f'statistics_traffic{{{j},mtype="user",type="rx"}}', None),
        ('node_traffic.tx.bytes', f'statistics_traffic{{{j},mtype="user",type="tx"}}', None),
        ('node_traffic.forward.bytes', f'statistics_traffic{{{j},type="forward"}}', None),
        ('node_traffic.mgmt_rx.bytes', f'statistics_traffic{{{j},mtype="mgmt",type="rx"}}', None),
        ('node_traffic.mgmt_tx.bytes', f'statistics_traffic{{{j},mtype="mgmt",type="tx"}}', None),
    ]
    # Airtime: alt die Zaehler des Treibers, neu der Anteil je Sammelrunde in
    # Prozent, wie yanic ihn aus den Zaehlern bildet
    for band, mtype in (('g', 'airtime2'), ('a', 'airtime5')):
        aktiv = (f'sum by ({BEI}) (increase(statistics_airtime{{{j},mtype="{mtype}",'
                 f'type="active"}}[10m]))')
        for neu, typ in (('chan_util', 'busy'), ('rx_util', 'rx'), ('tx_util', 'tx')):
            r.append((f'node_airtime11{band}.{neu}',
                      f'100 * sum by ({BEI}) (increase(statistics_airtime{{{j},mtype="{mtype}",'
                      f'type="{typ}"}}[10m])) / {aktiv}', None))
        r.append((f'node_airtime11{band}.noise',
                  f'statistics_airtime{{{j},mtype="{mtype}",type="noise"}}', None))
    # Linkqualitaet: alt 0..1, neu 0..100, andere Labelnamen
    r.append(('link_tq', f'100 * link_tq{{{j}}}', {
        'source': 'source.id', 'target': 'target.id', 'source_name': 'source.hostname',
        'target_name': 'target.hostname', 'link_type': 'type'}))
    return r


def holen(pfad, **param):
    url = f'{ALT}/{pfad}?' + urllib.parse.urlencode(param)
    for versuch in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as a:
                d = json.load(a)
            if d.get('status') == 'success':
                return d['data']
            raise RuntimeError(d.get('error', d))
        except Exception as ex:
            if versuch == 3:
                raise
            print(f'  Wiederholung nach Fehler: {ex}', file=sys.stderr)
            time.sleep(10 * (versuch + 1))


def jobs():
    """Alle nef-Jobs im Zeitraum. last_over_time ueber 100 Tage lehnt das alte
    Prometheus als zu schwer ab (HTTP 400), also Stichproben, vereinigt."""
    gefunden = set()
    for versatz in ('', ' offset 30d', ' offset 60d', ' offset 90d'):
        d = holen('query', query=f'count by (job) (statistics_clients_total{{job=~"nef.*"}}{versatz})')
        gefunden.update(x['metric']['job'] for x in d['result'])
    return sorted(gefunden)


def umsetzen(name, metrik, umbenennen):
    if umbenennen:
        neu = {umbenennen[k]: v for k, v in metrik.items() if k in umbenennen}
    else:
        neu = {k: v for k, v in metrik.items() if k in KNOTEN}
    neu.update({'__name__': name, 'db': 'neander', 'quelle': 'altkarte'})
    return neu


def schreiben(zeilen):
    if not zeilen:
        return
    daten = ('\n'.join(json.dumps(z) for z in zeilen) + '\n').encode()
    req = urllib.request.Request(NEU, data=daten, method='POST')
    with urllib.request.urlopen(req, timeout=300) as a:
        if a.status != 204:
            raise RuntimeError(f'Import: HTTP {a.status}')


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--jobs', help='nur diese Jobs, durch Komma getrennt')
    p.add_argument('--trocken', action='store_true', help='nur zaehlen, nichts schreiben')
    a = p.parse_args()

    # Prometheus haelt 98 Tage; ein Tag Abstand, damit der Anfang beim Abfragen
    # nicht schon verfallen ist
    beginn = (int(time.time()) - 97 * 86400) // SCHRITT * SCHRITT
    liste = a.jobs.split(',') if a.jobs else jobs()
    print(f'{len(liste)} Jobs, {time.strftime("%d.%m.%Y", time.localtime(beginn))} bis '
          f'{time.strftime("%d.%m.%Y %H:%M", time.localtime(ENDE))}', flush=True)
    gesamt_reihen = gesamt_punkte = 0
    for job in liste:
        punkte = anzahl = 0
        for name, ausdruck, umbenennen in reihen(job):
            von = beginn
            while von < ENDE:
                bis = min(von + STUECK, ENDE - SCHRITT)
                d = holen('query_range', query=ausdruck, start=von, end=bis, step=SCHRITT)
                zeilen = []
                for r in d['result']:
                    ts, ws = [], []
                    for t, w in r['values']:
                        w = float(w)
                        if math.isfinite(w):
                            ts.append(int(float(t) * 1000))
                            ws.append(w)
                    if ts:
                        zeilen.append({'metric': umsetzen(name, r['metric'], umbenennen),
                                       'values': ws, 'timestamps': ts})
                        punkte += len(ts)
                anzahl += len(zeilen)
                if not a.trocken:
                    schreiben(zeilen)
                von = bis + SCHRITT
                time.sleep(PAUSE)
        print(f'{job}: {anzahl} Reihenstuecke, {punkte} Werte', flush=True)
        gesamt_reihen += anzahl
        gesamt_punkte += punkte
    print(f'fertig: {gesamt_reihen} Reihenstuecke, {gesamt_punkte} Werte'
          f'{" (trocken)" if a.trocken else ""}', flush=True)


if __name__ == '__main__':
    main()
