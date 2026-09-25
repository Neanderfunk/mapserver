#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt das Grafana-Dashboard eines Knotens.

  dashboard-erzeugen.py > /var/lib/grafana/dashboards/knoten.json

Das Dashboard ist die Vertiefung hinter dem Link im Knotenfenster der Karte.
Die Karte selbst zeichnet ihre Diagramme ohne Grafana, siehe zeitreihe/ und
unserem meshviewer-Fork
(github.com/Neanderfunk/meshviewer, Zweig neanderfunk). Hier steht, was dort nicht hingehoert: lange
Zeitraeume, Tagesbilanzen als Balken und die Werte aus dem Paket
neanderfunk-respondd.

Als Generator und nicht als JSON von Hand, weil die Abfragen sonst zwischen
Klammern verschwinden. Wer eine Reihe aendern will, aendert sie hier.
"""
import json
import sys

QUELLE = {'type': 'prometheus', 'uid': 'neanderfunk'}

# Hostnamen unterscheiden sich bei uns am Ende, nicht am Anfang: ein ganzes
# Haus heisst vorn gleich (wlf-uk-Schulstr7-...). Auf schmalen Anzeigen
# schneidet Grafana aber hinten ab, und dann sehen alle Eintraege gleich aus.
# Gemessen am 23.09.2026: von links auf 16 Zeichen gekuerzt sind 397 von 1076
# Namen nicht mehr unterscheidbar, von rechts nur fuenf. Deshalb steht in
# Legenden und Tabellen das Ende vorn, der volle Name daneben.
KURZ = '.*?([^-_]+[-_][^-_]+)'


def kurzname(ausdruck, quelle='hostname'):
    return f'label_replace({ausdruck}, "kurz", "$1", "{quelle}", "{KURZ}")'


# Alle Abfragen fassen zusammen. yanic haengt Labels wie Frequenz oder
# Firmwareversion an jeden Punkt; jede Aenderung waere sonst eine neue Reihe
# mit eigener Farbe und eigenem Eintrag in der Legende. Ein Knoten, der
# mehrfach neu startet, fuellt damit die halbe Kachel (adorfer 23.09.2026).
# Die Frequenzlabels wirft VictoriaMetrics inzwischen schon beim Empfang weg,
# fuer aeltere Daten und fuer Firmwarewechsel bleibt die Zusammenfassung
# noetig.


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
        ziel('max({__name__="node_clients.total", nodeid="$node"})', 'gesamt', 'A'),
        ziel('max({__name__="node_clients.wifi24", nodeid="$node"})', '2,4 GHz', 'B'),
        ziel('max({__name__="node_clients.wifi5", nodeid="$node"})', '5 GHz', 'C'),
    ], 0, 5, min_=0, beschreibung='Gleichzeitig verbundene Geraete.'),

    panel(2, 'Bandbreite', [
        ziel('sum(rate({__name__="node_traffic.rx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'empfangen', 'A'),
        ziel('sum(rate({__name__="node_traffic.tx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'gesendet', 'B'),
        ziel('sum(rate({__name__="node_traffic.mgmt_rx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'Verwaltung empfangen', 'C'),
        ziel('sum(rate({__name__="node_traffic.mgmt_tx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'Verwaltung gesendet', 'D'),
        ziel('sum(rate({__name__="node_traffic.forward.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'weitergereicht', 'E'),
    ], 12, 5, einheit='bps', min_=0,
        beschreibung='Alle Betraege positiv. Verwaltung ist der batman-eigene Verkehr '
                     '(OGMs und Nachbarschaft), weitergereicht ist Verkehr fuer andere '
                     'Knoten im Mesh.'),

    panel(3, 'Datenmenge je Tag', [
        ziel('sum(increase({__name__="node_traffic.rx.bytes", nodeid="$node"}[1d]))',
             'Empfangen', 'A', '1d'),
        ziel('sum(increase({__name__="node_traffic.tx.bytes", nodeid="$node"}[1d]))',
             'Gesendet', 'B', '1d'),
    ], 0, 13, einheit='bytes', min_=0, balken=True, stapeln=True,
        beschreibung='Tagesbilanz. Bei Zeitraeumen unter zwei Tagen bleibt das Bild leer.'),

    # Airtime ausserhalb von 0 bis 100 Prozent ist immer ein Messfehler: der
    # mt76-Unterlauf mancher Gluon-Knoten und einmalig am 25.09.2026 um 11:02
    # die UniFi-APs (alte Bytezaehler gegen neue Airtime-Zaehler). Ohne die
    # Klammer sprengt ein einziger solcher Wert die Achse fuer 400 Tage.
    panel(4, 'Airtime', [
        ziel('clamp(max by (band) (label_replace({__name__=~"node_airtime11(g|a).chan_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).chan_util")), 0, 100)',
             '{{band}} belegt', 'A'),
        ziel('clamp(max by (band) (label_replace({__name__=~"node_airtime11(g|a).rx_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).rx_util")), 0, 100)',
             '{{band}} Empfang', 'B'),
        ziel('clamp(max by (band) (label_replace({__name__=~"node_airtime11(g|a).tx_util", nodeid="$node"},'
             ' "band", "$1", "__name__", "node_airtime11(g|a).tx_util")), 0, 100)',
             '{{band}} Senden', 'C'),
    ], 12, 13, einheit='percent', min_=0,
        beschreibung='g ist 2,4 GHz, a ist 5 GHz. Dauerhaft ueber 60 Prozent belegt heisst: der Kanal ist voll.'),

    panel(5, 'Speicher', [
        ziel('max({__name__="node_memory.available", nodeid="$node"}) * 1024', 'verfuegbar', 'A'),
        ziel('max({__name__="node_memory.free", nodeid="$node"}) * 1024', 'frei', 'B'),
    ], 0, 21, einheit='bytes', min_=0,
        beschreibung='Verfuegbar ist der Wert, auf den es ankommt; frei allein sagt wenig.'),

    panel(6, 'Last', [
        ziel('max({__name__="node_load", nodeid="$node"})', 'loadavg', 'A'),
        ziel('max({__name__="node_proc.running", nodeid="$node"})', 'laufende Prozesse', 'B'),
    ], 12, 21, min_=0),

    panel(7, 'Laufzeit', [
        ziel('max({__name__="node_time.up", nodeid="$node"})', 'Laufzeit', 'A'),
    ], 0, 29, einheit='s',
        beschreibung='Ein Sprung nach unten ist ein Neustart.'),

    panel(8, 'Nachbarn und Gegenstelle', [
        ziel('max({__name__="node_neighbours.batadv", nodeid="$node"})', 'batman', 'A'),
        ziel('max({__name__="node_neighbours.vpn", nodeid="$node"})', 'VPN', 'B'),
    ], 12, 29, min_=0),

    panel(9, 'Temperatur', [
        ziel('max by (sensor) (nf_temperature_celsius{nodeid="$node"})', '{{sensor}}', 'A'),
    ], 0, 37, einheit='celsius',
        beschreibung='Nur Knoten mit Sensor und dem Paket neanderfunk-respondd.'),

    panel(10, 'Pagecache-Refaults', [
        ziel('sum(rate({__name__="node_nf.refault_file", nodeid="$node"}[$__rate_interval]))',
             'Refaults je Sekunde', 'A'),
    ], 12, 37, min_=0,
        beschreibung='Fruehindikator fuer Speichermangel: der Knoten liest staendig nach, '
                     'was er gerade verworfen hat. Braucht das Paket neanderfunk-respondd.'),

    panel(11, 'Ethernet', [
        ziel('max by (port) (nf_ethernet_speed{nodeid="$node"})', '{{port}} ausgehandelt', 'A'),
        ziel('max by (port) (nf_ethernet_possible{nodeid="$node"})', '{{port}} moeglich', 'B'),
    ], 0, 45, einheit='Mbits', min_=0,
        beschreibung='Moeglich groesser als ausgehandelt heisst: der Port kam nicht hoch. '
                     'Ein toter Port meldet beides als 0, dafuer nf_ethernet_carrier.'),

    panel(13, 'Ausfaelle laut Knoten', [
        ziel('max({__name__="node_nf.ssid_changer.offline", nodeid="$node"})',
             'offline gegangen', 'A'),
        ziel('max({__name__="node_nf.ssid_changer.gateway_losses", nodeid="$node"})',
             'Gateway verloren', 'B'),
        ziel('max({__name__="node_nf.ssid_changer.switches", nodeid="$node"})',
             'SSID gewechselt', 'C'),
    ], 0, 53, min_=0,
        beschreibung='Zaehler des SSID-Changers seit dem letzten Start. Ein Knoten kann '
                     'nicht melden, dass er offline ist; dieser Zaehler steht danach aber '
                     'hoeher da und zeigt damit auch kurze Stoerungen ohne Neustart. '
                     'Springt er auf null, hat der Knoten neu gestartet. Nur mit dem '
                     'Paket neanderfunk-respondd.'),

    panel(12, 'zram', [
        ziel('max({__name__="node_nf.zram.data", nodeid="$node"}) * 1024', 'Daten', 'A'),
        ziel('max({__name__="node_nf.zram.ram", nodeid="$node"}) * 1024', 'im RAM', 'B'),
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
             'laut respondd', 'A'),
        ziel('sum(last_over_time(tt_clients[15m]) * on(sndomain) group_left()'
             ' (label_replace(last_over_time({__name__="node_load", hostname="$sn"}[15m]),'
             ' "sndomain", "$1", "domain", "(.*)") * 0 + 1))', 'laut Uebersetzungstabelle', 'B'),
    ], 12, 5, min_=0,
        beschreibung='Zwei Zaehlweisen. respondd summiert, was die Knoten melden, die '
                     'gerade antworten. Die Uebersetzungstabelle kennt jede Station der '
                     'Domain, auch hinter stummen Knoten, haelt sie aber noch ein paar '
                     'Minuten nach dem Abmelden. Untergrenze und Obergrenze also.'),

    panel(3, 'Verkehr der Instanz', [
        ziel('sum(rate({__name__="node_traffic.forward.bytes", hostname="$sn"}[$__rate_interval])) * 8',
             'weitergereicht', 'A'),
        ziel('sum(rate({__name__="node_traffic.rx.bytes", hostname="$sn"}[$__rate_interval])) * 8',
             'empfangen', 'B'),
        ziel('sum(rate({__name__="node_traffic.tx.bytes", hostname="$sn"}[$__rate_interval])) * 8',
             'gesendet', 'C'),
        ziel('sum(rate({__name__="node_traffic.mgmt_rx.bytes", hostname="$sn"}[$__rate_interval])) * 8',
             'Verwaltung empfangen', 'D'),
        ziel('sum(rate({__name__="node_traffic.mgmt_tx.bytes", hostname="$sn"}[$__rate_interval])) * 8',
             'Verwaltung gesendet', 'E'),
    ], 0, 13, einheit='bps', min_=0,
        beschreibung='Weitergereicht ist bei einem Supernode der eigentliche Wert.'),

    panel(4, 'Verkehr der angebundenen Knoten', [
        ziel('sum(' + DAHINTER % 'rate({__name__="node_traffic.rx.bytes"}[$__rate_interval])' + ') * 8',
             'empfangen', 'A'),
        ziel('sum(' + DAHINTER % 'rate({__name__="node_traffic.tx.bytes"}[$__rate_interval])' + ') * 8',
             'gesendet', 'B'),
        ziel('sum(' + DAHINTER % 'rate({__name__="node_traffic.mgmt_rx.bytes"}[$__rate_interval])' + ') * 8',
             'Verwaltung empfangen', 'C'),
        ziel('sum(' + DAHINTER % 'rate({__name__="node_traffic.mgmt_tx.bytes"}[$__rate_interval])' + ') * 8',
             'Verwaltung gesendet', 'D'),
    ], 12, 13, einheit='bps', min_=0,
        beschreibung='Aus Sicht der Knoten, nicht der Instanz. Die Differenz zum Verkehr '
                     'der Instanz ist Mesh-Verkehr, der nie zum Supernode laeuft.'),

    panel(5, 'Linkqualitaet zu den Knoten', [
        ziel('min(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))', 'schlechteste', 'A'),
        ziel('avg(last_over_time({__name__="link_tq", "target.hostname"="$sn"}[15m]))', 'Mittel', 'B'),
    ], 0, 21, einheit='percent', min_=0,
        beschreibung='TQ ueber alle Kanten. Faellt das Minimum, hat ein Knoten eine schlechte Anbindung.'),

    panel(6, 'Last der Maschine', [
        ziel('max({__name__="node_load", hostname="$sn"})', 'loadavg', 'A'),
        ziel('max({__name__="node_proc.running", hostname="$sn"})', 'laufende Prozesse', 'B'),
    ], 12, 21, min_=0,
        beschreibung='Gilt fuer die ganze Maschine, nicht fuer diese Domaininstanz: alle '
                     '48 respondd-Instanzen eines Supernodes melden dieselben Systemwerte.'),

    panel(7, 'Speicher der Maschine', [
        ziel('max({__name__="node_memory.available", hostname="$sn"}) * 1024', 'verfuegbar', 'A'),
        ziel('max({__name__="node_memory.total", hostname="$sn"}) * 1024', 'gesamt', 'B'),
    ], 0, 29, einheit='bytes', min_=0,
        beschreibung='Ebenfalls maschinenweit, siehe nebenan.'),

    panel(8, 'Laufzeit', [
        ziel('max({__name__="node_time.up", hostname="$sn"})', 'Laufzeit', 'A'),
    ], 12, 29, einheit='s',
        beschreibung='Ein Sprung nach unten ist ein Neustart der Maschine, nicht nur '
                     'dieser Instanz (23.09.2026 um 22:42 alle sechs, wegen batman-adv 2026.3).'),

    {
        'id': 9, 'title': 'Knoten an dieser Instanz', 'type': 'table', 'datasource': QUELLE,
        'description': 'Momentaufnahme mit Linkqualitaet, absteigend nach TQ.',
        'gridPos': {'h': 10, 'w': 24, 'x': 0, 'y': 37},
        'targets': [dict(ziel(kurzname('last_over_time({__name__="link_tq",'
                              ' "target.hostname"="$sn"}[15m])', 'source.hostname'),
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, '__name__': True, 'db': True,
                                  'target.addr': True, 'target.hostname': True,
                                  'target.id': True, 'source.addr': True},
                # Das Unterscheidende zuerst, der volle Name dahinter
                'indexByName': {'kurz': 0, 'Value': 1, 'source.hostname': 2,
                                'type': 3, 'source.id': 4},
                'renameByName': {'kurz': 'Knoten', 'source.hostname': 'voller Name',
                                 'source.id': 'node_id',
                                 'type': 'Art', 'Value': 'TQ'}}},
            {'id': 'sortBy', 'options': {'fields': {},
                                         'sort': [{'field': 'TQ', 'desc': False}]}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}}, 'overrides': []},
    },
]


# --- Domains ----------------------------------------------------------------
# Eine Domain als Ganzes. Die Knotenmetriken tragen den gemeldeten site_code
# (nef-05_mon, dus-30_sol_EOL), die Werte aus der Uebersetzungstabelle den
# Domaincode (05_mon). Gemeinsam ist beiden die Nummer, also wird sie per
# label_replace herausgezogen und darueber verbunden.
DNUM_KNOTEN = ('label_replace(%s, "dnum", "$1", "site", ".*?([0-9]+)_.*")')
DNUM_TT = ('label_replace(%s, "dnum", "$1", "domain", "([0-9]+)_.*")')


def dnum(ausdruck, tt=False):
    return (DNUM_TT if tt else DNUM_KNOTEN) % ausdruck


def je_domain(ausdruck):
    """Summe ueber die Knoten einer Domain, ausgewaehlt ueber $domain."""
    return ('sum(' + dnum(ausdruck) + ' * on(dnum) group_left() ('
            + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True)
            + ' * 0 + 1))')


DOMAIN_VARIABLEN = [
    {'name': 'domain', 'label': 'Domain', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 1, 'query': 'label_values(tt_clients, domain)',
               'refId': 'domain'},
     'definition': 'label_values(tt_clients, domain)',
     'refresh': 1, 'sort': 1, 'includeAll': False, 'multi': False,
     'current': {}, 'options': []},
]


def zahl(nr, titel, ausdruck, x, w=6, einheit='', beschreibung='', warnung=None):
    feld = {'unit': einheit, 'decimals': 0}
    if warnung is not None:
        feld['thresholds'] = {'mode': 'absolute', 'steps': [
            {'color': 'green', 'value': None}, {'color': 'orange', 'value': warnung}]}
    return {
        'id': nr, 'title': titel, 'type': 'stat', 'datasource': QUELLE,
        'description': beschreibung,
        'gridPos': {'h': 5, 'w': w, 'x': x, 'y': 0},
        'targets': [dict(ziel(ausdruck, '', 'A'), instant=True, range=False)],
        'fieldConfig': {'defaults': feld, 'overrides': []},
        'options': {'colorMode': 'value', 'graphMode': 'area', 'textMode': 'auto',
                    'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False}},
    }


DOMAIN_PANELS = [
    zahl(100, 'Knoten im Mesh', 'last_over_time(tt_im_mesh{domain="$domain"}[15m])', 0,
         beschreibung='Verschiedene Knoten, die batman in dieser Domain kennt.'),
    zahl(101, 'Dunkle Knoten', 'last_over_time(tt_dunkel{domain="$domain"}[15m])', 6,
         warnung=1,
         beschreibung='Im Mesh sichtbar, aber keiner Karte zuzuordnen: batman-Knoten, '
                      'deren respondd nicht antwortet. Ein Knoten dieser Art steckt '
                      'seit dem 23.09.2026 in jeder Domain (02:a5:a7:99:f0:fa, '
                      'antwortet weder auf respondd noch auf ping).'),
    zahl(102, 'Clients laut Tabelle', 'last_over_time(tt_clients{domain="$domain"}[15m])', 12,
         beschreibung='Stationen in der Uebersetzungstabelle, ohne die Knoten selbst.'),
    zahl(103, 'Clients laut respondd',
         je_domain('last_over_time({__name__="node_clients.total"}[15m])'), 18,
         beschreibung='Summe ueber die Knoten, die gerade geantwortet haben.'),

    panel(1, 'Clients', [
        ziel('last_over_time(tt_clients{domain="$domain"}[15m])', 'Uebersetzungstabelle', 'A'),
        ziel(je_domain('last_over_time({__name__="node_clients.total"}[15m])'), 'respondd', 'B'),
    ], 0, 5, min_=0,
        beschreibung='Obergrenze und Untergrenze. Die Tabelle haelt Stationen noch einige '
                     'Minuten nach dem Abmelden, respondd verfehlt alles hinter stummen Knoten.'),

    panel(2, 'Knoten', [
        ziel('last_over_time(tt_im_mesh{domain="$domain"}[15m])', 'im Mesh', 'A'),
        ziel('last_over_time(tt_dunkel{domain="$domain"}[15m])', 'dunkel', 'B'),
        ziel('last_over_time(tt_originatoren{domain="$domain"}[15m])', 'Originatoren', 'C'),
    ], 12, 5, min_=0,
        beschreibung='Originatoren sind mehr als Knoten: jede Mesh-Schnittstelle zaehlt '
                     'einzeln, im Schnitt etwa doppelt.'),

    panel(3, 'Verkehr der Domain', [
        ziel(je_domain('rate({__name__="node_traffic.rx.bytes"}[$__rate_interval])') + ' * 8',
             'empfangen', 'A'),
        ziel(je_domain('rate({__name__="node_traffic.tx.bytes"}[$__rate_interval])') + ' * 8',
             'gesendet', 'B'),
        ziel(je_domain('rate({__name__="node_traffic.mgmt_rx.bytes"}[$__rate_interval])') + ' * 8',
             'Verwaltung empfangen', 'C'),
        ziel(je_domain('rate({__name__="node_traffic.mgmt_tx.bytes"}[$__rate_interval])') + ' * 8',
             'Verwaltung gesendet', 'D'),
    ], 0, 13, einheit='bps', min_=0,
        beschreibung='Summe ueber alle Knoten der Domain, aus deren Sicht. Alle Betraege '
                     'positiv; Verwaltung ist der batman-eigene Verkehr.'),

    panel(4, 'Datenmenge je Tag', [
        ziel(je_domain('increase({__name__="node_traffic.rx.bytes"}[1d])'), 'empfangen', 'A', '1d'),
        ziel(je_domain('increase({__name__="node_traffic.tx.bytes"}[1d])'), 'gesendet', 'B', '1d'),
    ], 12, 13, einheit='bytes', min_=0, balken=True, stapeln=True),

    panel(5, 'Knoten mit wenig freiem Speicher', [
        ziel('count(' + dnum('last_over_time({__name__="node_memory.available"}[15m]) < 10000')
             + ' * on(dnum) group_left() ('
             + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True) + ' * 0 + 1))',
             'unter 10 MB', 'A'),
    ], 0, 21, min_=0,
        beschreibung='Kandidaten fuer den Austausch, unabhaengig vom Geraetetyp.'),

    panel(6, 'Laufzeit der Knoten', [
        ziel('min(' + dnum('last_over_time({__name__="node_time.up"}[15m])')
             + ' * on(dnum) group_left() ('
             + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True) + ' * 0 + 1))',
             'kuerzeste', 'A'),
        ziel('avg(' + dnum('last_over_time({__name__="node_time.up"}[15m])')
             + ' * on(dnum) group_left() ('
             + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True) + ' * 0 + 1))',
             'im Mittel', 'B'),
    ], 12, 21, einheit='s', min_=0,
        beschreibung='Faellt die kuerzeste Laufzeit staendig, startet dort etwas immer wieder neu.'),
]


DOMAIN = {
    'uid': 'nf-domain',
    'title': 'Domain',
    'description': 'Eine Domain als Ganzes: Clients aus zwei Quellen, Knoten im '
                   'Mesh, dunkle Knoten, Verkehr.',
    'tags': ['neanderfunk'],
    'timezone': 'browser',
    'schemaVersion': 39,
    'version': 1,
    'refresh': '5m',
    'time': {'from': 'now-7d', 'to': 'now'},
    'templating': {'list': DOMAIN_VARIABLEN},
    'panels': DOMAIN_PANELS,
    'editable': False,
    'graphTooltip': 1,
    'links': [{'type': 'dashboards', 'tags': ['neanderfunk'], 'title': 'Weitere',
               'asDropdown': True, 'icon': 'external link', 'includeVars': False,
               'keepTime': True, 'targetBlank': False}],
}


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
    json.dump({'supernode': SUPERNODE, 'domain': DOMAIN}.get(was, DASHBOARD),
              sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
