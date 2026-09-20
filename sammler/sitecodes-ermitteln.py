#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Ermittelt, welchen site_code die Knoten einer Domain tatsaechlich melden.

Der Name der Domain und der site_code ihrer Knoten sind nicht dasselbe. Im
Neanderfunk heisst eine Domain 30_sol, ihre Knoten melden aber dus-30_sol,
Geraete am Ende der Unterstuetzung dus-30_sol_EOL, und einzelne noch den
blanken Code. Die Praefixe unterscheiden sich je Domain (nef-, dus-, bgl-,
lvrno- ...), sie lassen sich also nicht erraten.

yanic filtert seine Ausgaben exakt nach site_code. Passt der Filter nicht,
bleibt die Karte leer, obwohl die Daten ankommen (20.09.2026: 28 von 48
Domains leer). Deshalb fragen wir die Knoten selbst und schreiben das
Ergebnis nach /etc/karte-en/sitecodes.conf, das der Konfigurationsgenerator
liest.

  sitecodes-ermitteln.py > /etc/karte-en/sitecodes.conf
"""
import collections
import json
import socket
import struct
import sys
import time
import zlib

KONF = '/etc/karte-en/domains.conf'
GRUPPEN = ('ff02::1', 'ff05::2:1001')
WARTEN = 6.0


def domains():
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, 10)
            if len(t) == 11:
                yield t[0], t[1], t[10]


def codes_von(iface):
    try:
        idx = socket.if_nametoindex(iface)
    except OSError:
        return collections.Counter()
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, struct.pack('I', idx))
    s.settimeout(0.4)
    for g in GRUPPEN:
        try:
            s.sendto(b'nodeinfo', (g, 1001, 0, idx))
        except OSError:
            pass
    gefunden = collections.Counter()
    ende = time.time() + WARTEN
    while time.time() < ende:
        try:
            daten, _ = s.recvfrom(65536)
        except socket.timeout:
            continue
        try:
            j = json.loads(daten)
        except ValueError:
            try:
                j = json.loads(zlib.decompress(daten, -15))
            except Exception:
                continue
        # Supernodes melden nur einen domain_code und keinen site_code; die
        # gehoeren erst dazu, wenn sie einen bekommen (siehe docs).
        sc = (j.get('system') or {}).get('site_code')
        if sc:
            gefunden[sc] += 1
    s.close()
    return gefunden


def main():
    print('# Erzeugt von sitecodes-ermitteln.py: was die Knoten je Domain als')
    print('# site_code melden. Nicht von Hand pflegen, sondern neu erheben.')
    print(f'# Stand {time.strftime("%Y-%m-%d %H:%M")}')
    print('#')
    print('# code       site_codes (Komma), haeufigster zuerst')
    leer = []
    for community, code, name in domains():
        c = codes_von(f'bat-{code}')
        if not c:
            leer.append((code, name))
            continue
        liste = ','.join(k for k, _ in c.most_common())
        print(f'{code:12} {liste}')
    if leer:
        print('#')
        print('# ohne Antwort, deshalb ohne Eintrag (der Generator nimmt dann den')
        print('# blanken Domaincode):')
        for code, name in leer:
            print(f'#   {code:12} {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
