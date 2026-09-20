#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Klopft an Tunneldigger-Broker an, ohne einen Tunnel aufzubauen.

  ./broker-probe.py                       # liest /etc/karte-en/domains.conf
  ./broker-probe.py ../tunnel/domains.conf
  ./broker-probe.py --broker b1.example:10000

Der Kontrollrahmen ist 80 73 A7 01 <typ> <laenge> <nutzlast>, auf zwoelf Byte
aufgefuellt. COOKIE (0x01) ist zustandslos: der Broker antwortet mit einem
Cookie und legt nichts an. Das ist die hoeflichste Art zu pruefen, ob dort
ueberhaupt ein Broker laeuft, und der erste Test bei einer neuen Gemeinschaft.
"""
import argparse
import socket
import sys
import time

MAGIC = b'\x80\x73\xa7\x01'
COOKIE = 0x01


def rahmen(typ, nutzlast=b''):
    p = MAGIC + bytes([typ, len(nutzlast)]) + nutzlast
    return p + b'\0' * max(0, 12 - len(p))


def frage(host, port, versuche=3, wartezeit=2.0):
    try:
        ziele = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
    except socket.gaierror as e:
        return None, str(e), '?'
    for fam, typ, proto, _, sa in ziele:
        s = socket.socket(fam, typ, proto)
        s.settimeout(wartezeit)
        try:
            for _ in range(versuche):
                t0 = time.time()
                s.sendto(rahmen(COOKIE, b'XXXXXXXX'), sa)
                try:
                    daten, _ = s.recvfrom(2048)
                except socket.timeout:
                    continue
                if daten[:4] != MAGIC:
                    return None, 'fremde Antwort', sa[0]
                return (time.time() - t0) * 1000, None, sa[0]
            return None, 'keine Antwort', sa[0]
        finally:
            s.close()
    return None, 'keine Adresse', '?'


def tabelle(pfad):
    for z in open(pfad, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, 7)
            if len(t) >= 8:
                yield t[0], int(t[2])


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('tabelle', nargs='?', default='/etc/karte-en/domains.conf')
    p.add_argument('--broker', action='append', default=[],
                   help='host:port statt der Tabelle')
    p.add_argument('--hosts', default='broker1.ff-en.de,broker2.ff-en.de',
                   help='Brokernamen zur Tabelle, durch Komma getrennt')
    a = p.parse_args()

    if a.broker:
        paare = []
        for b in a.broker:
            h, _, po = b.rpartition(':')
            paare.append(('-', h, int(po)))
    else:
        paare = [(code, h, port) for code, port in tabelle(a.tabelle)
                 for h in a.hosts.split(',')]

    schlecht = 0
    for code, host, port in paare:
        ms, fehler, ip = frage(host, port)
        if fehler:
            schlecht += 1
            print(f'{code:8} {host:22} {port:6}  {fehler:>14}  ({ip})')
        else:
            print(f'{code:8} {host:22} {port:6}  {ms:11.0f} ms  ({ip})')
    return 1 if schlecht == len(paare) else 0


if __name__ == '__main__':
    sys.exit(main())
