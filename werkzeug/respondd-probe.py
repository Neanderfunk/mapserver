#!/usr/bin/env python3
"""Respondd-Probe: fragt eine batman-Instanz per Multicast ab und zaehlt, wer antwortet.

Das ist genau die Abfrage, die yanic spaeter macht: ff05::2:1001 ist
site-local und wird von Stock-Gluon auf br-client bedient, also ueber bat0
im ganzen Mesh verteilt. Antworten kommen per Unicast zurueck.
"""
import json, socket, struct, sys, time, zlib

GRUPPE = 'ff05::2:1001'
PORT = 1001
WARTE = 6.0


def frage(iface, anfrage=b'nodeinfo'):
    idx = socket.if_nametoindex(iface)
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, struct.pack('I', idx))
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 64)
    s.bind(('::', 0))
    s.sendto(anfrage, (GRUPPE, PORT, 0, idx))
    s.settimeout(0.5)
    antworten = {}
    ende = time.time() + WARTE
    while time.time() < ende:
        try:
            daten, von = s.recvfrom(65536)
        except socket.timeout:
            continue
        try:
            j = json.loads(daten)
        except ValueError:
            try:
                j = json.loads(zlib.decompress(daten, -15))
            except Exception:
                j = None
        antworten[von[0]] = j
    s.close()
    return antworten


for iface in sys.argv[1:]:
    a = frage(iface)
    namen = sorted(v.get('hostname', '?') for v in a.values() if isinstance(v, dict))
    print(f'{iface:12} {len(a):4} Antworten   z.B. {", ".join(namen[:3])}')
