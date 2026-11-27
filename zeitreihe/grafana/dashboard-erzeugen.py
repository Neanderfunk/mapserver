#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt das Grafana-Dashboard eines Knotens.

  dashboard-erzeugen.py > /var/lib/grafana/dashboards/knoten.json
  dashboard-erzeugen.py community|domain|supernode > .../<name>.json

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


def achse_rechts(name):
    """Override: diese Reihe auf eigener Achse rechts, sonst wie die anderen.
    Fuer einen Bestand neben kleinen Zahlen (500 freie Bloecke neben 20
    belegten)."""
    return {'matcher': {'id': 'byName', 'options': name}, 'properties': [
        {'id': 'custom.axisPlacement', 'value': 'right'},
    ]}


def linie_rechts(name):
    """Override: diese Reihe als Linie auf eigener Achse rechts, nicht
    gestapelt. Fuer eine Groesse, die um Groessenordnungen neben den Balken
    liegt und sie sonst plattdrueckt."""
    return {'matcher': {'id': 'byName', 'options': name}, 'properties': [
        {'id': 'custom.drawStyle', 'value': 'line'},
        {'id': 'custom.axisPlacement', 'value': 'right'},
        {'id': 'custom.stacking', 'value': {'mode': 'none', 'group': 'rechts'}},
        {'id': 'custom.fillOpacity', 'value': 0},
        {'id': 'custom.lineWidth', 'value': 2},
        {'id': 'custom.showPoints', 'value': 'always'},
        {'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': 'red'}},
    ]}


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
          balken=False, stapeln=False, beschreibung='', sortieren=False,
          abweichend=(), legende_rechts=False):
    legende = {'displayMode': 'table', 'placement': 'bottom', 'showLegend': True,
               'calcs': ['mean', 'lastNotNull', 'max']}
    if legende_rechts:
        # Wenige Reihen in einem breiten Panel: rechts daneben passen alle,
        # unten verschwaende die Tabelle die Breite und schnitte Zeilen ab
        legende.update(placement='right', width=330)
    if sortieren:
        # Verteilungen: haeufigster Stand oben, nach dem aktuellen Wert
        legende.update(sortBy='Last *', sortDesc=True)
    return {
        'id': nr, 'title': titel, 'type': 'timeseries',
        'description': beschreibung,
        'datasource': QUELLE,
        'gridPos': {'h': h, 'w': w, 'x': x, 'y': y},
        'targets': ziele,
        'fieldConfig': dict(feld(einheit, min_, balken, stapeln),
                            overrides=list(abweichend)),
        'options': {'legend': legende,
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
                                 'model': 'Gerät', 'site': 'Domain',
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
                       'Minuten heißt: der Knoten ist weg.',
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

# ddhcpd, der verteilte DHCP (Paket neanderfunk-ddhcpd, nur Images mit dem
# Feed fuer 2025.1-next). Welche Werte etwas sagen, hat die Packages-Session
# am 27.11.2026 beantwortet (Belege Neanderfunk/ddhcpd c4b7245):
# - roaming.in zaehlt weitergeleitete Verlaengerungen (DHCPREQUEST fuer eine
#   Adresse aus einem fremden Block), keine Roaming-Ereignisse: ein Client,
#   der woanders bleibt, zaehlt bei jeder Verlaengerung neu. roaming.out
#   zaehlt beim Eigner und dazu die Uebergaben nach einem Konflikt, also
#   out >= in. Fuer Summen nur in nehmen.
# - discover deutlich ueber offer ueber laengere Zeit: der Knoten bedient
#   seine Clients nicht. dhcp.nak ist Rauschen (Client mit Adresse aus einem
#   anderen Netz) und enthaelt die Ablehnungen durch den Eigner;
#   roaming.nak_received waechst stetig nur, wenn ein Client in einem
#   Konflikt pendelt.
# - learning=1 dauert ab Werk 30 s; ueber mehrere Proben heisst es: der
#   Daemon startet im Kreis neu. Waehrend der Lernphase fehlt der Block
#   "blocks" ganz, die Werte sind dann nicht 0.
# - Alle Zaehler beginnen bei jedem Start des Daemons bei 0 (Neustart,
#   Domainwechsel, Respawn). Ueberlaeufe kommen nicht vor, rate() reicht.
# Weggelassen: dhcp.inform, dhcp.release, roaming.ack_*, conflicts.won (nur
# eine Untergrenze).
JE_STUNDE = 'suffix: /h'


def dd(schluessel, filter_='nodeid="$node"'):
    return '{__name__="node_nf.ddhcpd.%s", %s}' % (schluessel, filter_)


def je_stunde(auswahl):
    return 'sum(rate(%s[$__rate_interval])) * 3600' % auswahl


PANELS = KOPF + [
    panel(1, 'Clients', [
        ziel('max({__name__="node_clients.total", nodeid="$node"})', 'gesamt', 'A'),
        ziel('max({__name__="node_clients.wifi24", nodeid="$node"})', '2,4 GHz', 'B'),
        ziel('max({__name__="node_clients.wifi5", nodeid="$node"})', '5 GHz', 'C'),
    ], 0, 5, min_=0, beschreibung='Gleichzeitig verbundene Geräte.'),

    panel(2, 'Bandbreite', [
        ziel('sum(rate({__name__="node_traffic.rx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'empfangen', 'A'),
        ziel('sum(rate({__name__="node_traffic.tx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'gesendet', 'B'),
        ziel('sum(rate({__name__="node_traffic.mgmt_rx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'Management empfangen', 'C'),
        ziel('sum(rate({__name__="node_traffic.mgmt_tx.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'Management gesendet', 'D'),
        ziel('sum(rate({__name__="node_traffic.forward.bytes", nodeid="$node"}[$__rate_interval])) * 8',
             'weitergereicht', 'E'),
    ], 12, 5, einheit='bps', min_=0,
        beschreibung='Alle Beträge positiv. Management ist der batman-eigene Verkehr '
                     '(OGMs und Nachbarschaft), weitergereicht ist Verkehr für andere '
                     'Knoten im Mesh.'),

    panel(3, 'Datenmenge je Tag', [
        ziel('sum(increase({__name__="node_traffic.rx.bytes", nodeid="$node"}[1d]))',
             'Empfangen', 'A', '1d'),
        ziel('sum(increase({__name__="node_traffic.tx.bytes", nodeid="$node"}[1d]))',
             'Gesendet', 'B', '1d'),
        # Fuer andere Knoten im Mesh durchgereicht (adorfer 11.10.2026). Oft
        # tausendmal so viel wie der eigene Verkehr, deshalb eigene Achse.
        ziel('sum(increase({__name__="node_traffic.forward.bytes", nodeid="$node"}[1d]))',
             'Weitergereicht', 'C', '1d'),
    ], 0, 13, einheit='bytes', min_=0, balken=True, stapeln=True,
        abweichend=[linie_rechts('Weitergereicht')],
        beschreibung='Tagesbilanz. Balken: eigener Verkehr des Knotens. Linie (Achse '
                     'rechts): für andere Knoten im Mesh weitergereicht. Bei Zeiträumen '
                     'unter zwei Tagen bleibt das Bild leer.'),

    # Airtime ausserhalb von 0 bis 100 Prozent ist immer ein Messfehler: der
    # mt76-Unterlauf mancher Gluon-Knoten und einmalig am 25.09.2026 um 11:02
    # die UniFi-APs (alte Bytezaehler gegen neue Airtime-Zaehler). Ohne die
    # Klammer sprengt ein einziger solcher Wert die Achse fuer die ganze Aufbewahrung.
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
        beschreibung='g ist 2,4 GHz, a ist 5 GHz. Dauerhaft über 60 Prozent belegt heißt: der Kanal ist voll.'),

    panel(5, 'Speicher', [
        ziel('max({__name__="node_memory.available", nodeid="$node"}) * 1024', 'verfügbar', 'A'),
        ziel('max({__name__="node_memory.free", nodeid="$node"}) * 1024', 'frei', 'B'),
    ], 0, 21, einheit='bytes', min_=0,
        beschreibung='Verfügbar ist der Wert, auf den es ankommt; frei allein sagt wenig.'),

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
        beschreibung='Frühindikator für Speichermangel: der Knoten liest ständig nach, '
                     'was er gerade verworfen hat. Braucht das Paket neanderfunk-respondd.'),

    panel(11, 'Ethernet', [
        ziel('max by (port) (nf_ethernet_speed{nodeid="$node"})', '{{port}} ausgehandelt', 'A'),
        ziel('max by (port) (nf_ethernet_possible{nodeid="$node"})', '{{port}} möglich', 'B'),
    ], 0, 45, einheit='Mbits', min_=0,
        beschreibung='Möglich größer als ausgehandelt heißt: der Port kam nicht hoch. '
                     'Ein toter Port meldet beides als 0, dafür nf_ethernet_carrier.'),

    panel(13, 'Ausfälle laut Knoten', [
        ziel('max({__name__="node_nf.ssid_changer.offline", nodeid="$node"})',
             'offline gegangen', 'A'),
        ziel('max({__name__="node_nf.ssid_changer.gateway_losses", nodeid="$node"})',
             'Gateway verloren', 'B'),
        ziel('max({__name__="node_nf.ssid_changer.switches", nodeid="$node"})',
             'SSID gewechselt', 'C'),
    ], 0, 53, min_=0,
        beschreibung='Zähler des SSID-Changers seit dem letzten Start. Ein Knoten kann '
                     'nicht melden, dass er offline ist; dieser Zähler steht danach aber '
                     'höher da und zeigt damit auch kurze Störungen ohne Neustart. '
                     'Springt er auf null, hat der Knoten neu gestartet. Nur mit dem '
                     'Paket neanderfunk-respondd.'),

    panel(12, 'zram', [
        ziel('max({__name__="node_nf.zram.data", nodeid="$node"}) * 1024', 'Daten', 'A'),
        ziel('max({__name__="node_nf.zram.ram", nodeid="$node"}) * 1024', 'im RAM', 'B'),
    ], 12, 45, einheit='bytes', min_=0,
        beschreibung='Wie viel komprimiert im Speicher liegt. Braucht das Paket neanderfunk-respondd.'),

    panel(14, 'ddhcpd: Adressen', [
        ziel('max(%s)' % dd('leases.total'), 'in eigenen Blöcken', 'A'),
        ziel('max(%s)' % dd('leases.leased'), 'vergeben', 'B'),
        ziel('max(%s)' % dd('leases.offered'), 'angeboten', 'C'),
        ziel('max(%s)' % dd('leases.away'), 'davon Client woanders', 'D'),
        ziel('max({__name__="node_nf.clients_ipv4.total", nodeid="$node"})',
             'Clients mit IPv4', 'E'),
        ziel('max({__name__="node_nf.clients_ipv4.ddhcpd", nodeid="$node"})',
             'davon von ddhcpd', 'F'),
    ], 12, 53, min_=0,
        beschreibung='Verteilter DHCP (ddhcpd), nur auf Images mit dem Paket '
                     'neanderfunk-ddhcpd. Die Leases zählen nur die eigenen Blöcke des '
                     'Knotens. "Client woanders": eigene Lease, deren Client gerade an '
                     'einem anderen Knoten hängt oder seit 300 s still ist. Clients mit '
                     'IPv4 sind die lokalen Clients mit bekannter Adresse; was nicht von '
                     'ddhcpd kommt, hat der Kea des Supernodes vergeben.'),

    panel(15, 'ddhcpd: Anfragen je Stunde', [
        ziel(je_stunde(dd('dhcp.discover')), 'DISCOVER', 'A'),
        ziel(je_stunde(dd('dhcp.offer')), 'OFFER', 'B'),
        ziel(je_stunde(dd('dhcp.ack')), 'ACK', 'C'),
        ziel(je_stunde(dd('dhcp.nak')), 'NAK an Clients', 'D'),
        ziel(je_stunde(dd('roaming.in')), 'Verlängerung weitergeleitet', 'E'),
        ziel(je_stunde(dd('roaming.out')), 'Verlängerung für eigene Blöcke', 'F'),
        ziel(je_stunde(dd('roaming.nak_received')), 'vom Eigner abgelehnt', 'G'),
    ], 0, 61, einheit=JE_STUNDE, min_=0,
        beschreibung='Bleibt OFFER länger deutlich unter DISCOVER, bekommen die Clients '
                     'an diesem Knoten keine Adresse. NAK an Clients ist normales Rauschen '
                     '(Client mit einer Adresse aus einem anderen Netz) und enthält die '
                     'Ablehnungen durch den Eigner. Weitergeleitet: Verlängerung für eine '
                     'Adresse aus dem Block eines anderen Knotens, einmal je Verlängerung, '
                     'also kein Zählwerk für Roaming. Für eigene Blöcke: die Gegenseite, '
                     'dazu Übergaben nach einem Konflikt. Steigt "vom Eigner abgelehnt" '
                     'stetig, pendelt ein Client in einem Konflikt.'),

    panel(16, 'ddhcpd: Blöcke und Zustand', [
        ziel('max(%s)' % dd('blocks.ours'), 'eigene Blöcke', 'A'),
        ziel('max(%s)' % dd('blocks.claiming'), 'im Anspruch', 'B'),
        ziel('max(%s)' % dd('blocks.releasing'), 'in Übergabe', 'C'),
        ziel('max(%s)' % dd('running'), 'Daemon läuft', 'D'),
        ziel('max(%s)' % dd('learning'), 'Lernphase', 'E'),
        ziel('max(%s)' % dd('conflicts.lost'), 'Konflikte verloren', 'F'),
    ], 12, 61, min_=0,
        beschreibung='Daemon läuft 0: ddhcpd ist tot, die anderen Werte fehlen dann. '
                     'Lernphase 1 über mehrere Proben (sie dauert nur 30 s): der Daemon '
                     'startet im Kreis neu. In der Lernphase fehlen die Blockwerte, sie '
                     'sind dann nicht 0. Eigene Blöcke 0, obwohl Clients mit IPv4 da '
                     'sind: der Knoten hat keinen Block bekommen. "In Übergabe" hält nur '
                     'eine Runde und ist im 5-Minuten-Raster fast immer 0. Konflikte '
                     'verloren zählt seit dem Start des Daemons; steigt er, zerfällt das '
                     'Mesh wiederholt in Inseln.'),
]

# --- Supernodes -------------------------------------------------------------
# Ein Supernode ist kein Knoten wie die anderen: kein WLAN, keine Airtime,
# keine Clients an ihm selbst. Interessant ist, was an ihm haengt. Je Domain
# tritt er als eigener Knoten auf (hostname <name>_<domain>, node_id
# f2beef00<dd><ss>). Das Dashboard fasst alle Instanzen eines Supernodes
# zusammen (adorfer 05.11.2026): die Domains wandern zwischen den Supernodes,
# je Instanz getrennt sagt der Verlauf nichts. Gewaehlt wird ueber <ss>, den
# hinteren Teil der node_id; der bleibt bei einer Umbenennung und bei einem
# Domainwechsel gleich. Gezeigt wird der Name aus dem Hostnamen. Eine Domain
# zaehlt also zu dem Supernode, auf dem sie zu der Zeit lief.
#
# KANTE bildet die Kanten auf die node_id der Gegenstelle ab. Damit lassen
# sich Werte der angebundenen Knoten summieren, ohne eine Liste zu pflegen:
# "* 0 + 1" macht aus der Kante einen Faktor 1, max by haelt jeden Knoten
# einmal, auch mit zwei Kanten.
SN = 'is_gateway="true", nodeid=~"f2beef00[0-9]{2}$sn"'
SN_KANTE = '"target.id"=~"f2beef00[0-9]{2}$sn"'

# CPU aus statistics.stat: Jiffies seit dem Boot, Anteil = Rate des Feldes
# durch die Summe der Raten aller Felder. Alle Instanzen eines Supernodes
# melden dieselbe Maschine, also max ueber die Instanzen.
CPU_FELDER = (('user', 'user'), ('nice', 'nice'), ('system', 'system'),
              ('softirq', 'softirq'), ('irq', 'irq'), ('iowait', 'iowait'), ('steal', 'steal'))
CPU_ALLE = 'user|nice|system|idle|iowait|irq|softirq|steal'


def cpu_anteil(f):
    return ('100 * max(rate({__name__="node_stat.cpu.%s", %s}[$__rate_interval])) / '
            'max(sum by (nodeid) (rate({__name__=~"node_stat.cpu.(%s)", %s}[$__rate_interval])))'
            % (f, SN, CPU_ALLE, SN))
KANTE = ('max by (nodeid) (label_replace(last_over_time({__name__="link_tq", %s}[15m]),'
         ' "nodeid", "$1", "source.id", "(.*)"))' % SN_KANTE)
DAHINTER = '%s * on(nodeid) group_left() (' + KANTE + ' * 0 + 1)'

# Alle Knoten der Domains, die der Supernode gerade traegt, ueber die
# Domainnummer verbunden. Nicht nur die mit Kante zu ihm: die meisten Knoten
# haengen per Mesh hinter einem anderen Knoten (am 05.11.2026 bei sinope 88
# mit Kante von 393), ihre Clients fehlten sonst.
SEINE_DOMAINS = ('(max by (dnum) (label_replace(last_over_time({__name__="node_load", %s}[15m]),'
                 ' "dnum", "$1", "domain", "[^0-9]*([0-9]+).*")) * 0 + 1)' % SN)


def in_seinen_domains(ausdruck):
    return ('sum(max by (nodeid, dnum) (label_replace(%s, "dnum", "$1", "site", ".*?([0-9]+)_.*"))'
            ' * on(dnum) group_left() %s)' % (ausdruck, SEINE_DOMAINS))

SUPERNODES = ('query_result(topk by (ss) (1, max by (sn, ss) (label_replace(label_replace('
              'tlast_over_time(node_load{is_gateway="true"}[$__range]), '
              '"ss", "$1", "nodeid", "f2beef00[0-9]{2}([0-9]{2})"), '
              '"sn", "$1", "hostname", "([a-z0-9]+)[_-].*"))))')

SUPERNODE_VARIABLEN = [
    {'name': 'sn', 'label': 'Supernode', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 3, 'query': SUPERNODES, 'refId': 'sn'},
     'definition': SUPERNODES,
     'regex': '/sn="(?<text>[^"]+)".*ss="(?<value>[^"]+)"/',
     'refresh': 1, 'sort': 1, 'includeAll': False, 'multi': False,
     'current': {}, 'options': []},
]


def summe(metrik):
    return ('sum(rate({__name__="node_traffic.%s.bytes", %s}[$__rate_interval])) * 8'
            % (metrik, SN))


def dahinter(metrik):
    return in_seinen_domains('rate({__name__="node_traffic.%s.bytes", firmware_base=~"gluon.*"}'
                             '[$__rate_interval])' % metrik) + ' * 8'


SUPERNODE_KOPF = [
    {
        'id': 100, 'title': 'Domains auf diesem Supernode', 'type': 'table',
        'datasource': QUELLE,
        'description': 'Instanzen, die gerade antworten, je Domain eine.',
        'gridPos': {'h': 5, 'w': 17, 'x': 0, 'y': 0},
        'targets': [dict(ziel('last_over_time({__name__="node_load", %s}[15m])' % SN,
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, 'Value': True, '__name__': True,
                                  'db': True, 'firmware_base': True,
                                  'firmware_image_name': True, 'firmware_subtarget': True,
                                  'firmware_release': True, 'firmware_target': True,
                                  'model': True, 'autoupdater': True, 'site': True,
                                  'is_gateway': True},
                'indexByName': {'domain': 0, 'hostname': 1, 'nodeid': 2},
                'renameByName': {'hostname': 'Instanz', 'nodeid': 'node_id',
                                 'domain': 'Domain'}}},
            {'id': 'sortBy', 'options': {'fields': {},
                                         'sort': [{'field': 'Domain', 'desc': False}]}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}}, 'overrides': []},
    },
    {
        'id': 101, 'title': 'Knoten an diesem Supernode', 'type': 'stat', 'datasource': QUELLE,
        'gridPos': {'h': 5, 'w': 7, 'x': 17, 'y': 0},
        'targets': [dict(ziel('count(%s)' % KANTE, 'Knoten', 'A'), instant=True, range=False)],
        'fieldConfig': {'defaults': {'decimals': 0, 'thresholds': {'mode': 'absolute', 'steps': [
            {'color': 'red', 'value': None}, {'color': 'green', 'value': 1}]}}, 'overrides': []},
        'options': {'colorMode': 'value', 'graphMode': 'area', 'textMode': 'auto',
                    'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False}},
    },
]

SUPERNODE_PANELS = SUPERNODE_KOPF + [
    panel(1, 'Angebundene Knoten und Domains', [
        ziel('count(%s)' % KANTE, 'Knoten', 'A'),
        ziel('count(count by (nodeid) (last_over_time({__name__="node_load", %s}[15m])))' % SN,
             'Domains', 'B'),
    ], 0, 5, min_=0, abweichend=[linie_rechts('Domains')],
        beschreibung='Knoten mit einer Kante zu einer Instanz dieses Supernodes, und wie '
                     'viele Domains er gerade trägt (rechte Achse). Springt die Zahl der '
                     'Domains, sind Domains umgezogen.'),

    panel(2, 'Clients dahinter', [
        ziel(in_seinen_domains('last_over_time({__name__="node_clients.total", '
                               'is_gateway="false"}[15m])'),
             'laut respondd', 'A'),
        # Verbunden ueber die Domainnummer: die Instanz meldet als Domain
        # ffnefdNN oder, seit der Umstellung der Supernodes, den Code der
        # Knoten (dus-23_dusuks). max by entfernt doppelte Reihen nach einem
        # Wechsel.
        ziel('sum(label_replace(last_over_time(tt_clients[15m]),'
             ' "dnum", "$1", "domain", "([0-9]+)_.*")'
             ' * on(dnum) group_left() (max by (dnum) (label_replace('
             'last_over_time({__name__="node_load", %s}[15m]),'
             ' "dnum", "$1", "domain", "[^0-9]*([0-9]+).*")) * 0 + 1))' % SN,
             'laut Übersetzungstabelle', 'B'),
    ], 12, 5, min_=0,
        beschreibung='Clients in den Domains, die der Supernode gerade trägt, auf zwei '
                     'Wegen gezählt. respondd: Summe von clients.total aller Knoten und '
                     'UniFi-APs dieser Domains, die gerade antworten. Übersetzungstabelle: '
                     'jede Station der Domains, auch hinter stummen Knoten, noch ein paar '
                     'Minuten nach dem Abmelden. Bis 05.11.2026 zählte respondd nur Knoten '
                     'mit direkter Kante zum Supernode und lag deshalb weit darunter.'),

    panel(3, 'Verkehr des Supernodes', [
        ziel(summe('forward'), 'weitergereicht', 'A'),
        ziel(summe('rx'), 'empfangen', 'B'),
        ziel(summe('tx'), 'gesendet', 'C'),
        ziel(summe('mgmt_rx'), 'Management empfangen', 'D'),
        ziel(summe('mgmt_tx'), 'Management gesendet', 'E'),
    ], 0, 13, einheit='bps', min_=0,
        beschreibung='Summe über alle Domaininstanzen des Supernodes. Empfangen und '
                     'gesendet ist der Verkehr zwischen Mesh und Internet, weitergereicht '
                     'der zwischen Knoten über den Supernode.'),

    panel(4, 'Verkehr der Knoten in seinen Domains', [
        ziel(dahinter('rx'), 'empfangen', 'A'),
        ziel(dahinter('tx'), 'gesendet', 'B'),
        ziel(dahinter('mgmt_rx'), 'Management empfangen', 'C'),
        ziel(dahinter('mgmt_tx'), 'Management gesendet', 'D'),
    ], 12, 13, einheit='bps', min_=0,
        beschreibung='Summe über die Gluon-Knoten der Domains, die der Supernode gerade '
                     'trägt, aus deren Sicht. Empfangen der Knoten sollte etwa gesendet des '
                     'Supernodes sein; die Differenz ist Verkehr, der im Mesh bleibt.'),

    panel(5, 'Linkqualität zu den Knoten', [
        ziel('min(last_over_time({__name__="link_tq", %s}[15m]))' % SN_KANTE, 'schlechteste', 'A'),
        ziel('avg(last_over_time({__name__="link_tq", %s}[15m]))' % SN_KANTE, 'Mittel', 'B'),
    ], 0, 21, einheit='percent', min_=0,
        beschreibung='TQ über alle Kanten. Fällt das Minimum, hat ein Knoten eine schlechte Anbindung.'),

    panel(6, 'Last der Maschine', [
        ziel('max({__name__="node_load", %s})' % SN, 'loadavg', 'A'),
        ziel('max({__name__="node_proc.running", %s})' % SN, 'laufende Prozesse', 'B'),
    ], 12, 21, min_=0,
        beschreibung='Alle respondd-Instanzen eines Supernodes melden dieselben '
                     'Systemwerte der Maschine.'),

    panel(7, 'Speicher der Maschine', [
        ziel('max({__name__="node_memory.available", %s}) * 1024' % SN, 'verfügbar', 'A'),
        ziel('max({__name__="node_memory.total", %s}) * 1024' % SN, 'gesamt', 'B'),
    ], 0, 29, einheit='bytes', min_=0),

    panel(8, 'Laufzeit', [
        ziel('max({__name__="node_time.up", %s})' % SN, 'Laufzeit', 'A'),
    ], 12, 29, einheit='s',
        beschreibung='Ein Sprung nach unten ist ein Neustart der Maschine '
                     '(23.09.2026 um 22:42 alle sechs, wegen batman-adv 2026.3).'),

    panel(10, 'CPU der Maschine', [
        ziel(cpu_anteil(f), name, chr(ord('A') + i)) for i, (f, name) in enumerate(CPU_FELDER)
    ], 0, 37, w=24, einheit='percent', min_=0, stapeln=True, legende_rechts=True,
        beschreibung='Anteile der CPU-Zeit aus /proc/stat (statistics.stat, seit 21.11.2026), '
                     'gestapelt, ohne idle. steal ist Zeit, die der Hypervisor der VM '
                     'vorenthalten hat: Sie fehlt dem Supernode, ohne dass loadavg sie zeigt.'),

    {
        'id': 9, 'title': 'Knoten an diesem Supernode', 'type': 'table', 'datasource': QUELLE,
        'description': 'Momentaufnahme mit Linkqualität, absteigend nach TQ.',
        'gridPos': {'h': 10, 'w': 24, 'x': 0, 'y': 45},
        'targets': [dict(ziel(kurzname('last_over_time({__name__="link_tq", %s}[15m])'
                                       % SN_KANTE, 'source.hostname'),
                              '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'organize', 'options': {
                'excludeByName': {'Time': True, '__name__': True, 'db': True,
                                  'target.addr': True, 'target.id': True,
                                  'source.addr': True},
                # Das Unterscheidende zuerst, der volle Name dahinter
                'indexByName': {'kurz': 0, 'Value': 1, 'target.hostname': 2,
                                'source.hostname': 3, 'type': 4, 'source.id': 5},
                'renameByName': {'kurz': 'Knoten', 'source.hostname': 'voller Name',
                                 'source.id': 'node_id', 'target.hostname': 'Instanz',
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
#
# Knoten mit Multidomain-Firmware (ab RC 26112621sta) melden als site_code nur
# "ffnef", die Domain steht im Label domain (21_dias). Fuer sie kommt die
# Nummer aus domain (gefunden am 27.11.2026: alle 74 RC-Knoten fehlten im
# Domain-Dashboard). Nur fuer Nicht-Gateways: die Domaininstanzen der
# Supernodes tragen domain ebenfalls, ihr Verkehr zaehlte sonst doppelt.
# UniFi-APs tragen in domain den site_code (lvrmo-33_lvrmo), der passt nicht
# auf den Anfang und aendert nichts.
DNUM_KNOTEN = ('label_replace(label_join(label_replace(%s, "dnum", "$1", "site", '
               '".*?([0-9]+)_.*"), "gw_domain", "/", "is_gateway", "domain"), '
               '"dnum", "$1", "gw_domain", "false/([0-9]+)_.*")')
DNUM_TT = ('label_replace(%s, "dnum", "$1", "domain", "([0-9]+)_.*")')


def dnum(ausdruck, tt=False):
    return (DNUM_TT if tt else DNUM_KNOTEN) % ausdruck


def in_domain(ausdruck):
    """Die Knotenreihen der Domain, ausgewaehlt ueber $domain."""
    return (dnum(ausdruck) + ' * on(dnum) group_left() ('
            + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True)
            + ' * 0 + 1)')


def je_domain(ausdruck, art='sum'):
    """Summe (oder max, min ...) ueber die Knoten einer Domain."""
    return art + '(' + in_domain(ausdruck) + ')'


def dd_domain(schluessel):
    """Momentaufnahme eines ddhcpd-Wertes, je Knoten der Domain."""
    return 'last_over_time({__name__="node_nf.ddhcpd.%s"}[15m])' % schluessel


def dd_domain_summe(schluessel):
    """Summe ueber die Knoten, je Knoten einmal: nach einem Firmwarewechsel
    liefert ein Knoten 15 Minuten lang zwei Reihen (gesehen beim Ausrollen
    des RC am 27.11.2026: 30 gemeldete Bloecke bei 22 belegten)."""
    return 'sum(max by (nodeid) (' + in_domain(dd_domain(schluessel)) + '))'


DD_FREI_MEDIAN = ('quantile(0.5, max by (nodeid) ('
                  + in_domain(dd_domain('blocks.free')) + '))')


def dd_domain_stunde(schluessel):
    return je_domain('rate({__name__="node_nf.ddhcpd.%s"}[$__rate_interval])'
                     % schluessel) + ' * 3600'


DOMAIN_VARIABLEN = [
    {'name': 'domain', 'label': 'Domain', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 1, 'query': 'label_values(tt_clients, domain)',
               'refId': 'domain'},
     'definition': 'label_values(tt_clients, domain)',
     'refresh': 1, 'sort': 1, 'includeAll': False, 'multi': False,
     'current': {}, 'options': []},
]


# Datenraten ohne feste Nachkommastellen: Grafana waehlt dann selbst so viele,
# dass drei gueltige Ziffern stehen (1.03 Gb/s, 45.6 Mb/s, 110 Mb/s), gut
# 1 % Aufloesung. Mit decimals 0 stand "1 Gb/s" fuer alles von 0,5 bis 1,5
# (adorfer 28.09.2026: mindestens etwa 5 % Genauigkeit).
DATENRATEN = {'bps', 'Bps', 'binbps', 'binBps', 'KBs', 'Kbits', 'MBs', 'Mbits', 'GBs', 'Gbits'}


# Farbe der Kennzahlen. Ohne eigene Schwellen nimmt Grafana seine Vorgabe
# (gruen, ab 80 rot): dann standen 1026 Knoten online rot und 45 offline gruen
# da (28.09.2026). Deshalb immer eigene Schwellen: gruen, oder "text" fuer
# Zahlen, die weder gut noch schlecht sind; orange erst ab warnung.
def zahl(nr, titel, ausdruck, x, w=6, einheit='', beschreibung='', warnung=None, y=0,
         farbe='green'):
    feld = {'unit': einheit}
    if einheit not in DATENRATEN:
        feld['decimals'] = 0
    stufen = [{'color': farbe, 'value': None}]
    if warnung is not None:
        stufen.append({'color': 'orange', 'value': warnung})
    feld['thresholds'] = {'mode': 'absolute', 'steps': stufen}
    return {
        'id': nr, 'title': titel, 'type': 'stat', 'datasource': QUELLE,
        'description': beschreibung,
        'gridPos': {'h': 5, 'w': w, 'x': x, 'y': y},
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
         beschreibung='Stationen in der Übersetzungstabelle, ohne die Knoten selbst.'),
    zahl(103, 'Clients laut respondd',
         je_domain('last_over_time({__name__="node_clients.total"}[15m])'), 18,
         beschreibung='Summe über die Knoten, die gerade geantwortet haben.'),

    panel(1, 'Clients', [
        ziel('last_over_time(tt_clients{domain="$domain"}[15m])', 'Übersetzungstabelle', 'A'),
        ziel(je_domain('last_over_time({__name__="node_clients.total"}[15m])'), 'respondd', 'B'),
    ], 0, 5, min_=0,
        beschreibung='Obergrenze und Untergrenze. Die Tabelle hält Stationen noch einige '
                     'Minuten nach dem Abmelden, respondd verfehlt alles hinter stummen Knoten.'),

    panel(2, 'Knoten', [
        ziel('last_over_time(tt_im_mesh{domain="$domain"}[15m])', 'im Mesh', 'A'),
        ziel('last_over_time(tt_dunkel{domain="$domain"}[15m])', 'dunkel', 'B'),
        ziel('last_over_time(tt_originatoren{domain="$domain"}[15m])', 'Originatoren', 'C'),
    ], 12, 5, min_=0,
        beschreibung='Originatoren sind mehr als Knoten: jede Mesh-Schnittstelle zählt '
                     'einzeln, im Schnitt etwa doppelt.'),

    panel(3, 'Verkehr der Domain', [
        ziel(je_domain('rate({__name__="node_traffic.rx.bytes"}[$__rate_interval])') + ' * 8',
             'empfangen', 'A'),
        ziel(je_domain('rate({__name__="node_traffic.tx.bytes"}[$__rate_interval])') + ' * 8',
             'gesendet', 'B'),
        ziel(je_domain('rate({__name__="node_traffic.mgmt_rx.bytes"}[$__rate_interval])') + ' * 8',
             'Management empfangen', 'C'),
        ziel(je_domain('rate({__name__="node_traffic.mgmt_tx.bytes"}[$__rate_interval])') + ' * 8',
             'Management gesendet', 'D'),
    ], 0, 13, einheit='bps', min_=0,
        beschreibung='Summe über alle Knoten der Domain, aus deren Sicht. Alle Beträge '
                     'positiv; Management ist der batman-eigene Verkehr.'),

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
        beschreibung='Kandidaten für den Austausch, unabhängig vom Gerätetyp.'),

    panel(6, 'Laufzeit der Knoten', [
        ziel('min(' + dnum('last_over_time({__name__="node_time.up"}[15m])')
             + ' * on(dnum) group_left() ('
             + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True) + ' * 0 + 1))',
             'kürzeste', 'A'),
        ziel('avg(' + dnum('last_over_time({__name__="node_time.up"}[15m])')
             + ' * on(dnum) group_left() ('
             + dnum('last_over_time(tt_clients{domain="$domain"}[15m])', tt=True) + ' * 0 + 1))',
             'im Mittel', 'B'),
    ], 12, 21, einheit='s', min_=0,
        beschreibung='Fällt die kürzeste Laufzeit ständig, startet dort etwas immer wieder neu.'),

    # Die Blocktabelle kennt jeder Knoten der Domain, aber aus seiner Sicht.
    # Die Packages-Session riet zu max (der optimistischste Knoten). Ein
    # gerade gestarteter Knoten sieht aber kurz fast alles frei: am
    # 27.11.2026 sprang max in 21_dias von 490 auf 511, "belegt" fiel auf 0.
    # Der Median bleibt ruhig (486 bis 496 ueber einen Tag).
    panel(7, 'ddhcpd: Blöcke und Leases', [
        ziel(DD_FREI_MEDIAN, 'Blöcke frei', 'A'),
        ziel(je_domain(dd_domain('blocks.total'), 'max') + ' - ' + DD_FREI_MEDIAN,
             'Blöcke belegt', 'B'),
        ziel(dd_domain_summe('blocks.ours'), 'davon gemeldet', 'C'),
        ziel(dd_domain_summe('leases.leased'), 'Leases vergeben', 'D'),
        ziel(dd_domain_summe('leases.away'), 'davon Client woanders', 'E'),
        ziel('count(count by (nodeid) (' + in_domain(dd_domain('running') + ' == 1') + '))',
             'Knoten mit ddhcpd', 'F'),
    ], 0, 29, min_=0, abweichend=[achse_rechts('Blöcke frei')],
        beschreibung='Verteilter DHCP (ddhcpd), nur Knoten mit dem Paket '
                     'neanderfunk-ddhcpd. Blöcke frei (Achse rechts): Median über die '
                     'Knoten; ein gerade gestarteter Knoten sieht kurz fast alles frei. '
                     'Bei 0 ist der Pool leer. '
                     'Liegt "davon gemeldet" unter "belegt", gehören die übrigen Blöcke '
                     'Knoten, die nichts melden (alte Firmware), oder es sind Ansprüche, '
                     'die noch nicht abgelaufen sind (300 s). "Client woanders": Lease '
                     'eines Knotens, deren Client gerade an einem anderen hängt.'),

    panel(8, 'ddhcpd: Anfragen je Stunde', [
        ziel(dd_domain_stunde('roaming.in'), 'Verlängerungen weitergeleitet', 'A'),
        ziel(dd_domain_stunde('dhcp.ack'), 'ACK an Clients', 'B'),
        ziel(dd_domain_stunde('dhcp.nak'), 'NAK an Clients', 'C'),
        ziel(dd_domain_stunde('roaming.nak_received'), 'vom Eigner abgelehnt', 'D'),
        ziel(dd_domain_stunde('conflicts.lost'), 'Konflikte verloren', 'E'),
    ], 12, 29, einheit=JE_STUNDE, min_=0,
        beschreibung='Summe über die Knoten der Domain. Weitergeleitet: Verlängerung '
                     'einer Adresse aus dem Block eines anderen Knotens, einmal je '
                     'Verlängerung; das misst, wie viel Roaming es gibt, zählt aber keine '
                     'Wechsel. NAK an Clients ist normales Rauschen. Konflikte entstehen, '
                     'wenn die Domain in Inseln zerfiel und wieder zusammenwächst.'),
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


# --- Community ----------------------------------------------------------------
# Die Gesamtsicht (adorfer 25.09.2026, Vorbild die "Global"-Seite der alten
# Karte): grosse Zahlen fuer das, was jetzt gilt, Verlaeufe fuer das, woran
# man einen Trend sieht, etwa das Ausrollen einer Firmware oder den Austausch
# alter Hardware.
#
# Gezaehlt wird aus den Knotenmetriken und nicht aus yanics fertigen Zaehlern
# (firmware_count, model_count): die mischen Gluon-Knoten, UniFi-APs und
# Supernodes. Hier stehen die drei Arten getrennt.
#
# Verkehr nur ueber die Gluon-Knoten: was ein AP uebertraegt, laeuft auch ueber
# das LAN seines Routers, und die Gateways sehen alles noch einmal.
#
# $domain waehlt Domains aus (mehrere, oder alle). Die Knoten tragen den
# gemeldeten site_code (nef-05_mon, lvrso-35_lvrso_EOL), die Auswahl den
# Domaincode (05_mon); der steckt in jedem site_code.
FENSTER = '[10m]'   # yanic fragt alle 5 Minuten
AUSWAHL = 'site=~".*(${domain:regex}).*"'
GLUON = 'firmware_base=~"gluon.*", ' + AUSWAHL
UNIFI = 'firmware_base="UniFi", ' + AUSWAHL
GATEWAY = 'is_gateway="true"'


def jetzt(metrik, filter_):
    return 'last_over_time({__name__="%s", %s}%s)' % (metrik, filter_, FENSTER)


def knoten(filter_):
    """Knoten, die gerade antworten, je Knoten einmal (ein Firmwarewechsel
    macht für ein paar Minuten zwei Reihen daraus)."""
    return 'count(count by (nodeid) (%s))' % jetzt('node_load', filter_)


def verteilung(label, filter_, leer='unbekannt'):
    return ('label_replace(count by (%s) (%s), "%s", "%s", "%s", "")'
            % (label, jetzt('node_load', filter_), label, leer, label))


def supernodes():
    """Supernodes selbst, nicht ihre Instanzen: je Domain läuft auf einem
    Supernode eine Instanz, Hostname <supernode>_<domain_code>."""
    return ('count(count by (supernode) (label_replace(%s, "supernode", "$1", '
            '"hostname", "([^_]+)_.*")))' % jetzt('node_load', GATEWAY))


def je_supernode():
    """rx+tx der Gateway-Instanzen, je Supernode summiert. Den Supernode
    traegt der Hostname vorn (<supernode>_<domain_code>); rate() wirft den
    Metriknamen weg, danach passen rx und tx Punkt fuer Punkt zusammen."""
    return ('sum by (supernode) (label_replace('
            'rate({__name__="node_traffic.rx.bytes", %(gw)s}[$__rate_interval]) + '
            'rate({__name__="node_traffic.tx.bytes", %(gw)s}[$__rate_interval]), '
            '"supernode", "$1", "hostname", "([a-z0-9]+)[_-].*"))' % {'gw': GATEWAY})


def verkehr(richtung):
    return ('sum(rate({__name__="node_traffic.%s.bytes", %s}[$__rate_interval])) * 8'
            % (richtung, GLUON))


COMMUNITY_VARIABLEN = [
    {'name': 'domain', 'label': 'Domain', 'type': 'query', 'datasource': QUELLE,
     'query': {'qryType': 1, 'query': 'label_values(tt_clients, domain)',
               'refId': 'domain'},
     'definition': 'label_values(tt_clients, domain)',
     'refresh': 1, 'sort': 1, 'includeAll': True, 'allValue': '.*', 'multi': True,
     'current': {'selected': True, 'text': ['All'], 'value': ['$__all']},
     'options': []},
]

TAG = 86400
# Grafanas Einheit 'd' schreibt auch in der deutschen Oberflaeche "days";
# ein eigenes Suffix bleibt deutsch.
TAGE = 'suffix: Tage'

# Domainhelper (statistics.neanderfunk.domainhelper, yanic-Fork dab4259).
# from/to/peer_domain/follow_domain sind Domaincodes (21_dias), anders als
# site. Die Reihen gibt es nur, solange ein Knoten den Teil meldet.
DH_FENSTER = '[30d]'
DH_WECHSEL = kurzname(
    'max by (nodeid, hostname, from, to, how) (last_over_time('
    '{__name__="nf_domainhelper_last_switch_time", from=~"${domain:regex}"}%(f)s)) * 1000 or '
    'max by (nodeid, hostname, from, to, how) (last_over_time('
    '{__name__="nf_domainhelper_last_switch_time", to=~"${domain:regex}"}%(f)s)) * 1000'
    % {'f': DH_FENSTER})


def dh_teil(metrik, art, labels):
    return ('label_replace(max by (nodeid, hostname, %s) (last_over_time({__name__="%s", %s}%s)), '
            '"art", "%s", "", "")' % (labels, metrik, AUSWAHL, FENSTER, art))


DH_AKTIV = kurzname(' or '.join([
    dh_teil('nf_domainhelper_bridge_age', 'Brücke', 'state, where, peer_domain, peer_node, note'),
    dh_teil('nf_domainhelper_follow_age', 'follow', 'follow_domain, rule'),
    dh_teil('nf_domainhelper_island_age', 'Insel', 'site'),
]))


def tabelle(nr, titel, ausdruck, x, y, w=24, h=8, beschreibung='', spalten=None,
            sortieren=None, einheit_wert=''):
    """Momentaufnahme als Tabelle. spalten: Label -> Ueberschrift, in dieser
    Reihenfolge; alle anderen Labels fallen weg."""
    spalten = spalten or {}
    return {
        'id': nr, 'title': titel, 'type': 'table', 'datasource': QUELLE,
        'description': beschreibung,
        'gridPos': {'h': h, 'w': w, 'x': x, 'y': y},
        'targets': [dict(ziel(ausdruck, '', 'A'), instant=True, range=False, format='table')],
        'transformations': [
            {'id': 'filterFieldsByName', 'options': {'include': {'names': list(spalten)}}},
            {'id': 'organize', 'options': {
                'indexByName': {k: i for i, k in enumerate(spalten)},
                'renameByName': spalten}},
        ] + ([{'id': 'sortBy', 'options': {'fields': {}, 'sort': [
            {'field': sortieren, 'desc': sortieren == 'Zeit'}]}}] if sortieren else []),
        'options': {'showHeader': True},
        # Die Einheit gilt nur fuer Zahlen, die Labelspalten sind Text
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}, 'unit': einheit_wert},
                        'overrides': []},
    }


def domaintabelle(nr, titel, spalten, x, y, w=24, h=8, beschreibung=''):
    """Eine Zeile je Domain, eine Spalte je Abfrage. spalten: Liste von
    (Ueberschrift, Ausdruck), jeder Ausdruck aggregiert by (domain)."""
    namen = {'domain': 'Domain'}
    namen.update({'Value #%s' % chr(65 + i): n for i, (n, _) in enumerate(spalten)})
    return {
        'id': nr, 'title': titel, 'type': 'table', 'datasource': QUELLE,
        'description': beschreibung,
        'gridPos': {'h': h, 'w': w, 'x': x, 'y': y},
        'targets': [dict(ziel(a, '', chr(65 + i)), instant=True, range=False, format='table')
                    for i, (_, a) in enumerate(spalten)],
        'transformations': [
            {'id': 'merge', 'options': {}},
            {'id': 'filterFieldsByName', 'options': {'include': {'names': list(namen)}}},
            {'id': 'organize', 'options': {
                'indexByName': {k: i for i, k in enumerate(namen)},
                'renameByName': namen}},
            {'id': 'sortBy', 'options': {'fields': {}, 'sort': [{'field': 'Domain'}]}},
        ],
        'options': {'showHeader': True},
        'fieldConfig': {'defaults': {'custom': {'align': 'auto'}, 'decimals': 0},
                        'overrides': []},
    }


# ddhcpd laeuft nur auf Multidomain-Firmware, und die meldet als site nur
# "ffnef": ausgewaehlt wird hier ueber das Label domain, nicht ueber AUSWAHL.
DD_AUSWAHL = 'domain=~"${domain:regex}"'


def dd_jetzt(schluessel, art='sum', parameter=''):
    """ddhcpd-Momentaufnahme je Domain; je Knoten erst einmal zusammengefasst,
    ein Firmwarewechsel macht fuer ein paar Minuten zwei Reihen daraus."""
    return '%s by (domain) (%smax by (domain, nodeid) (%s))' % (
        art, parameter, jetzt('node_nf.ddhcpd.' + schluessel, DD_AUSWAHL))


def dd_tag(schluessel):
    return ('sum by (domain) (increase({__name__="node_nf.ddhcpd.%s", %s}[1d]))'
            % (schluessel, DD_AUSWAHL))


DD_LAEUFT = 'max by (domain, nodeid) (%s)' % jetzt('node_nf.ddhcpd.running', DD_AUSWAHL)
DD_TABELLE = [
    ('Knoten mit ddhcpd', 'count by (domain) (%s == 1)' % DD_LAEUFT),
    # "or ... * 0": eine 0 statt eines leeren Feldes, solange alle laufen
    ('Daemon aus', 'count by (domain) (%s == 0) or count by (domain) (%s) * 0'
     % (DD_LAEUFT, DD_LAEUFT)),
    # Median statt max, siehe Domain-Dashboard
    ('Blöcke frei', dd_jetzt('blocks.free', 'quantile', '0.5, ')),
    ('Blöcke belegt', dd_jetzt('blocks.total', 'max') + ' - '
     + dd_jetzt('blocks.free', 'quantile', '0.5, ')),
    ('Leases vergeben', dd_jetzt('leases.leased')),
    ('Client woanders', dd_jetzt('leases.away')),
    ('Clients mit ddhcpd-Adresse', 'sum by (domain) (max by (domain, nodeid) (%s))'
     % jetzt('node_nf.clients_ipv4.ddhcpd', DD_AUSWAHL)),
    ('Verlängerungen weitergeleitet 24 h', dd_tag('roaming.in')),
    ('NAK an Clients 24 h', dd_tag('dhcp.nak')),
    ('Konflikte verloren 24 h', dd_tag('conflicts.lost')),
]


COMMUNITY_PANELS = [
    # Erste Zeile: wer ist da
    zahl(100, 'Gluon-Knoten online', knoten(GLUON), 0, w=4,
         beschreibung='Gluon-Knoten, die in den letzten 10 Minuten geantwortet haben.'),
    zahl(101, 'Knoten offline', 'count(count by (nodeid) (last_over_time({__name__="node_load", '
         + GLUON + '}[7d]))) - ' + knoten(GLUON), 4, w=4,
         farbe='text',
         beschreibung='In den letzten 7 Tagen gesehen, jetzt nicht.'),
    zahl(102, 'UniFi-APs online', knoten(UNIFI), 8, w=4,
         beschreibung='Accesspoints aus dem UniFi-Controller, die an einem Freifunk-Router hängen.'),
    zahl(103, 'Supernodes', supernodes(), 12, w=4,
         beschreibung='Supernodes, die antworten. Unabhängig von der Domainauswahl.'),
    zahl(109, 'Gateway-Instanzen', knoten(GATEWAY), 16, w=4,
         beschreibung='Je Domain eine Instanz auf einem Supernode. Unabhängig von der '
                      'Domainauswahl.'),
    zahl(104, 'Clients', 'sum(' + jetzt('node_clients.total', 'is_gateway="false", ' + AUSWAHL) + ')',
         20, w=4,
         beschreibung='Summe über Knoten und APs; Clients an einem AP zählen nur dort, '
                      'nicht noch einmal beim Router.'),
    # Zweite Zeile: was laeuft
    zahl(105, 'Download jetzt', verkehr('rx'), 0, einheit='bps', y=5,
         beschreibung='Was die Knoten an ihre Clients ausliefern, Summe über alle Gluon-Knoten.'),
    zahl(106, 'Upload jetzt', verkehr('tx'), 6, einheit='bps', y=5,
         beschreibung='Was die Clients über die Knoten ins Netz schicken.'),
    zahl(107, 'Laufzeit im Mittel', 'avg(' + jetzt('node_time.up', GLUON) + ') / %d' % TAG,
         12, einheit=TAGE, y=5, beschreibung='Tage seit dem letzten Start, Mittel über die Gluon-Knoten.'),
    zahl(108, 'Laufzeit höchste', 'max(' + jetzt('node_time.up', GLUON) + ') / %d' % TAG,
         18, einheit=TAGE, y=5, beschreibung='Der Knoten, der am längsten durchläuft.'),

    panel(1, 'Knoten', [
        ziel(knoten(GLUON), 'Gluon-Knoten', 'A'),
        ziel(knoten(UNIFI), 'UniFi-APs', 'B'),
        ziel(knoten(GATEWAY), 'Gateway-Instanzen', 'C'),
        ziel(supernodes(), 'Supernodes', 'D'),
    ], 0, 10, min_=0),
    panel(2, 'Clients', [
        ziel('sum(' + jetzt('node_clients.total', 'is_gateway="false", ' + AUSWAHL) + ')', 'gesamt', 'A'),
        ziel('sum(' + jetzt('node_clients.total', UNIFI) + ')', 'davon an UniFi-APs', 'B'),
        ziel('sum(' + jetzt('node_clients.wifi24', 'is_gateway="false", ' + AUSWAHL) + ')', '2,4 GHz', 'C'),
        ziel('sum(' + jetzt('node_clients.wifi5', 'is_gateway="false", ' + AUSWAHL) + ')', '5 GHz', 'D'),
    ], 12, 10, min_=0),

    panel(3, 'Verkehr', [
        ziel(verkehr('rx'), 'Download', 'A'),
        ziel(verkehr('tx'), 'Upload', 'B'),
        ziel(verkehr('forward'), 'weitergeleitet', 'C'),
        ziel(verkehr('mgmt_rx'), 'Management empfangen', 'D'),
        ziel(verkehr('mgmt_tx'), 'Management gesendet', 'E'),
    ], 0, 18, einheit='bps', min_=0,
        beschreibung='Summe über die Gluon-Knoten, aus deren Sicht. Management ist der '
                     'batman-eigene Verkehr.'),
    # Was ein Knoten empfaengt, hat ein Gateway gesendet, und umgekehrt: beide
    # Summen muessen fast gleich sein (am 25.09.2026: 764 zu 771 Mbit/s und
    # 65,2 zu 64,8 Mbit/s). Deshalb zaehlt oben nur eine Seite; zusammengezaehlt
    # waere es glatt verdoppelt (adorfer). Gehen die Linien auseinander, misst
    # eine Seite falsch oder es laeuft viel Verkehr direkt zwischen Knoten.
    panel(13, 'Gegenprobe: Knoten und Gateways', [
        ziel(verkehr('rx'), 'Knoten empfangen', 'A'),
        ziel('sum(rate({__name__="node_traffic.tx.bytes", %s}[$__rate_interval])) * 8' % GATEWAY,
             'Gateways gesendet', 'B'),
        ziel(verkehr('tx'), 'Knoten gesendet', 'C'),
        ziel('sum(rate({__name__="node_traffic.rx.bytes", %s}[$__rate_interval])) * 8' % GATEWAY,
             'Gateways empfangen', 'D'),
    ], 0, 74, w=24, einheit='bps', min_=0,
        beschreibung='Je zwei Linien sollten aufeinanderliegen. Gilt für alle Domains; '
                     'die Gateways lassen sich nicht nach Domain auswählen.'),
    # Anteil je Supernode an 100 %, gestapelt wie die Firmware (adorfer
    # 05.11.2026). Der Anteil kommt aus der Abfrage, nicht aus Grafanas
    # Prozent-Stapel: so stehen in Legende und Tooltip Prozente, keine bit/s.
    panel(14, 'Verkehr nach Supernode', [
        ziel('%s / scalar(sum(%s)) * 100' % (je_supernode(), je_supernode()),
             '{{supernode}}', 'A'),
    ], 0, 82, w=24, h=9, einheit='percent', min_=0, stapeln=True, sortieren=True,
        legende_rechts=True,
        beschreibung='Anteil jedes Supernodes am Verkehr aller Gateways (empfangen und '
                     'gesendet), zusammen 100 %. Verschiebt sich, wenn Domains umziehen. '
                     'Gilt für alle Domains, unabhängig von der Auswahl.'),
    panel(4, 'Datenmenge je Tag', [
        ziel('sum(increase({__name__="node_traffic.rx.bytes", %s}[1d]))' % GLUON, 'Download', 'A', '1d'),
        ziel('sum(increase({__name__="node_traffic.tx.bytes", %s}[1d]))' % GLUON, 'Upload', 'B', '1d'),
    ], 12, 18, einheit='bytes', min_=0, balken=True, stapeln=True),

    panel(5, 'Laufzeit', [
        ziel('avg(' + jetzt('node_time.up', GLUON) + ') / %d' % TAG, 'Mittel', 'A'),
        ziel('quantile(0.5, ' + jetzt('node_time.up', GLUON) + ') / %d' % TAG, 'Median', 'B'),
        ziel('max(' + jetzt('node_time.up', GLUON) + ') / %d' % TAG, 'höchste', 'C'),
    ], 0, 26, einheit=TAGE, min_=0,
        beschreibung='Tage seit dem letzten Start. Der wöchentliche Neustart (Do 3:15) '
                     'begrenzt die meisten Knoten auf sieben Tage.'),
    panel(6, 'Autoupdater', [
        ziel(verteilung('autoupdater', GLUON), '{{autoupdater}}', 'A'),
    ], 12, 26, min_=0, stapeln=True, sortieren=True,
        beschreibung='Zweig, dem die Knoten folgen.'),

    panel(7, 'Firmware', [
        ziel(verteilung('firmware_release', GLUON), '{{firmware_release}}', 'A'),
    ], 0, 34, w=24, h=10, min_=0, stapeln=True, sortieren=True,
        beschreibung='Gluon-Knoten je Firmwarestand, gestapelt. Beim Ausrollen wandert die '
                     'Fläche von einem Stand zum nächsten.'),

    panel(8, 'Targets', [
        ziel(verteilung('firmware_target', GLUON), '{{firmware_target}}', 'A'),
    ], 0, 44, min_=0, stapeln=True, sortieren=True,
        beschreibung='Plattform der Gluon-Knoten. "unbekannt": ältere Firmware meldet sie nicht.'),
    panel(9, 'Arbeitsspeicher', [
        ziel('count(count by (nodeid) (%s < 40000))' % jetzt('node_memory.total', GLUON), 'bis 32 MB', 'A'),
        ziel('count(count by (nodeid) (%s >= 40000 < 80000))' % jetzt('node_memory.total', GLUON), '64 MB', 'B'),
        ziel('count(count by (nodeid) (%s >= 80000 < 160000))' % jetzt('node_memory.total', GLUON), '128 MB', 'C'),
        ziel('count(count by (nodeid) (%s >= 160000))' % jetzt('node_memory.total', GLUON), '256 MB und mehr', 'D'),
    ], 12, 44, min_=0, stapeln=True, sortieren=True,
        beschreibung='Gluon-Knoten nach Arbeitsspeicher. Beim Austausch alter Hardware '
                     'schrumpfen die unteren Klassen.'),

    panel(10, 'Geräte', [
        ziel('topk_last(20, ' + verteilung('model', GLUON) + ', "model=andere")', '{{model}}', 'A'),
    ], 0, 52, w=24, h=12, min_=0, stapeln=True, sortieren=True,
        beschreibung='Die 20 häufigsten Modelle der Gluon-Knoten, der Rest als "andere".'),

    panel(11, 'UniFi-APs: Firmware', [
        ziel(verteilung('firmware_release', UNIFI), '{{firmware_release}}', 'A'),
    ], 0, 64, min_=0, stapeln=True, sortieren=True),
    panel(12, 'UniFi-APs: Modelle', [
        ziel(verteilung('model', UNIFI), '{{model}}', 'A'),
    ], 12, 64, min_=0, stapeln=True, sortieren=True),

    tabelle(15, 'Domainwechsel', DH_WECHSEL, 0, 91, h=10,
            beschreibung='Letzter Domainwechsel je Knoten laut neanderfunk-domainhelper '
                         '(ab 0.12, Feed b99b4e6, also erst ab dem Build danach), aus den '
                         'letzten 30 Tagen, neueste zuerst. Der Knoten merkt sich den Wechsel '
                         'im Flash, er bleibt über Neustart und sysupgrade stehen. Die Zeit '
                         'kommt vom Knoten: ohne NTP vor dem Wechsel kann sie falsch sein. '
                         'Gefiltert wird über von oder nach.',
            sortieren='Zeit',
            spalten={'kurz': 'Knoten', 'from': 'von', 'to': 'nach', 'how': 'wodurch',
                     'Value': 'Zeit', 'hostname': 'voller Name', 'nodeid': 'node_id'},
            einheit_wert='dateTimeAsIso'),
    tabelle(16, 'Domainhelper gerade aktiv', DH_AKTIV, 0, 101, h=8,
            beschreibung='Was neanderfunk-domainhelper gerade tut, im Normalfall leer. '
                         'Brücke: fremde Domain am Kabel, Zustand bridge (bleibt, Grund in '
                         'Hinweis) oder cut (getrennt), Nachbar mit Domain und node_id. '
                         'follow: das Netz kommt aus einer anderen Domain, Regel R1 (Kabel) '
                         'oder R2 (nur fremde Gateways); gewechselt wird, wenn das Alter die '
                         'Wartezeit erreicht. Insel: kein Gateway. Alter seit dem Ereignis.',
            sortieren='Alter',
            spalten={'art': 'Art', 'kurz': 'Knoten', 'state': 'Zustand', 'where': 'Port',
                     'peer_domain': 'Nachbar-Domain', 'peer_node': 'Nachbar',
                     'follow_domain': 'folgt', 'rule': 'Regel', 'note': 'Hinweis',
                     'Value': 'Alter', 'hostname': 'voller Name', 'nodeid': 'node_id'},
            einheit_wert='s'),

    domaintabelle(17, 'ddhcpd je Domain', DD_TABELLE, 0, 109, h=10,
                  beschreibung='Verteilter DHCP, nur Domains mit Knoten, die das Paket '
                               'neanderfunk-ddhcpd haben. Daemon aus: Knoten, deren ddhcpd '
                               'nicht antwortet. Blöcke frei: Median über die Knoten der '
                               'Domain; bei 0 ist der Pool leer. Weitergeleitete '
                               'Verlängerungen zählen jede Verlängerung einer Adresse aus '
                               'einem fremden Block, keine Wechsel. Zähler beginnen bei '
                               'jedem Start des Daemons bei 0.'),
]


COMMUNITY = {
    'uid': 'nf-community',
    'title': 'Community',
    'description': 'Gesamtsicht: Knoten, APs, Gateways, Clients, Verkehr, Laufzeit, '
                   'Firmware- und Hardwarestände im Verlauf.',
    'tags': ['neanderfunk'],
    'timezone': 'browser',
    'schemaVersion': 39,
    'version': 1,
    'refresh': '5m',
    'time': {'from': 'now-30d', 'to': 'now'},
    'templating': {'list': COMMUNITY_VARIABLEN},
    'panels': COMMUNITY_PANELS,
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
    'description': 'Ein Supernode mit allen seinen Domaininstanzen und was an '
                   'ihm hängt.',
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
    json.dump({'supernode': SUPERNODE, 'domain': DOMAIN,
               'community': COMMUNITY}.get(was, DASHBOARD),
              sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
