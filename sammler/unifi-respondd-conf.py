#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt die Konfiguration fuer unifi_respondd (Fork Neanderfunk/unifi_respondd).

  unifi-respondd-conf.py > /etc/unifi_respondd/unifi_respondd.yaml

unifi_respondd holt die Accesspoints aus dem UniFi-Controller und meldet sie
yanic als Knoten. Er lauscht auf allen batman-Instanzen unserer Community und
beantwortet jede Anfrage nur mit den APs, deren Router in genau dieser Domain
steht. So sieht jeder Sammler in jedem Mesh, was dorthin gehoert, wie bei
einem echten Knoten, auch fremde Sammler wie die alte Karte.

Die Zuordnung Schnittstelle -> site_codes kommt aus sitecodes.conf, nur fuer
batman-Instanzen, die gerade existieren (wie bei yanic).

Den Router je AP liest unifi_respondd aus der Datei, die
karte-unifi-offloader aus der batman-Uebersetzungstabelle erzeugt
(karte-unifi-zuordnung.timer). APs ohne gemessenen Router meldet er nicht:
offloader_mac bleibt leer, also faellt so ein AP in keine Domain. Ein
falscher Router waere schlimmer als ein fehlender AP.

Zugangsdaten stehen in /etc/unifi_respondd/zugang (0600 root), drei Zeilen:
Benutzer, Passwort, Controller-URL. Das Ergebnis dieses Skripts enthaelt sie
ebenfalls und gehoert deshalb nach 0640 root:unifi-respondd.
"""
import json
import os
import sys
from urllib.parse import urlparse

SITE_KONF = '/etc/karte-en/sitecodes.conf'
ZUGANG = '/etc/unifi_respondd/zugang'
ZUORDNUNG = '/var/lib/karte/unifi-zuordnung.json'
KARTE = 'https://neander.map.freifunk.space/data/meshviewer.json'


def sitecodes(pfad=SITE_KONF):
    ergebnis = {}
    with open(pfad) as f:
        for zeile in f:
            teile = zeile.split('#')[0].split()
            if len(teile) != 2:
                continue
            code, codes = teile
            liste = [c for c in codes.split(',') if c]
            if code not in liste:
                liste.append(code)
            ergebnis[code] = liste
    return ergebnis


def schnittstellen(codes, vorhanden):
    return {'bat-' + code: liste for code, liste in sorted(codes.items())
            if 'bat-' + code in vorhanden}


def zugang(pfad=ZUGANG):
    with open(pfad) as f:
        benutzer, passwort, url = [z.strip() for z in f.read().splitlines()[:3]]
    teile = urlparse(url if '://' in url else 'https://' + url)
    return benutzer, passwort, teile.hostname, teile.port or 443


def konfiguration(benutzer, passwort, host, port, ifs):
    # JSON ist gueltiges YAML; so gibt es keine Anfuehrungszeichen-Fallen im
    # Passwort.
    return {
        'controller_url': host,
        'controller_port': port,
        'username': benutzer,
        'password': passwort,
        'version': 'v5',
        'ssl_verify': True,
        # Freifunk und FreifunkStreaming; beide landen im Freifunk-Netz
        # (am 25.09.2026 in der Uebersetzungstabelle nachgesehen).
        'ssid_regex': '.*freifunk.*',
        'offloader_mac': {},
        'offloader_by_ap': ZUORDNUNG,
        'nodelist': KARTE,
        'fallback_domain': 'unifi_respondd_fallback',
        'multicast_enabled': True,
        # yanic fragt auf jeder batman-Instanz an ff02::1
        'multicast_address': 'ff02::1',
        'multicast_port': 1001,
        'unicast_address': '::1',
        'unicast_port': 10001,
        'interface': 'lo',
        'interfaces': ifs,
        'cache_seconds': 60,
        'verbose': False,
        'logging_config': {
            'version': 1,
            'handlers': {'console': {'class': 'logging.StreamHandler',
                                     'formatter': 'standard'}},
            'formatters': {'standard': {'format': '%(levelname)s %(message)s'}},
            # Auf INFO schreibt unifi_respondd jede einzelne Antwort ins Log
            'root': {'level': 'WARNING', 'handlers': ['console']},
        },
    }


def main():
    ifs = schnittstellen(sitecodes(), set(os.listdir('/sys/class/net')))
    if not ifs:
        sys.exit('keine batman-Instanz aus sitecodes.conf vorhanden')
    json.dump(konfiguration(*zugang(), ifs), sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == '__main__':
    main()
