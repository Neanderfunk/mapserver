#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt das Grafana-Dashboard eines Knotens.

  dashboard-erzeugen.py > /var/lib/grafana/dashboards/knoten.json

Das Dashboard ist die Vertiefung hinter dem Link im Knotenfenster der Karte.
Die Karte selbst zeichnet ihre Diagramme ohne Grafana, siehe zeitreihe/ und
web/patches/meshviewer.patch. Hier steht, was dort nicht hingehoert: lange
Zeitraeume, Tagesbilanzen als Balken und die Werte aus dem Paket
neanderfunk-respondd.

Als Generator und nicht als JSON von Hand, weil die Abfragen sonst zwischen
Klammern verschwinden. Wer eine Reihe aendern will, aendert sie hier.
"""
import json
import sys

QUELLE = {'type': 'prometheus', 'uid': 'neanderfunk'}


def ziel(expr, legende='', refid='A', schritt=''):
    z = {'refId': refid, 'expr': expr, 'legendFormat': legende,
         'datasource': QUELLE, 'range': True, 'editorMode': 'code'}
    if schritt:
        z['interval'] = schritt
    return z


def feld(einheit='', min_=None, balken=False, stapeln=False):
    eigen = {'drawStyle': 'bars' if balken else 'line',
             'lineWidth': 1 if balken else 2,
             'fillOpacity': 60 if balken else 10,
             'showPoints': 'never',
             'barAlignment': 0,
             'spanNulls': False}
    if stapeln:
        eigen['stacking'] = {'mode': 'normal', 'group': 'A'}
    d = {'unit': einheit, 'custom': eigen}
    if min_ is not None:
        d['min'] = min_
    return {'defaults': d, 'overrides': []}


def panel(nr, titel, ziele, x, y, w=12, h=8, einheit='', min_=None,
          balken=False, stapeln=False, beschreibung=''):
    return {
        'id': nr, 'title': titel, 'type': 'timeseries',
        'description': beschreibung,
        'datasource': QUELLE,
        'gridPos': {'h': h, 'w': w, 'x': x, 'y': y},
        'targets': ziele,
        'fieldConfig': feld(einheit, min_, balken, stapeln),
        'options': {'legend': {'displayMode': 'table', 'placement': 'bottom',
                               'showLegend': True,
                               'calcs': ['mean', 'lastNotNull', 'max']},
                    'tooltip': {'mode': 'multi', 'sort': 'desc'}},
    }


# Der Knoten kommt als Variable herein; der Link aus der Karte setzt sie per
# ?var-node=<node_id>. Die Liste erlaubt zusaetzlich das Stoebern.
VARIABLEN = [
    {'name': 'node', 'label': 'Knoten', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 1, 'query': 'label_values(node_load, nodeid)',
               'refId': 'node'},
     'definition': 'label_values(node_load, nodeid)',
     'refresh': 1, 'sort': 1, 'includeAll': False, 'multi': False,
     'current': {}, 'options': []},
]

# Kopfzeile: wer ist das, und hat er sich gerade gemeldet. Die Angaben
# kommen aus den Labels der Zeitreihe, eine eigene Abfrage braucht es nicht.
KOPF = [
    {
        'id': 100, 'title': 'Knoten', 'type': 'table', 'datasource': QUELLE,
        'gridPos': {'h': 5, 'w': 17, 'x': 0, 'y': 0},
        'targets': [dict(ziel('last_over_time({__name__="node_load", nodeid="$node"}[6h])',
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, 'Value': True, '__name__': True,
                                  'db': True, 'firmware_base': True,
                                  'frequency11a': True, 'frequency11g': True,
                                  'firmware_image_name': True,
                                  'firmware_subtarget': True},
                'renameByName': {'hostname': 'Name', 'nodeid': 'node_id',
                                 'model': 'Geraet', 'site': 'Domain',
                                 'firmware_release': 'Firmware',
                                 'firmware_target': 'Target',
                                 'autoupdater': 'Autoupdater',
                                 'is_gateway': 'Gateway'}}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}}, 'overrides': []},
    },
    {
        'id': 101, 'title': 'Letzte Meldung', 'type': 'stat', 'datasource': QUELLE,
        'description': 'Abstand zur letzten respondd-Antwort. Mehr als etwa zehn '
                       'Minuten heisst: der Knoten ist weg.',
        'gridPos': {'h': 5, 'w': 7, 'x': 17, 'y': 0},
        'targets': [dict(ziel('time() - timestamp(last_over_time('
                              '{__name__="node_load", nodeid="$node"}[7d]))', 'vor', 'A'),
                         instant=True, range=False)],
        'fieldConfig': {'defaults': {
            'unit': 's', 'decimals': 0,
            'thresholds': {'mode': 'absolute', 'steps': [
                {'color': 'green', 'value': None},
                {'color': 'orange', 'value': 900},
                {'color': 'red', 'value': 3600}]}},
            'overrides': []},
        'options': {'colorMode': 'value', 'graphMode': 'none',
                    'textMode': 'auto', 'reduceOptions': {
                        'calcs': ['lastNotNull'], 'fields': '', 'values': False}},
    },
]

PANELS = KOPF + [
    panel(1, 'Clients', [
        ziel('{__name__="node_clients.total", nodeid="$node"}', 'gesamt', 'A'),
        ziel('{__name__="node_clients.wifi24", nodeid="$node"}', '2,4 GHz', 'B'),
        ziel('{__name__="node_clients.wifi5", nodeid="$node"}', '5 GHz', 'C'),
    ], 0, 5, min_=0, beschreibung='Gleichzeitig verbundene Geraete.'),

    panel(2, 'Bandbreite', [
        ziel('rate({__name__="node_traffic.rx.bytes", nodeid="$node"}[$__rate_interval]) * 8',
             'Empfangen', 'A'),
        ziel('- rate({__name__="node_traffic.tx.bytes", nodeid="$node"}[$__rate_interval]) * 8',
             'Gesendet', 'B'),
    ], 12, 5, einheit='bps',
        beschreibung='Gesendet nach unten, damit sich beide Richtungen vergleichen lassen.'),

    panel(3, 'Datenmenge je Tag', [
        ziel('increase({__name__="node_traffic.rx.bytes", nodeid="$node"}[1d])',
             'Empfangen', 'A', '1d'),
        ziel('increase({__name__="node_traffic.tx.bytes", nodeid="$node"}[1d])',
             'Gesendet', 'B', '1d'),
    ], 0, 13, einheit='bytes', min_=0, balken=True, stapeln=True,
        beschreibung='Tagesbilanz. Bei Zeitraeumen unter zwei Tagen bleibt das Bild leer.'),

    panel(4, 'Airtime', [
        ziel('label_replace({__name__=~"node_airtime11(g|a).chan_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).chan_util")',
             '{{band}} belegt', 'A'),
        ziel('label_replace({__name__=~"node_airtime11(g|a).rx_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).rx_util")',
             '{{band}} Empfang', 'B'),
        ziel('label_replace({__name__=~"node_airtime11(g|a).tx_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).tx_util")',
             '{{band}} Senden', 'C'),
    ], 12, 13, einheit='percent', min_=0,
        beschreibung='g ist 2,4 GHz, a ist 5 GHz. Dauerhaft ueber 60 Prozent belegt heisst: der Kanal ist voll.'),

    panel(5, 'Speicher', [
        ziel('{__name__="node_memory.available", nodeid="$node"} * 1024', 'verfuegbar', 'A'),
        ziel('{__name__="node_memory.free", nodeid="$node"} * 1024', 'frei', 'B'),
    ], 0, 21, einheit='bytes', min_=0,
        beschreibung='Verfuegbar ist der Wert, auf den es ankommt; frei allein sagt wenig.'),

    panel(6, 'Last', [
        ziel('{__name__="node_load", nodeid="$node"}', 'loadavg', 'A'),
        ziel('{__name__="node_proc.running", nodeid="$node"}', 'laufende Prozesse', 'B'),
    ], 12, 21, min_=0),

    panel(7, 'Laufzeit', [
        ziel('{__name__="node_time.up", nodeid="$node"}', 'Laufzeit', 'A'),
    ], 0, 29, einheit='s',
        beschreibung='Ein Sprung nach unten ist ein Neustart.'),

    panel(8, 'Nachbarn und Gegenstelle', [
        ziel('{__name__="node_neighbours.batadv", nodeid="$node"}', 'batman', 'A'),
        ziel('{__name__="node_neighbours.vpn", nodeid="$node"}', 'VPN', 'B'),
    ], 12, 29, min_=0),

    panel(9, 'Temperatur', [
        ziel('nf_temperature_celsius{nodeid="$node"}', '{{sensor}}', 'A'),
    ], 0, 37, einheit='celsius',
        beschreibung='Nur Knoten mit Sensor und dem Paket neanderfunk-respondd.'),

    panel(10, 'Pagecache-Refaults', [
        ziel('rate({__name__="node_nf.refault_file", nodeid="$node"}[$__rate_interval])',
             'Refaults je Sekunde', 'A'),
    ], 12, 37, min_=0,
        beschreibung='Fruehindikator fuer Speichermangel: der Knoten liest staendig nach, '
                     'was er gerade verworfen hat. Braucht das Paket neanderfunk-respondd.'),

    panel(11, 'Ethernet', [
        ziel('nf_ethernet_speed{nodeid="$node"}', '{{port}} ausgehandelt', 'A'),
        ziel('nf_ethernet_possible{nodeid="$node"}', '{{port}} moeglich', 'B'),
    ], 0, 45, einheit='Mbits', min_=0,
        beschreibung='Moeglich groesser als ausgehandelt heisst: der Port kam nicht hoch. '
                     'Ein toter Port meldet beides als 0, dafuer nf_ethernet_carrier.'),

    panel(12, 'zram', [
        ziel('{__name__="node_nf.zram.data", nodeid="$node"} * 1024', 'Daten', 'A'),
        ziel('{__name__="node_nf.zram.ram", nodeid="$node"} * 1024', 'im RAM', 'B'),
    ], 12, 45, einheit='bytes', min_=0,
        beschreibung='Wie viel komprimiert im Speicher liegt. Braucht das Paket neanderfunk-respondd.'),
]

# --- Supernodes -------------------------------------------------------------
# Ein Supernode ist kein Knoten wie die anderen: kein WLAN, keine Airtime,
# keine Clients an ihm selbst. Interessant ist, was an ihm haengt. Je Domain
# tritt er als eigener Knoten auf (hostname <name>_<domain>, node_id
# f2beef00<dd><nn>), deshalb waehlt die Variable den Hostnamen.
#
# KANTE bildet die Kanten auf die node_id der Gegenstelle ab. Damit lassen
# sich Werte der angebundenen Knoten summieren, ohne eine Liste zu pflegen:
# "* 0 + 1" macht aus der Kante einen Faktor 1.
KANTE = ('label_replace(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]),'
         ' "nodeid", "$1", "source.id", "(.*)")')
DAHINTER = '%s * on(nodeid) group_left() (' + KANTE + ' * 0 + 1)'

SUPERNODE_VARIABLEN = [
    {'name': 'sn', 'label': 'Supernode', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 1,
               'query': 'label_values(node_load{is_gateway="true"}, hostname)',
               'refId': 'sn'},
     'definition': 'label_values(node_load{is_gateway="true"}, hostname)',
     'refresh': 1, 'sort': 1, 'includeAll': False, 'multi': False,
     'current': {}, 'options': []},
]

SUPERNODE_KOPF = [
    {
        'id': 100, 'title': 'Supernode', 'type': 'table', 'datasource': QUELLE,
        'gridPos': {'h': 5, 'w': 17, 'x': 0, 'y': 0},
        'targets': [dict(ziel('last_over_time({__name__="node_load", hostname="$sn"}[6h])',
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, 'Value': True, '__name__': True,
                                  'db': True, 'firmware_base': True,
                                  'firmware_image_name': True, 'firmware_subtarget': True,
                                  'firmware_release': True, 'firmware_target': True,
                                  'model': True, 'autoupdater': True, 'site': True},
                'renameByName': {'hostname': 'Instanz', 'nodeid': 'node_id',
                                 'domain': 'Domain', 'is_gateway': 'Gateway'}}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}}, 'overrides': []},
    },
    {
        'id': 101, 'title': 'Knoten an dieser Instanz', 'type': 'stat', 'datasource': QUELLE,
        'gridPos': {'h': 5, 'w': 7, 'x': 17, 'y': 0},
        'targets': [dict(ziel('count(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))',
                              'Knoten', 'A'), instant=True, range=False)],
        'fieldConfig': {'defaults': {'decimals': 0, 'thresholds': {'mode': 'absolute', 'steps': [
            {'color': 'red', 'value': None}, {'color': 'green', 'value': 1}]}}, 'overrides': []},
        'options': {'colorMode': 'value', 'graphMode': 'area', 'textMode': 'auto',
                    'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False}},
    },
]

SUPERNODE_PANELS = SUPERNODE_KOPF + [
    panel(1, 'Angebundene Knoten', [
        ziel('count(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))',
             'Knoten', 'A'),
    ], 0, 5, min_=0,
        beschreibung='Kanten zu dieser Instanz. Faellt die Zahl, hat der Supernode Knoten verloren.'),

    panel(2, 'Clients dahinter', [
        ziel('sum(' + DAHINTER % 'last_over_time({__name__="node_clients.total"}[15m])' + ')',
             'Clients', 'A'),
    ], 12, 5, min_=0,
        beschreibung='Summe ueber alle Knoten, die gerade an dieser Instanz haengen.'),

    panel(3, 'Verkehr der Instanz', [
        ziel('rate({__name__="node_traffic.forward.bytes", hostname="$sn"}[$__rate_interval]) * 8',
             'weitergereicht', 'A'),
        ziel('rate({__name__="node_traffic.rx.bytes", hostname="$sn"}[$__rate_interval]) * 8',
             'empfangen', 'B'),
        ziel('- rate({__name__="node_traffic.tx.bytes", hostname="$sn"}[$__rate_interval]) * 8',
             'gesendet', 'C'),
    ], 0, 13, einheit='bps',
        beschreibung='Weitergereicht ist bei einem Supernode der eigentliche Wert.'),

    panel(4, 'Verkehr der angebundenen Knoten', [
        ziel('sum(' + DAHINTER % 'rate({__name__="node_traffic.rx.bytes"}[$__rate_interval])' + ') * 8',
             'empfangen', 'A'),
        ziel('- sum(' + DAHINTER % 'rate({__name__="node_traffic.tx.bytes"}[$__rate_interval])' + ') * 8',
             'gesendet', 'B'),
    ], 12, 13, einheit='bps',
        beschreibung='Aus Sicht der Knoten, nicht der Instanz. Die Differenz zum Verkehr '
                     'der Instanz ist Mesh-Verkehr, der nie zum Supernode laeuft.'),

    panel(5, 'Linkqualitaet zu den Knoten', [
        ziel('min(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))', 'schlechteste', 'A'),
        ziel('avg(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))', 'Mittel', 'B'),
    ], 0, 21, einheit='percent', min_=0,
        beschreibung='TQ ueber alle Kanten. Faellt das Minimum, hat ein Knoten eine schlechte Anbindung.'),

    panel(6, 'Last und Speicher', [
        ziel('{__name__="node_load", hostname="$sn"}', 'loadavg', 'A'),
        ziel('{__name__="node_proc.running", hostname="$sn"}', 'laufende Prozesse', 'B'),
    ], 12, 21, min_=0),

    panel(7, 'Freier Speicher', [
        ziel('{__name__="node_memory.available", hostname="$sn"} * 1024', 'verfuegbar', 'A'),
        ziel('{__name__="node_memory.total", hostname="$sn"} * 1024', 'gesamt', 'B'),
    ], 0, 29, einheit='bytes', min_=0),

    panel(8, 'Laufzeit', [
        ziel('{__name__="node_time.up", hostname="$sn"}', 'Laufzeit', 'A'),
    ], 12, 29, einheit='s',
        beschreibung='Ein Sprung nach unten ist ein Neustart der Instanz.'),

    {
        'id': 9, 'title': 'Knoten an dieser Instanz', 'type': 'table', 'datasource': QUELLE,
        'description': 'Momentaufnahme mit Linkqualitaet, absteigend nach TQ.',
        'gridPos': {'h': 10, 'w': 24, 'x': 0, 'y': 37},
        'targets': [dict(ziel('last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m])',
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, '__name__': True, 'db': True,
                                  'target.addr': True, 'target.hostname': True,
                                  'target.id': True, 'source.addr': True},
                'renameByName': {'source.hostname': 'Knoten', 'source.id': 'node_id',
                                 'type': 'Art', 'Value': 'TQ'}}},
            {'id': 'sortBy', 'options': {'fields': {},
                                         'sort': [{'field': 'TQ', 'desc': False}]}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}}, 'overrides': []},
    },
]


DASHBOARD = {
    'uid': 'nf-knoten',
    'title': 'Knoten',
    'description': 'Zeitreihen eines Knotens. Aufgerufen aus dem Knotenfenster '
                   'der Karte; die Karte selbst zeichnet ihre Diagramme ohne Grafana.',
    'tags': ['neanderfunk'],
    'timezone': 'browser',
    'schemaVersion': 39,
    'version': 1,
    'refresh': '5m',
    'time': {'from': 'now-7d', 'to': 'now'},
    'templating': {'list': VARIABLEN},
    'panels': PANELS,
    'editable': False,
    'graphTooltip': 1,
    'links': [{'type': 'dashboards', 'tags': ['neanderfunk'], 'title': 'Weitere',
               'asDropdown': True, 'icon': 'external link', 'includeVars': False,
               'keepTime': True, 'targetBlank': False}],
}


SUPERNODE = {
    'uid': 'nf-supernode',
    'title': 'Supernode',
    'description': 'Eine Supernode-Instanz und was an ihr haengt. Je Domain '
                   'gibt es eine Instanz.',
    'tags': ['neanderfunk'],
    'timezone': 'browser',
    'schemaVersion': 39,
    'version': 1,
    'refresh': '5m',
    'time': {'from': 'now-7d', 'to': 'now'},
    'templating': {'list': SUPERNODE_VARIABLEN},
    'panels': SUPERNODE_PANELS,
    'editable': False,
    'graphTooltip': 1,
    'links': [{'type': 'dashboards', 'tags': ['neanderfunk'], 'title': 'Weitere',
               'asDropdown': True, 'icon': 'external link', 'includeVars': False,
               'keepTime': True, 'targetBlank': False}],
}


def main():
    was = sys.argv[1] if len(sys.argv) > 1 else 'knoten'
    json.dump(SUPERNODE if was == 'supernode' else DASHBOARD, sys.stdout,
              ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
