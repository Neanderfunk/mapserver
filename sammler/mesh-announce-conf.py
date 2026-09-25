#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt die Konfiguration fuer mesh-announce (ffnord/mesh-announce).

  mesh-announce-conf.py > /etc/mesh-announce/respondd.conf

Der Kartenserver haengt mit einem Tunnel in jedem Mesh, das er misst, und
steht dort als batman-Originator. Ohne respondd-Antwort ist er fuer jede
andere Karte ein "dunkler Knoten" (adorfer 26.09.2026). mesh-announce, das
auch auf den Supernodes laeuft, antwortet je batman-Instanz als eigener
Knoten: mit Namen, Kontakt, Tunnel und batman-Nachbarn.

Eine Sektion je Domain aus domains.conf, deren batman-Instanz gerade
existiert und deren Community nicht ruht (standby.conf). mesh-announce tritt
den Multicast-Gruppen nur beim Start bei; deshalb erzeugt der Dienst die
Datei bei jedem Start neu, und der Watchdog startet ihn neu, wenn eine
batman-Instanz ohne Gruppe dasteht.
"""
import os
import sys

DOMAINS = '/etc/karte-en/domains.conf'
STANDBY = '/etc/karte-en/standby.conf'
NET = '/sys/class/net'

KOPF = '''# Erzeugt von mesh-announce-conf.py. Nicht von Hand aendern.
[Defaults]
Port: 1001
MulticastLinkAddress: ff02::2:1001
MulticastSiteAddress: ff05::2:1001
DomainType: batadv
VPNProtocols: None
VPN: False
Hardware-Model: Kartenserver (VM)
Contact: projekt@neanderfunk.de
'''


def zeilen(pfad):
    try:
        with open(pfad, encoding='utf-8') as f:
            for z in f:
                z = z.strip()
                if z and not z.startswith('#'):
                    yield z.split()
    except OSError:
        return


def main():
    ruhend = {t[0] for t in zeilen(STANDBY)}
    vorhanden = set(os.listdir(NET))
    teile = [KOPF]
    for t in zeilen(DOMAINS):
        if len(t) < 2:
            continue
        community, code = t[0], t[1]
        bat = 'bat-' + code
        if community in ruhend or bat not in vorhanden:
            continue
        teile.append(f'[{code}]\nDomainCode: {code}\nBatmanInterface: {bat}\n'
                     f'Hostname: map-neanderfunk-{code}\n')
    if len(teile) == 1:
        sys.exit('keine aktive batman-Instanz aus domains.conf')
    print('\n'.join(teile))


if __name__ == '__main__':
    main()
