#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Zaehlt die Clients je Domain aus der Uebersetzungstabelle von batman.

  clients-zaehlen.py [community]        # Vorgabe neander
  clients-zaehlen.py neander --zeigen   # nur ausgeben, nichts schreiben

Die Clientzahl, die respondd liefert, ist die Summe ueber die Knoten, die
gerade geantwortet haben. Wer hinter einem stummen Knoten haengt, fehlt darin.
Die globale Uebersetzungstabelle kennt dagegen jede Client-MAC der Domain,
denn genau die verteilt batman an alle Mitglieder des Mesh, und wir sind eines
(23.09.2026: 48 Abfragen kosten zusammen 0,13 Sekunden).

Abgegrenzt wird gegen die Knoten selbst: jede MAC, die in nodes.json als
primaere oder als Mesh-Schnittstelle eines Knotens steht, ist kein Client.
Dasselbe Verfahren wie in werkzeug/unifi-offloader.py.

Geschrieben wird in die Zeitreihen, im Influx-Zeilenformat:

  tt,domain=01_vel,sndomain=ffnefd01 clients=123,eintraege=769,knoten=44

Daraus werden tt_clients, tt_eintraege, tt_knoten, tt_originatoren,
tt_im_mesh und tt_dunkel.

Dunkle Knoten sind der zweite Grund fuer dieses Skript: batman-Knoten, die im
Mesh mitreden, deren respondd aber nicht antwortet. Sie stehen auf keiner
Karte, und ohne diesen Vergleich merkt sie niemand.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en/sites'
ZIEL = 'http://127.0.0.1:8428/write'
BESTAND = '/var/lib/karte/adressbuch'
API = '/var/www/karte-en/api'

FELDER = ('community', 'code', 'ordner', 'port', 'id', 'host', 'mtu', 'broker',
          'prefix6', 'prefix4', 'name')


def domains(community):
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, len(FELDER) - 1)
            if len(t) == len(FELDER) and t[0] == community:
                yield dict(zip(FELDER, t))


def knoten_macs(community):
    """Alle MACs, die zu Knoten gehoeren, also keine Clients sind."""
    pfad = f'{WEB}/{community}/alle/data/nodes.json'
    macs = set()
    try:
        daten = json.load(open(pfad, encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'{pfad}: {e}', file=sys.stderr)
        return macs
    for n in daten.get('nodes') or []:
        netz = ((n.get('nodeinfo') or {}).get('network') or {})
        if netz.get('mac'):
            macs.add(netz['mac'].lower())
        for iface in (netz.get('mesh') or {}).values():
            for liste in (iface.get('interfaces') or {}).values():
                for mac in liste or []:
                    macs.add(mac.lower())
    return macs


def mesh_macs(community):
    """Mesh-MAC -> node_id, fuer alle Knoten, die die Karte kennt."""
    pfad = f'{WEB}/{community}/alle/data/nodes.json'
    zu = {}
    try:
        daten = json.load(open(pfad, encoding='utf-8'))
    except (OSError, ValueError):
        return zu
    for n in daten.get('nodes') or []:
        ni = n.get('nodeinfo') or {}
        netz = ni.get('network') or {}
        nid = ni.get('node_id')
        for iface in (netz.get('mesh') or {}).values():
            for liste in (iface.get('interfaces') or {}).values():
                for mac in liste or []:
                    zu[mac.lower()] = nid
        if netz.get('mac'):
            zu.setdefault(netz['mac'].lower(), nid)
    return zu


def mesh(iface, zu, dunkle=None, ankuendiger=None, domain=''):
    """(Originatoren, verschiedene Knoten, dunkle Knoten) einer Domain.

    Ein Knoten taucht mit jeder seiner Mesh-Schnittstellen als Originator auf,
    im Schnitt also etwa doppelt. Wer Originatoren mit Knoten vergleicht,
    erfindet dunkle Knoten (23.09.2026: 1763 Originatoren sind 1070 Knoten).

    Dunkel heisst hier: im Mesh sichtbar, aber keiner Mesh-MAC eines Knotens
    zuzuordnen, den die Karte kennt. Faktisch ein batman-Knoten, dessen
    respondd nicht antwortet.
    """
    try:
        aus = subprocess.run(['batctl', 'meshif', iface, 'originators'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0, 0, 0
    orig, naechster = set(), {}
    for z in aus.splitlines()[2:]:
        f = z.split()
        if f and f[0] == '*':
            f = f[1:]
        if f and len(f[0]) == 17:
            orig.add(f[0].lower())
            weiter = [x.lower() for x in f[1:] if len(x) == 17]
            if weiter:
                naechster[f[0].lower()] = weiter[0]
    knoten = {zu[m] for m in orig if m in zu}
    fremd = [m for m in orig if m not in zu]
    if dunkle is not None:
        for m in fremd:
            e = dunkle.setdefault(m, {'domains': [], 'ankuendigungen': 0,
                                      'respondd_gruppe': False, 'ueber': []})
            e['domains'].append(domain)
            angesagt = (ankuendiger or {}).get(m, [])
            e['ankuendigungen'] += len(angesagt)
            if RESPONDD_GRUPPE in angesagt:
                e['respondd_gruppe'] = True
            if naechster.get(m) and naechster[m] not in e['ueber']:
                e['ueber'].append(naechster[m])
    return len(orig), len(knoten), len(fremd)


# Die Multicast-Gruppe, auf der respondd lauscht (ff05::2:1001). Wer sie
# ankuendigt, hat eine Firmware mit respondd; antwortet er trotzdem nicht, ist
# das ein kaputter Knoten und kein handgebautes Geraet.
RESPONDD_GRUPPE = '33:33:00:02:10:01'


def tabelle(iface, ankuendiger=None):
    """MACs aus der globalen Uebersetzungstabelle einer bat-Instanz.

    Mit ankuendiger (dict) wird zusaetzlich festgehalten, welcher Originator
    welche MAC ankuendigt. Das trennt echte Teilnehmer von Phantomen: ein
    Phantom aus reflektierten OGMs kuendigt nichts an.
    """
    try:
        aus = subprocess.run(['batctl', 'meshif', iface, 'transglobal'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    macs = set()
    for z in aus.splitlines()[2:]:
        f = z.split()
        if f and f[0] == '*':
            f = f[1:]
        if not f or len(f[0]) != 17:
            continue
        mac = f[0].lower()
        if ankuendiger is not None:
            via = [x.lower() for x in f[1:] if len(x) == 17]
            if via:
                ankuendiger.setdefault(via[0], []).append(mac)
        # Multicast und Broadcast sind keine Stationen
        if mac.startswith(('01:00:5e', '33:33', 'ff:ff')) or int(mac[1], 16) & 1:
            continue
        macs.add(mac)
    return macs


def schreiben(zeilen, community):
    daten = '\n'.join(zeilen).encode('utf-8')
    req = urllib.request.Request(f'{ZIEL}?db={community}', data=daten,
                                 method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def main():
    ruf = [a for a in sys.argv[1:] if not a.startswith('-')]
    community = ruf[0] if ruf else 'neander'
    zeigen = '--zeigen' in sys.argv

    knoten = knoten_macs(community)
    zuordnung = mesh_macs(community)
    dunkle = {}
    zeilen = []
    for d in domains(community):
        iface = f'bat-{d["code"]}'
        ankuendiger = {}
        eintraege = tabelle(iface, ankuendiger)
        if not eintraege:
            continue
        clients = eintraege - knoten
        # Die Domainnummer steckt vorn im Code (05_mon) und ist zugleich die
        # Nummer, unter der die Supernodes ihre Instanz melden (ffnefd05).
        nummer = d['code'].split('_')[0]
        orig, im_mesh, dunkel = mesh(iface, zuordnung, dunkle, ankuendiger,
                                     d['code'])
        zeilen.append(f'tt,domain={d["code"]},sndomain=ffnefd{nummer} '
                      f'clients={len(clients)}i,eintraege={len(eintraege)}i,'
                      f'knoten={len(eintraege) - len(clients)}i,'
                      f'originatoren={orig}i,im_mesh={im_mesh}i,dunkel={dunkel}i')
        if zeigen:
            print(f'{d["code"]:12} {len(clients):5} Clients, '
                  f'{len(eintraege):5} Eintraege, '
                  f'{orig:4} Originatoren, {im_mesh:4} Knoten, '
                  f'{dunkel:3} dunkel')

    if not zeilen:
        print('keine Tabelle lesbar, laeuft das als root?', file=sys.stderr)
        return 1
    if zeigen:
        for mac, e in sorted(dunkle.items()):
            print(f'dunkel {mac}  {len(e["domains"]):2} Domains, '
                  f'{e["ankuendigungen"]:3} Ankuendigungen, '
                  f'respondd-Gruppe {"ja" if e["respondd_gruppe"] else "nein"}')
        return 0
    schreiben(zeilen, community)
    dunkelliste(dunkle, community)
    return 0


def dunkelliste(dunkle, community):
    """Die dunklen Knoten mit Merkmalen festhalten, nicht nur zaehlen.

    Was sie sind, entscheidet der Blick auf die Merkmale (adorfer 23.09.2026):
    ein gestorbenes respondd, ein handgebautes Geraet, ein absichtlich stummer
    Knoten oder ein Phantom aus reflektierten OGMs. Die Zahl allein sagt das
    nicht, die Liste hilft beim Nachsehen.
    """
    jetzt = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    bestand_pfad = f'{BESTAND}/dunkel-{community}.json'
    try:
        bestand = json.load(open(bestand_pfad, encoding='utf-8'))
    except (OSError, ValueError):
        bestand = {}
    for mac, e in dunkle.items():
        alt = bestand.get(mac, {})
        bestand[mac] = {
            'domains': sorted(e['domains']),
            'ankuendigungen': e['ankuendigungen'],
            'respondd_gruppe': e['respondd_gruppe'],
            'ueber': sorted(e['ueber']),
            'erste_sichtung': alt.get('erste_sichtung', jetzt),
            'letzte_sichtung': jetzt,
        }
    os.makedirs(BESTAND, exist_ok=True)
    for pfad in (bestand_pfad, f'{API}/{community}/dunkel.json'):
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        neu = pfad + '.neu'
        with open(neu, 'w', encoding='utf-8') as f:
            json.dump({'generated': jetzt, 'community': community,
                       'knoten': bestand} if pfad.endswith('dunkel.json')
                      else bestand, f, ensure_ascii=False, sort_keys=True)
        os.chmod(neu, 0o644)
        os.replace(neu, pfad)


if __name__ == '__main__':
    sys.exit(main())
