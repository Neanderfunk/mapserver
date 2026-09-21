#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Findet heraus, hinter welchem Freifunk-Knoten ein Unifi-Accesspoint haengt.

  unifi-offloader.py neander                     # nur messen und auflisten
  unifi-offloader.py neander --sites sites.csv   # fertigen Konfigurationsblock

Fuer unifi_respondd (github.com/freifunkMUC/unifi_respondd) muss je Unifi-Site
die MAC des Offloaders in der Konfiguration stehen. Von Hand heisst das: fuer
jede Site herausfinden, hinter welchem Freifunk-Knoten ihre Accesspoints
haengen. Das muss niemand suchen, es steht in den Tabellen von batman.

Ein AP hinter einem Freifunk-Knoten ist aus Sicht von batman ein Client dieses
Knotens. Die globale Uebersetzungstabelle nennt zu jeder Client-MAC den
Originator, der sie ankuendigt, und ueber die Mesh-Schnittstellen aus den
respondd-Daten kommt man von dort auf den Knoten, wie er auf der Karte steht.

Mit --sites (CSV: MAC,Sitename) entsteht daraus der fertige offloader_mac-Block
und, wichtiger, die Liste der Sites, deren Accesspoints hinter Knoten in
verschiedenen Domains haengen. Genau die muessen aufgeteilt werden, denn
unifi_respondd kennt je Site nur einen Offloader und damit nur eine Domain.
"""
import argparse
import collections
import csv
import json
import os
import subprocess
import sys

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en/sites'

# Herstellerpraefixe von Ubiquiti. Die Liste ist nicht vollstaendig und darf
# wachsen; unbekannte Praefixe tauchen mit --alle auf.
UBIQUITI = (
    '24:5a:4c', '78:8a:20', '68:d7:9a', 'e0:63:da', 'f4:92:bf', '74:83:c2',
    '44:d9:e7', 'fc:ec:da', '80:2a:a8', 'b4:fb:e4', '18:e8:29', '70:a7:41',
    'd0:21:f9', 'dc:9f:db', '04:18:d6', '9c:05:d6', '28:70:4e', 'ac:8b:a9',
    '78:45:58', 'f0:9f:c2', '44:d9:e7', '60:22:32', 'e4:38:83',
)


def domains(community):
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, 10)
            if len(t) == 11 and t[0] == community:
                yield t[1], t[5], t[10]


def knoten_nach_mac(community):
    """Jede Mesh-MAC eines Knotens auf (node_id, hostname, primaere MAC)."""
    pfad = f'{WEB}/{community}/alle/data/nodes.json'
    try:
        daten = json.load(open(pfad, encoding='utf-8'))
    except (OSError, ValueError):
        print(f'{pfad} nicht lesbar, Aufloesung faellt aus', file=sys.stderr)
        return {}
    karte = {}
    for n in daten.get('nodes') or []:
        ni = n.get('nodeinfo') or {}
        netz = ni.get('network') or {}
        eintrag = (ni.get('node_id'), ni.get('hostname'), netz.get('mac'))
        for wert in (netz.get('mac'),):
            if wert:
                karte[wert.lower()] = eintrag
        for iface in (netz.get('mesh') or {}).values():
            for liste in (iface.get('interfaces') or {}).values():
                for mac in liste or []:
                    karte[mac.lower()] = eintrag
    return karte


def clients(iface, alle):
    """Client-MACs der Domain mit dem Originator, der sie ankuendigt."""
    try:
        aus = subprocess.run(['batctl', 'meshif', iface, 'transglobal'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gefunden = []
    for z in aus.splitlines()[2:]:
        f = z.split()
        if f and f[0] == '*':
            f = f[1:]
        if len(f) < 6 or len(f[0]) != 17:
            continue
        mac = f[0].lower()
        if mac.startswith(('01:00:5e', '33:33', 'ff:ff')):
            continue
        if not alle and mac[:8] not in UBIQUITI:
            continue
        via = [x.lower() for x in f[1:] if len(x) == 17]
        gefunden.append((mac, via[0] if via else None))
    return gefunden


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('community')
    p.add_argument('--sites', help='CSV mit MAC,Sitename aus dem Controller')
    p.add_argument('--alle', action='store_true',
                   help='alle Clients, nicht nur Ubiquiti-Praefixe')
    a = p.parse_args()

    aufloesung = knoten_nach_mac(a.community)
    # AP-MAC -> (Domain, Offloader-Hostname, Offloader-MAC)
    zuordnung = {}
    je_domain = collections.Counter()
    for code, host, name in domains(a.community):
        for mac, via in clients(f'bat-{code}', a.alle):
            # Unsere eigenen Knoten laufen zum Teil auf Ubiquiti-Hardware und
            # kuendigen ihre MAC selbst als Client an. Wer als Knoten bekannt
            # ist, ist kein Accesspoint dahinter (gemessen 21.09.2026: sonst
            # sind neun von zehn Treffern Gluon-Knoten).
            if mac in aufloesung:
                continue
            knoten = aufloesung.get(via or '', (None, None, None))
            zuordnung[mac] = (host, knoten[1], knoten[2] or via)
            je_domain[host] += 1

    if not a.sites:
        print(f'# {len(zuordnung)} Geraete in {len(je_domain)} Domains')
        print(f'# {"AP-MAC":19}{"Domain":24}{"Offloader":28}Offloader-MAC')
        for mac, (host, name, omac) in sorted(zuordnung.items(),
                                              key=lambda x: (x[1][0] or '', x[0])):
            print(f'{mac:19}{host or "?":24}{name or "?":28}{omac or "?"}')
        return 0

    # Mit Sitenliste: Konfigurationsblock und Warnliste
    sites = collections.defaultdict(list)
    with open(a.sites, encoding='utf-8') as f:
        for zeile in csv.reader(f):
            if len(zeile) >= 2 and ':' in zeile[0]:
                sites[zeile[1].strip()].append(zeile[0].strip().lower())

    eindeutig, gemischt = {}, {}
    for site, macs in sites.items():
        treffer = [zuordnung[m] for m in macs if m in zuordnung]
        if not treffer:
            continue
        domains_der_site = {t[0] for t in treffer}
        offloader = collections.Counter(t[2] for t in treffer)
        if len(domains_der_site) == 1 and len(offloader) == 1:
            eindeutig[site] = (offloader.most_common(1)[0][0], treffer[0][1])
        else:
            gemischt[site] = (domains_der_site, offloader, len(macs), len(treffer))

    print('# Erzeugt von unifi-offloader.py, gemessen aus den batman-Tabellen.')
    print('# Vor dem Uebernehmen durchsehen: die Zuordnung stimmt nur fuer')
    print('# Geraete, die gerade online sind.')
    print('offloader_mac:')
    for site, (mac, name) in sorted(eindeutig.items()):
        print(f'    {site}: {mac}   # {name}')

    if gemischt:
        print()
        print('# ACHTUNG, diese Sites streuen ueber mehrere Domains oder Knoten.')
        print('# unifi_respondd kennt je Site nur einen Offloader, sie muessen')
        print('# also aufgeteilt werden, eine Site je Domain:')
        for site, (doms, offl, ges, erkannt) in sorted(gemischt.items()):
            print(f'#   {site}: {erkannt} von {ges} Geraeten erkannt, '
                  f'Domains {sorted(doms)}, {len(offl)} Offloader')
    print(f'\n# {len(eindeutig)} Sites eindeutig, {len(gemischt)} aufzuteilen',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
