#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Schreibt je Domain eine Zeile in eine CSV, damit man sehen kann, was ein
fremdes Netz ueber Stunden tut.

Bei Freifunk EN fallen seit dem 20.09.2026 einzelne Domains aus und kommen
wieder, ohne erkennbares Muster: mal antwortet nur eine, mal sieben von acht,
und welche es ist, wechselt. Solange wir nur gelegentlich hinsehen, bleibt es
ein Eindruck. Mit einer Zeitreihe wird daraus eine Beobachtung.

Aufgerufen aus karte-verlauf.timer, alle fuenf Minuten. Eine Zeile je Domain
und Lauf, das sind bei 56 Domains rund 16000 Zeilen am Tag und damit etwa
ein Megabyte. Aeltere Zeilen werden nach ALTER Tagen entfernt.
"""
import csv
import datetime
import json
import os
import subprocess
import sys

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en/sites'
ZIEL = '/var/lib/karte/verlauf.csv'
ALTER = 30
SPALTEN = ('zeit', 'community', 'domain', 'host', 'originatoren', 'nachbarn',
           'gateways', 'knoten', 'online', 'juengste_sichtung_min')


def domains():
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if z and not z.startswith('#'):
            t = z.split(None, 10)
            if len(t) == 11:
                yield t[0], t[1], t[5]


def batctl(iface, was):
    try:
        aus = subprocess.run(['batctl', 'meshif', iface, was],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    zeilen = [z for z in aus.splitlines()[2:] if z.strip()]
    if was == 'originators':
        return sum(1 for z in zeilen if z.startswith(' *'))
    return len(zeilen)


def aus_datei(pfad, jetzt):
    try:
        d = json.load(open(pfad, encoding='utf-8'))
    except (OSError, ValueError):
        return 0, 0, ''
    n = d.get('nodes') or []
    ls = [x.get('lastseen') for x in n if x.get('lastseen')]
    alt = ''
    if ls:
        try:
            alt = int((jetzt - datetime.datetime.fromisoformat(max(ls))).total_seconds() // 60)
        except ValueError:
            alt = ''
    return len(n), sum(1 for x in n if x.get('is_online')), alt


def aufraeumen(pfad):
    grenze = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=ALTER)).isoformat()
    try:
        with open(pfad, encoding='utf-8') as f:
            zeilen = f.readlines()
    except OSError:
        return
    if len(zeilen) < 2:
        return
    behalten = [zeilen[0]] + [z for z in zeilen[1:] if z.split(',', 1)[0] >= grenze]
    if len(behalten) != len(zeilen):
        with open(pfad, 'w', encoding='utf-8') as f:
            f.writelines(behalten)


def main():
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    neu = not os.path.exists(ZIEL)
    with open(ZIEL, 'a', encoding='utf-8', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(SPALTEN)
        for comm, code, host in domains():
            iface = f'bat-{code}'
            ges, on, alt = aus_datei(f'{WEB}/{comm}/{host}/data/meshviewer.json', jetzt)
            s.writerow([jetzt.isoformat(timespec='seconds'), comm, code, host,
                        batctl(iface, 'originators'), batctl(iface, 'neighbors'),
                        batctl(iface, 'gwl'), ges, on, alt])
    aufraeumen(ZIEL)
    return 0


if __name__ == '__main__':
    sys.exit(main())
