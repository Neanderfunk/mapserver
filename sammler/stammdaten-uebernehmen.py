#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Uebernimmt die Neanderfunk-Domains aus den Stammdaten der Supernodes.

  stammdaten-uebernehmen.py                  # holen, schreiben, anwenden
  stammdaten-uebernehmen.py --trocken        # nur zeigen, was sich aendert
  stammdaten-uebernehmen.py --offline --ohne-anwenden   # aus dem Zwischenstand

Die Stammdaten (git.ideenwerk.me/neanderfunk/supernode/stammdaten,
erzeugt/stammdaten.json) sind die eine Quelle fuer Supernodes, Brokerlisten,
Ports, MTU, ULA, Namen und site_codes der Neanderfunk-Domains (adorfer
29.10.2026, E2: automatisch uebernehmen, nicht nur melden).

Geschrieben wird in zwei Dateien:

- domains.conf: in den Zeilen der Community neander port, mtu, broker,
  prefix6 und name. Bei uns bleiben id (steckt in unseren MACs, darf sich nie
  aendern), host (Teil der oeffentlichen Adresse), ordner und prefix4. Eine
  Zeile, an der sich nichts aendert, bleibt Zeichen fuer Zeichen stehen.
- sitecodes.conf: ganz, aus den site_codes der Stammdaten.

Neue Domains legt das Skript nicht selbst an, und fehlt eine Domain in den
Stammdaten, bleibt ihre Zeile stehen. Beides braucht Handarbeit (Hostname-Teil
festlegen, Ortskarte einrichten bzw. loeschen) und steht als offener Punkt im
Stand fuer Checkmk.

Angewendet wird gezielt: ein Tunnel startet neu, wenn sich Port oder MTU
geaendert haben oder ein Broker weggefallen ist; ein hinzugekommener Broker
braucht keinen Neustart, der laufende Tunnel bleibt gueltig. Haben sich Namen
oder site_codes geaendert, werden die yanic-Konfiguration und die
Kartenkonfiguration neu erzeugt.

Liefert die Quelle Unsinn (kaputtes JSON, falsches Schema, unplausible Werte),
bleibt alles beim letzten guten Stand.
"""
import argparse
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import urllib.request

QUELLE = ('https://git.ideenwerk.me/neanderfunk/supernode/stammdaten/-/raw/'
          'main/erzeugt/stammdaten.json')
DOMAINS = '/etc/karte-en/domains.conf'
SITECODES = '/etc/karte-en/sitecodes.conf'
ZWISCHEN = '/var/lib/karte/stammdaten.json'
STAND = '/var/lib/karte/stammdaten-stand.json'
COMMUNITY = 'neander'
HOST = 'map.freifunk.space'

FELDER = ('community', 'code', 'ordner', 'port', 'id', 'host', 'mtu', 'broker',
          'prefix6', 'prefix4', 'name')

CODE = re.compile(r'^\d\d_[a-z0-9]+$')
SITE = re.compile(r'^[A-Za-z0-9_-]+$')
RECHNER = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$')
ULA = re.compile(r'^[0-9a-f:]+/\d{1,3}$')

SITE_KOPF = """\
# Welchen site_code die Knoten je Domain melden.
#
# Erzeugt von stammdaten-uebernehmen.py aus den Stammdaten
# (git.ideenwerk.me/neanderfunk/supernode/stammdaten), Feld site_codes.
# Aenderungen gehoeren dorthin, hier werden sie beim naechsten Lauf
# ueberschrieben. Gegenprobe im Netz mit sitecodes-ermitteln.py.
#
# code        site_codes (Komma)
"""


class Unsinn(Exception):
    pass


def holen(quelle):
    if re.match(r'^https?://', quelle):
        with urllib.request.urlopen(quelle, timeout=60) as r:
            return r.read()
    with open(quelle, 'rb') as f:
        return f.read()


def pruefen(d):
    """Gibt die Domains als {code: dict} zurueck oder wirft Unsinn."""
    if not isinstance(d, dict) or d.get('schema') != 1:
        raise Unsinn('Schema ist nicht 1')
    liste = d.get('domains')
    if not isinstance(liste, list) or not liste:
        raise Unsinn('keine Domains')
    erg = {}
    for x in liste:
        code = x.get('code')
        if not isinstance(code, str) or not CODE.match(code):
            raise Unsinn(f'Code {code!r}')
        if code in erg:
            raise Unsinn(f'{code} doppelt')
        nr, port, mtu = x.get('nr'), x.get('port'), x.get('mtu')
        if not all(isinstance(v, int) for v in (nr, port, mtu)):
            raise Unsinn(f'{code}: nr, port, mtu keine Zahlen')
        if code[:2] != f'{nr:02d}' or not 1024 < port < 65536 \
                or not 1200 <= mtu <= 1500:
            raise Unsinn(f'{code}: nr {nr}, port {port}, mtu {mtu}')
        broker = x.get('broker')
        if not isinstance(broker, list) or not broker:
            raise Unsinn(f'{code}: keine Broker')
        rechner = []
        for b in broker:
            h, _, p = str(b).rpartition(':')
            if not RECHNER.match(h) or p != str(port):
                raise Unsinn(f'{code}: Broker {b!r}')
            rechner.append(h)
        sites = x.get('site_codes')
        if not isinstance(sites, list) or not sites \
                or not all(isinstance(s, str) and SITE.match(s) for s in sites):
            raise Unsinn(f'{code}: site_codes {sites!r}')
        ula = x.get('ula')
        if not isinstance(ula, str) or not ULA.match(ula):
            raise Unsinn(f'{code}: ula {ula!r}')
        name = x.get('langname')
        if not isinstance(name, str) or not name.strip() \
                or any(ord(c) < 32 for c in name):
            raise Unsinn(f'{code}: langname {name!r}')
        erg[code] = {'port': str(port), 'mtu': str(mtu),
                     'broker': ','.join(rechner), 'prefix6': ula,
                     'name': name.strip(), 'sites': sites}
    return erg


def zeile(f):
    # Gleiche Spaltenbreiten wie die von Hand gepflegten Zeilen
    return (f"{f['community']} {f['code']:<10} {f['ordner']}  {f['port']} "
            f"{f['id']:>3} {f['host']:<28} {f['mtu']} {f['broker']} "
            f"{f['prefix6']:<26} {f['prefix4']:<15} {f['name']}")


def domains_neu(text, soll):
    """Neuer Text der domains.conf, dazu Aenderungen und Codes."""
    aus, aenderungen, vorhanden = [], [], set()
    for z in text.splitlines():
        t = z.split(None, len(FELDER) - 1)
        if z.startswith('#') or len(t) != len(FELDER) or t[0] != COMMUNITY:
            aus.append(z)
            continue
        alt = dict(zip(FELDER, t))
        code = alt['code']
        vorhanden.add(code)
        s = soll.get(code)
        if not s:
            aus.append(z)
            continue
        neu = dict(alt, **{k: s[k] for k in
                           ('port', 'mtu', 'broker', 'prefix6', 'name')})
        if neu == alt:
            aus.append(z)
            continue
        for k in ('port', 'mtu', 'broker', 'prefix6', 'name'):
            if alt[k] != neu[k]:
                aenderungen.append((code, k, alt[k], neu[k]))
        aus.append(zeile(neu))
    return '\n'.join(aus) + '\n', aenderungen, vorhanden


def sitecodes_neu(soll):
    return SITE_KOPF + ''.join(f'{c:<12} {",".join(s["sites"])}\n'
                               for c, s in sorted(soll.items()))


def daten(text):
    # Reihenfolge und Leerraum zaehlen nicht, nur der Inhalt
    return sorted(tuple(z.split()) for z in text.splitlines()
                  if z.strip() and not z.startswith('#'))


def lesen(pfad):
    try:
        with open(pfad, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def schreiben(pfad, text):
    tmp = pfad + '.neu'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, pfad)


def laufen(*befehl, ausgabe=None):
    print('  ' + ' '.join(befehl))
    if ausgabe:
        with open(ausgabe + '.neu', 'w', encoding='utf-8') as f:
            r = subprocess.run(befehl, stdout=f)
        if r.returncode == 0:
            os.replace(ausgabe + '.neu', ausgabe)
    else:
        r = subprocess.run(befehl)
    if r.returncode:
        print(f'  fehlgeschlagen ({r.returncode})', file=sys.stderr)
    return r.returncode == 0


def anwenden(aenderungen, sites_geaendert):
    neustart = set()
    karte = sites_geaendert
    for code, k, alt, neu in aenderungen:
        if k in ('port', 'mtu'):
            neustart.add(code)
        elif k == 'broker' and set(alt.split(',')) - set(neu.split(',')):
            neustart.add(code)
        elif k == 'name':
            karte = True
    for code in sorted(neustart):
        laufen('systemctl', 'try-restart', f'karte-en-tunnel@{code}.service')
    if karte:
        ok = laufen('/usr/local/sbin/karte-en-yanic-conf', COMMUNITY,
                    ausgabe=f'/etc/yanic-{COMMUNITY}.conf')
        ok = ok and laufen('systemctl', 'try-restart', f'yanic@{COMMUNITY}.service')
        ok = laufen('/usr/local/sbin/karte-en-konfig') and ok
        ok = laufen('nginx', '-t', '-q') and laufen('systemctl', 'reload', 'nginx') and ok
        return ok
    return True


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--quelle', default=QUELLE)
    a.add_argument('--domains', default=DOMAINS)
    a.add_argument('--sitecodes', default=SITECODES)
    a.add_argument('--zwischen', default=ZWISCHEN)
    a.add_argument('--stand', default=STAND)
    a.add_argument('--offline', action='store_true',
                   help='den letzten guten Stand nehmen statt zu holen')
    a.add_argument('--trocken', action='store_true',
                   help='nur zeigen, nichts schreiben')
    a.add_argument('--ohne-anwenden', action='store_true',
                   help='Dateien schreiben, aber nichts neu starten')
    o = a.parse_args()

    anwenden_ja = not (o.trocken or o.ohne_anwenden)
    if anwenden_ja and socket.gethostname() != HOST:
        sys.exit(f'Anwenden nur auf {HOST}; sonst --trocken oder --ohne-anwenden')

    try:
        roh = holen(o.zwischen if o.offline else o.quelle)
        d = json.loads(roh)
        soll = pruefen(d)
    except (OSError, ValueError, Unsinn) as e:
        sys.exit(f'Stammdaten unbrauchbar, alles bleibt beim alten: {e}')
    quelle = str(d.get('quelle', ''))

    alt_text = lesen(o.domains)
    if not daten(alt_text):
        sys.exit(f'{o.domains} fehlt oder ist leer')
    neu_text, aenderungen, vorhanden = domains_neu(alt_text, soll)
    alt_sites = lesen(o.sitecodes)
    neu_sites = sitecodes_neu(soll)
    sites_geaendert = daten(alt_sites) != daten(neu_sites)

    offen = [f'neue Domain {c} in den Stammdaten, von Hand einrichten'
             for c in sorted(set(soll) - vorhanden)]
    offen += [f'Domain {c} fehlt in den Stammdaten, Zeile steht noch'
              for c in sorted(vorhanden - set(soll))]

    print(f'Stammdaten {quelle[:19]}: {len(soll)} Domains, '
          f'{len(aenderungen)} Aenderungen in domains.conf, '
          f'sitecodes.conf {"geaendert" if sites_geaendert else "gleich"}')
    for code, k, alt, neu in aenderungen:
        print(f'  {code} {k}: {alt} -> {neu}')
    for p in offen:
        print(f'  offen: {p}')
    if o.trocken:
        return

    if aenderungen:
        schreiben(o.domains, neu_text)
    if neu_sites != alt_sites:
        schreiben(o.sitecodes, neu_sites)
    if not o.offline:
        schreiben(o.zwischen, roh.decode('utf-8'))

    ok = True
    if anwenden_ja and (aenderungen or sites_geaendert):
        ok = anwenden(aenderungen, sites_geaendert)
    if not o.offline:
        schreiben(o.stand, json.dumps({
            'zeit': datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec='seconds'),
            'quelle': quelle, 'domains': len(soll), 'offen': offen,
            'angewendet': ok}, ensure_ascii=False, indent=1) + '\n')
    if not ok:
        sys.exit('Anwenden teilweise fehlgeschlagen, siehe oben')


if __name__ == '__main__':
    main()
