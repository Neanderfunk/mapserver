#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Sucht Knoten, die auf keinen Rundruf antworten, und legt sie yanic hin.

  ziele-ernten.py en > /etc/karte-en/ziele-en.txt

Bei Freifunk EN erreicht unser Multicast die Knoten in den meisten Domains
nicht, waehrend Unicast in beide Richtungen einwandfrei laeuft (vermutlich
ueberlaufende Tabellen in ihrer Virtualisierung, siehe docs/hintergrund.md).
Der Weg daran vorbei fuehrt ueber die Uebersetzungstabelle von batman: jeder
Gluon-Knoten meldet seine eigene bat0-MAC als Client ins Mesh, und deren
EUI-64 ist genau die Link-Local-Adresse, auf der respondd lauscht.

Hier wird einmal je Lauf durchprobiert und nur aufgeschrieben, wer wirklich
geantwortet hat. yanic fragt die Liste danach in jeder Runde mit, ueber den
mit patches/yanic-seeds.patch ergaenzten Weg. Die Knoten antworten dann an
yanics eigenen Socket, und ab da sind sie fuer yanic gewoehnliche Knoten.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
import zlib

KONF = '/etc/karte-en/domains.conf'
PAKETE = 40          # wie viele Anfragen gleichzeitig unterwegs sind
WARTEN = 4.0         # Sekunden je Schwung auf Antworten warten


def domains(community):
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, 10)
            if len(t) == 11 and t[0] == community:
                yield t[1], t[10]


def eui64(mac):
    """MAC zu Link-Local: Bit 1 des ersten Bytes kippen, ff:fe einschieben."""
    t = [int(x, 16) for x in mac.split(':')]
    t[0] ^= 0x02
    b = t[:3] + [0xff, 0xfe] + t[3:]
    g = [f'{b[i]:02x}{b[i + 1]:02x}' for i in range(0, 8, 2)]
    return 'fe80::' + ':'.join(x.lstrip('0') or '0' for x in g)


def kandidaten(iface):
    try:
        aus = subprocess.run(['batctl', 'meshif', iface, 'transglobal'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    macs = []
    for z in aus.splitlines()[2:]:
        t = z.split()
        if t and t[0] == '*':
            t = t[1:]
        if not t or len(t[0]) != 17:
            continue
        # Multicast- und Broadcast-Adressen sind keine Knoten
        if t[0].startswith(('01:00:5e', '33:33', 'ff:ff')):
            continue
        macs.append(t[0])
    return [eui64(m) for m in dict.fromkeys(macs)]


def fragen(iface, adressen):
    """Schwungweise fragen, zurueck kommen nur die, die geantwortet haben."""
    idx = socket.if_nametoindex(iface)
    gefunden = {}
    for anfang in range(0, len(adressen), PAKETE):
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        for a in adressen[anfang:anfang + PAKETE]:
            try:
                s.sendto(b'nodeinfo', (a, 1001, 0, idx))
            except OSError:
                pass
        ende = time.time() + WARTEN
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
                    continue
            gefunden[von[0]] = (j.get('hostname') or '?',
                                (j.get('system') or {}).get('site_code') or '')
        s.close()
    return gefunden


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('community')
    p.add_argument('--nur', help='nur diese Domain (Code)')
    a = p.parse_args()

    print(f'# Adressen, die per Unicast antworten, erhoben am '
          f'{time.strftime("%Y-%m-%d %H:%M")}.')
    print('# Erzeugt von ziele-ernten.py, wird von yanic in jeder Runde mitgefragt.')
    gesamt = 0
    for code, name in domains(a.community):
        if a.nur and code != a.nur:
            continue
        iface = f'bat-{code}'
        k = kandidaten(iface)
        g = fragen(iface, k)
        gesamt += len(g)
        print(f'#')
        print(f'# {name}: {len(k)} Kandidaten, {len(g)} antworten')
        for adresse, (name_k, site) in sorted(g.items()):
            print(f'{adresse}%{iface}   # {name_k} {site}')
        print(f'  {iface:14} {len(k):4} Kandidaten, {len(g):4} Antworten',
              file=sys.stderr)
    print(f'# insgesamt {gesamt} Adressen')
    print(f'insgesamt {gesamt} Adressen', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
