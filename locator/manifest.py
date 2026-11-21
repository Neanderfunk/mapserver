#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""HVB-Manifest fuer den nodeplacer erzeugen und signieren (Teil 1).

  sudo locator-manifest [--trocken]
  sudo locator-manifest --hand <node_id> <ziel> [<stunden>]   (Vorgabe 72)
  sudo locator-manifest --hand-weg <node_id>
  sudo locator-manifest --hand-liste

Aus den abgelegten Ortungsmeldungen (je Knoten die letzte) kommt ein Knoten
ins Manifest, wenn
  - seine letzte Meldung aus 25_hvb stammt und hoechstens MAX_ALTER alt ist,
  - er laut Karte gerade in 25_hvb ist (Konzept 4.4 Punkt 1),
  - er nicht selbst per LAN-Mesh umschaltet (lan_switch),
  - Regel E11 eine Zieldomain liefert (Mesh-Partner, -75 dBm oder zwei
    Mesh-Punkte), sonst die Position ohne Klaerungsfall (Teil 2,
    auswertung.position), und das Ziel nicht 25_hvb ist,
  - Regel E12 "darf gehen: ja" sagt.
Automatisch aus E11/E12: adorfer 20.11.2026, Position: adorfer 21.11.2026.

Handeintraege (Konzept 4.4 Punkt 5, Klaerung von Hand) stehen in HAND, eine
Zeile "<node_id> <ziel> <bis>" je Knoten. Sie gehen ohne weitere Pruefung
ins Manifest, bis sie ablaufen, und haben Vorrang vor der Automatik.

Format: Neanderfunk/packages neanderfunk-nodeplacer/docs/MANIFEST-FORMAT.md,
FORMAT=1, nur Methode domain (D-045). Signiert wird der Teil vor "---" mit
ecdsasign und dem HVB-Schluessel (nur root lesbar); der Knoten prueft gegen
den Pubkey in der Domain-Datei von 25_hvb. Ausgeliefert per http unter
<mirror>/nodeplacer.manifest, Mirror http://locator.ffnef.de/hvb/nodeplacer.

--trocken: Manifest nur ausgeben, nicht signieren, nicht schreiben.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auswertung  # noqa: E402
import flaechen  # noqa: E402
import ortung  # noqa: E402

QUELLDOMAIN = '25_hvb'
MAX_ALTER = datetime.timedelta(days=3)   # Knoten melden taeglich
GUELTIG = datetime.timedelta(days=3)     # EXPIRES; laeuft der Timer nicht, verfaellt es
SCHLUESSEL = os.environ.get('LOCATOR_SCHLUESSEL', '/etc/locator/nodeplacer.secret')
HAND = os.environ.get('LOCATOR_HAND', '/etc/locator/hand.conf')
ZIEL = os.environ.get('LOCATOR_MANIFEST', '/var/www/locator/hvb/nodeplacer/nodeplacer.manifest')


def zeitformat(t):
    """'YYYY-MM-DD HH:MM:SS+HH:MM' wie im Autoupdater-Manifest."""
    s = t.strftime('%Y-%m-%d %H:%M:%S%z')
    return s[:-2] + ':' + s[-2:]


def auswahl(aus, jetzt, karte=None, hand=None):
    """Zeilen (node_id, ziel) aus dem Ergebnis von auswertung.auswerten.
    karte: {node_id: domain} laut Kartendaten (None: nicht pruefen), hand:
    gueltige Handeintraege {node_id: ziel}, die vorgehen."""
    zeilen = dict(hand or {})
    for a in aus:
        if a['node_id'] in zeilen:
            continue
        if a['domain'] != QUELLDOMAIN or a['darf_gehen'] is None:
            continue   # andere Domain, oder lan_switch (schaltet selbst)
        if karte is not None and karte.get(a['node_id']) != QUELLDOMAIN:
            continue
        if jetzt - datetime.datetime.fromisoformat(a['letzte']) > MAX_ALTER:
            continue
        ziel = a.get('ziel', a['wuerde_verschieben'])
        if not ziel or ziel == QUELLDOMAIN or a.get('klaerung'):
            continue
        if a['darf_gehen'][0] is not True:
            continue
        zeilen[a['node_id']] = ziel
    return sorted(zeilen.items())


def hand_lesen(pfad=None):
    """{node_id: (ziel, bis)} aller Zeilen; abgelaufene inbegriffen."""
    h = {}
    try:
        f = open(pfad or HAND, encoding='utf-8')
    except FileNotFoundError:
        return h
    for zeile in f:
        t = zeile.split('#', 1)[0].split()
        if len(t) == 3 and ortung.NODE_ID.match(t[0]):
            h[t[0]] = (t[1], datetime.datetime.fromisoformat(t[2]))
    return h


def hand_gueltig(h, jetzt):
    return {nid: z for nid, (z, bis) in h.items() if bis > jetzt}


def hand_schreiben(h):
    t = '# Handeintraege fuer das HVB-Manifest (locator-manifest --hand), node_id ziel bis\n'
    t += ''.join('%s %s %s\n' % (nid, z, bis.isoformat()) for nid, (z, bis) in sorted(h.items()))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(HAND), prefix='.hand-')
    with os.fdopen(fd, 'w') as f:
        f.write(t)
    os.replace(tmp, HAND)


def karte_lesen():
    """{node_id: domain} aus der Gesamtausgabe von yanic."""
    d = json.load(open(flaechen.QUELLE, encoding='utf-8'))
    return {n['node_id']: ortung.karten_domain(n) for n in d['nodes'] if n.get('node_id')}


def koerper(zeilen, jetzt):
    t = ['FORMAT=1',
         'DATE=' + zeitformat(jetzt),
         'EXPIRES=' + zeitformat(jetzt + GUELTIG),
         'COMMENT=HVB-Locator, automatisch aus E11/E12/Position und von Hand, %d Knoten' % len(zeilen)]
    t += ['%s domain target=%s' % z for z in zeilen]
    return ''.join(z + '\n' for z in t)


def signieren(text):
    with tempfile.NamedTemporaryFile('w', delete=False) as f:
        f.write(text)
    try:
        with open(SCHLUESSEL) as s:
            sig = subprocess.run(['ecdsasign', f.name], stdin=s, capture_output=True,
                                 text=True, check=True).stdout.strip()
    finally:
        os.unlink(f.name)
    if len(sig) != 128 or any(c not in '0123456789abcdef' for c in sig):
        raise RuntimeError('ecdsasign lieferte keine Signatur')
    return sig


def schreiben(inhalt):
    d = os.path.dirname(ZIEL)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.manifest-')
    with os.fdopen(fd, 'w') as f:
        f.write(inhalt)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ZIEL)


def hand_befehl(args, jetzt):
    h = hand_lesen()
    if args[0] == '--hand-liste':
        for nid, (z, bis) in sorted(h.items()):
            print('%s -> %s bis %s%s' % (nid, z, bis.isoformat(), '' if bis > jetzt else ' (abgelaufen)'))
        return 0
    if len(args) < 2 or not ortung.NODE_ID.match(args[1]):
        print('node_id: 12 Hexziffern, klein', file=sys.stderr)
        return 2
    if args[0] == '--hand-weg':
        h.pop(args[1], None)
    else:
        domains = set(ortung.meshids_lesen(auswertung.MESHIDS).values()) - {QUELLDOMAIN}
        if len(args) < 3 or args[2] not in domains:
            print('Ziel: eine unserer Domains ausser %s' % QUELLDOMAIN, file=sys.stderr)
            return 2
        stunden = float(args[3]) if len(args) > 3 else 72
        h[args[1]] = (args[2], jetzt + datetime.timedelta(hours=stunden))
    hand_schreiben(h)
    return erzeugen(jetzt)


def erzeugen(jetzt, trocken=False):
    utc = jetzt.astimezone(datetime.timezone.utc)
    aus = auswertung.auswerten(auswertung.lesen(auswertung.ABLAGE),
                               ortung.meshids_lesen(auswertung.MESHIDS),
                               flaechen.lesen(), auswertung.POSITIONEN)
    hand = hand_gueltig(hand_lesen(), utc)
    zeilen = auswahl(aus, utc, karte_lesen(), hand)
    text = koerper(zeilen, jetzt)
    if trocken:
        sys.stdout.write(text)
        return 0
    schreiben(text + '---\n' + signieren(text) + '\n')
    print('nodeplacer.manifest: %d Knoten%s' % (len(zeilen), ''.join(
        '\n  %s -> %s%s' % (n, z, ' (von Hand)' if n in hand else '') for n, z in zeilen)))
    return 0


def main():
    jetzt = datetime.datetime.now().astimezone().replace(microsecond=0)
    a = sys.argv[1:]
    if a and a[0] in ('--hand', '--hand-weg', '--hand-liste'):
        return hand_befehl(a, jetzt)
    return erzeugen(jetzt, '--trocken' in a)


if __name__ == '__main__':
    sys.exit(main())
