#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Knotensuche: alte Adresse, node_id oder MAC -> aktuelle Adressen.

  GET /nf/lookup?ip=<IPv6>      genau diese Adresse, sonst die unteren 64 Bit
                                (Interface-ID) gegen alle bekannten Adressen,
                                Praefix egal (oeffentlich, ULA, Link-Local)
  GET /nf/lookup?node_id=<hex>  12 Hex-Zeichen, Trennzeichen egal
  GET /nf/lookup?mac=<MAC>      Schreibweise egal (aa:bb.., AA-BB.., aabb.cc..)

Wechselt ein Knoten den Supernode, wechselt sein oeffentliches /64; die
Interface-ID (EUI-64 aus der primaeren MAC) bleibt. Gemerkte Adressen in
Skripten und Notizen veralten so laufend. Diese Suche macht aus einer alten
Adresse die aktuellen (Auftrag adorfer ueber die Packages-Session, 25.11.2026).

Quelle ist das Adressbuch (sammler/adressbuch.py, alle zwei Minuten neu):
/var/www/karte-en/api/<community>/targets.json. Dieselben Daten wie dort,
nichts darueber hinaus. Ein Knoten faellt dort nie heraus; ein ausgefallener
steht mit online false und der zuletzt bekannten Adresse da.

Von Hand vergebene Interface-IDs (unter 2^32, etwa ::1 der Supernodes) gibt
es in jedem Praefix; sie zaehlen nur bei genau gleicher Adresse, sonst kaeme
fuer ::1 jeder Supernode zurueck. Findet die Interface-ID keine bekannte
Adresse und ist sie eine EUI-64, wird daraus die MAC und damit die node_id
(Gluon: node_id = primaere MAC).

Antwort JSON: {"query", "generated", "nodes": [{node_id, hostname, domain,
site_code, addresses, online, last_seen, match}]}; bei mehreren Treffern alle,
bei keinem 404, bei unbrauchbarer Anfrage 400.

Laeuft hinter nginx (web/konfig-erzeugen.py, location = /nf/lookup), lauscht
nur auf 127.0.0.1. Die Community setzt nginx per Kopfzeile X-Karte-Community.

  knotensuche.py [--port 8782]
"""
import ipaddress
import json
import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = '/var/www/karte-en/api'
PFAD = '/nf/lookup'
MASKE64 = (1 << 64) - 1
VON_HAND = 1 << 32  # Interface-IDs darunter nur bei genau gleicher Adresse


def hex12(text):
    """MAC oder node_id in beliebiger Schreibweise -> 12 Hex klein, sonst None."""
    h = re.sub(r'[\s:.\-]', '', (text or '').strip().lower())
    return h if re.fullmatch(r'[0-9a-f]{12}', h) else None


def ipv6(text):
    """Adresse tolerant lesen: Klammern, Zone (%bat0), /Praefix, Leerraum."""
    t = (text or '').strip().strip('[]')
    t = t.split('%', 1)[0].split('/', 1)[0].strip('[]')
    try:
        a = ipaddress.ip_address(t)
    except ValueError:
        return None
    return a if a.version == 6 else None


def eui64_mac(iid):
    """Interface-ID -> MAC (12 Hex), wenn sie eine EUI-64 ist, sonst None."""
    b = iid.to_bytes(8, 'big')
    if b[3:5] != b'\xff\xfe':
        return None
    return bytes([b[0] ^ 0x02, b[1], b[2], b[5], b[6], b[7]]).hex()


class Bestand:
    """targets.json je Community, neu gelesen, sobald sich die Datei aendert."""

    def __init__(self, api=API):
        self.api = api
        self.sperre = threading.Lock()
        self.stand = {}

    def holen(self, community):
        pfad = os.path.join(self.api, community, 'targets.json')
        try:
            mtime = os.stat(pfad).st_mtime
        except OSError:
            return None
        with self.sperre:
            alt = self.stand.get(community)
            if alt and alt[0] == mtime:
                return alt[1]
        with open(pfad, encoding='utf-8') as f:
            d = json.load(f)
        nodes = d.get('nodes') or {}
        iid, adresse = {}, {}
        for nid, n in nodes.items():
            for a in n.get('addresses') or []:
                x = ipv6(a)
                if x:
                    adresse.setdefault(int(x), set()).add(nid)
                    iid.setdefault(int(x) & MASKE64, set()).add(nid)
        index = {'generated': d.get('generated'), 'nodes': nodes, 'iid': iid, 'adresse': adresse}
        with self.sperre:
            self.stand[community] = (mtime, index)
        return index


def suchen(index, ip=None, node_id=None, mac=None):
    """-> Liste (node_id, match). Reihenfolge: Adresse, Interface-ID, EUI-64, node_id, mac."""
    nodes, treffer = index['nodes'], []

    def dazu(nid, wie):
        if nid in nodes and nid not in [t[0] for t in treffer]:
            treffer.append((nid, wie))

    if ip is not None:
        for nid in sorted(index['adresse'].get(int(ip), ())):
            dazu(nid, 'address')
        i = int(ip) & MASKE64
        if i >= VON_HAND:
            for nid in sorted(index['iid'].get(i, ())):
                dazu(nid, 'interface-id')
        if not treffer:
            m = eui64_mac(i)
            if m:
                dazu(m, 'eui64')
    if node_id:
        dazu(node_id, 'node_id')
    if mac:
        dazu(mac, 'mac')
    return treffer


def eintrag(nid, n, wie):
    return {'node_id': nid, 'hostname': n.get('hostname'), 'domain': n.get('domain'),
            'site_code': n.get('site_code'), 'addresses': n.get('addresses') or [],
            'online': n.get('online'), 'last_seen': n.get('last_seen'), 'match': wie}


def antwort(bestand, community, query):
    """-> (HTTP-Status, Objekt). Getrennt vom Server, damit es testbar bleibt."""
    if not re.fullmatch(r'[a-z0-9]{1,32}', community or ''):
        return 404, {'error': 'unbekannte Karte'}
    q = urllib.parse.parse_qs(query or '', keep_blank_values=True)
    roh = {k: (q.get(k) or [''])[0] for k in ('ip', 'node_id', 'mac') if k in q}
    if not roh:
        return 400, {'error': 'ip, node_id oder mac angeben',
                     'beispiel': PFAD + '?ip=2001:db8:1:315:aa:bbff:fe00:1'}
    ip = node_id = mac = None
    if 'ip' in roh:
        ip = ipv6(roh['ip'])
        if ip is None:
            return 400, {'error': 'ip ist keine IPv6-Adresse', 'query': roh}
    if 'node_id' in roh:
        node_id = hex12(roh['node_id'])
        if node_id is None:
            return 400, {'error': 'node_id: 12 Hex-Zeichen', 'query': roh}
    if 'mac' in roh:
        mac = hex12(roh['mac'])
        if mac is None:
            return 400, {'error': 'mac: sechs Bytes in Hex', 'query': roh}
    index = bestand.holen(community)
    if index is None:
        return 404, {'error': 'fuer diese Karte gibt es kein Adressbuch', 'query': roh}
    t = suchen(index, ip, node_id, mac)
    aus = {'query': roh, 'generated': index['generated'],
           'nodes': [eintrag(nid, index['nodes'][nid], wie) for nid, wie in t]}
    if not t:
        aus['error'] = 'kein Knoten gefunden'
        return 404, aus
    return 200, aus


class Handler(BaseHTTPRequestHandler):
    bestand = None
    server_version = 'knotensuche'
    sys_version = ''

    def log_message(self, *a):
        pass  # nginx protokolliert schon

    def senden(self, status, obj, kopf=True):
        daten = (json.dumps(obj, ensure_ascii=False, indent=1) + '\n').encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(daten)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        if kopf:
            self.wfile.write(daten)

    def bearbeiten(self, kopf=True):
        teile = urllib.parse.urlsplit(self.path)
        if teile.path != PFAD or len(self.path) > 512:
            return self.senden(404, {'error': 'nicht gefunden'}, kopf)
        try:
            status, obj = antwort(self.bestand, self.headers.get('X-Karte-Community', ''), teile.query)
        except Exception as e:  # kaputte Datei o.ae.: melden statt haengen
            print('Fehler: %r' % e, file=sys.stderr)
            status, obj = 503, {'error': 'Adressbuch gerade nicht lesbar'}
        self.senden(status, obj, kopf)

    def do_GET(self):
        self.bearbeiten()

    def do_HEAD(self):
        self.bearbeiten(kopf=False)


def main():
    port = 8782
    a = sys.argv[1:]
    if a[:1] == ['--port']:
        port = int(a[1])
    Handler.bestand = Bestand()
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == '__main__':
    main()
