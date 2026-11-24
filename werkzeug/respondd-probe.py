#!/usr/bin/env python3
"""Respondd-Probe: fragt eine batman-Instanz per Rundruf ab und zaehlt, wer antwortet.

  respondd-probe.py [-g GRUPPE ...] bat-<code> [...]

Ohne -g gehen alle drei ueblichen Gruppen gleichzeitig hinaus, je ein eigener
Socket, die Antworten werden getrennt gezaehlt:

  ff05::2:1001   Stock-Gluon auf br-client (Neanderfunk 24.11.2026: 875 von
                 1076, 2025.1 antwortet, die Sackgasse 2021.1 nicht)
  ff02::2:1001   Stock-Gluon auf den Mesh-Schnittstellen; ueber batman nur
                 mit dem Patch fix-respondd-rsk
  ff02::1        Patch fix-respondd-rsk (entfaellt, alte Knoten haben ihn
                 weiter); yanic fragt dauerhaft ff05 und ff02::1

Antworten kommen per Unicast zurueck. Gewartet wird 12 Sekunden: Gluon
startet respondd auf br-client mit -t 10 (MAXDELAY), Antworten auf einen
Rundruf kommen also bis zu 10 Sekunden verzoegert (auf einem Testknoten
am 23.11.2026 gesehen: 2 und 4 Sekunden).
"""
import argparse
import json
import select
import socket
import struct
import time
import zlib

GRUPPEN = ('ff05::2:1001', 'ff02::2:1001', 'ff02::1')
PORT = 1001
WARTE = 12.0


def frage(iface, gruppen, anfrage=b'GET nodeinfo'):
    idx = socket.if_nametoindex(iface)
    socks = {}
    for g in gruppen:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, struct.pack('I', idx))
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 64)
        s.bind(('::', 0))
        s.sendto(anfrage, (g, PORT, 0, idx))
        socks[s] = g
    antworten = {g: {} for g in gruppen}
    ende = time.time() + WARTE
    while time.time() < ende:
        bereit, _, _ = select.select(list(socks), [], [], max(0.0, ende - time.time()))
        for s in bereit:
            daten, von = s.recvfrom(65536)
            try:
                j = json.loads(daten)
            except ValueError:
                try:
                    j = json.loads(zlib.decompress(daten, -15))
                except Exception:
                    j = None
            if isinstance(j, dict):
                j = j.get('nodeinfo', j)
            antworten[socks[s]][von[0]] = j
    for s in socks:
        s.close()
    return antworten


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('-g', '--gruppe', action='append',
                    help='Abfragegruppe, mehrfach moeglich (Vorgabe: alle drei)')
    ap.add_argument('iface', nargs='+')
    a = ap.parse_args()
    for iface in a.iface:
        for g, an in frage(iface, a.gruppe or GRUPPEN).items():
            namen = sorted(v.get('hostname', '?') for v in an.values() if isinstance(v, dict))
            print(f'{iface:12} {g:13} {len(an):4} Antworten   z.B. {", ".join(namen[:3])}')


if __name__ == '__main__':
    main()
