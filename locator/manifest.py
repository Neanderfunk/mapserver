#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""HVB-Manifest fuer den nodeplacer erzeugen und signieren (Teil 1).

  sudo locator-manifest [--trocken]

Aus den abgelegten Ortungsmeldungen (je Knoten die letzte) kommt ein Knoten
ins Manifest, wenn
  - seine letzte Meldung aus 25_hvb stammt und hoechstens MAX_ALTER alt ist,
  - er nicht selbst per LAN-Mesh umschaltet (lan_switch),
  - Regel E11 eine Zieldomain liefert (Mesh-Partner, -75 dBm oder zwei
    Mesh-Punkte) und die nicht 25_hvb ist,
  - Regel E12 "darf gehen: ja" sagt.
Automatisch aus E11/E12: adorfer 20.11.2026. Ziel ueber die Position gibt
es noch nicht (Teil 2).

Format: Neanderfunk/packages neanderfunk-nodeplacer/docs/MANIFEST-FORMAT.md,
FORMAT=1, nur Methode domain (D-045). Signiert wird der Teil vor "---" mit
ecdsasign und dem HVB-Schluessel (nur root lesbar); der Knoten prueft gegen
den Pubkey in der Domain-Datei von 25_hvb. Ausgeliefert per http unter
<mirror>/nodeplacer.manifest, Mirror http://locator.ffnef.de/hvb/nodeplacer.

--trocken: Manifest nur ausgeben, nicht signieren, nicht schreiben.
"""
import datetime
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auswertung  # noqa: E402
import ortung  # noqa: E402

QUELLDOMAIN = '25_hvb'
MAX_ALTER = datetime.timedelta(days=3)   # Knoten melden taeglich
GUELTIG = datetime.timedelta(days=3)     # EXPIRES; laeuft der Timer nicht, verfaellt es
SCHLUESSEL = os.environ.get('LOCATOR_SCHLUESSEL', '/etc/locator/nodeplacer.secret')
ZIEL = os.environ.get('LOCATOR_MANIFEST', '/var/www/locator/hvb/nodeplacer/nodeplacer.manifest')


def zeitformat(t):
    """'YYYY-MM-DD HH:MM:SS+HH:MM' wie im Autoupdater-Manifest."""
    s = t.strftime('%Y-%m-%d %H:%M:%S%z')
    return s[:-2] + ':' + s[-2:]


def auswahl(aus, jetzt):
    """Zeilen (node_id, ziel) aus dem Ergebnis von auswertung.auswerten."""
    zeilen = []
    for a in aus:
        if a['domain'] != QUELLDOMAIN or a['darf_gehen'] is None:
            continue   # andere Domain, oder lan_switch (schaltet selbst)
        if jetzt - datetime.datetime.fromisoformat(a['letzte']) > MAX_ALTER:
            continue
        ziel = a['wuerde_verschieben']
        if not ziel or ziel == QUELLDOMAIN:
            continue
        if a['darf_gehen'][0] is not True:
            continue
        zeilen.append((a['node_id'], ziel))
    return sorted(zeilen)


def koerper(zeilen, jetzt):
    t = ['FORMAT=1',
         'DATE=' + zeitformat(jetzt),
         'EXPIRES=' + zeitformat(jetzt + GUELTIG),
         'COMMENT=HVB-Locator, automatisch aus E11/E12, %d Knoten' % len(zeilen)]
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


def main():
    jetzt = datetime.datetime.now().astimezone().replace(microsecond=0)
    aus = auswertung.auswerten(auswertung.lesen(auswertung.ABLAGE),
                               ortung.meshids_lesen(auswertung.MESHIDS))
    zeilen = auswahl(aus, jetzt.astimezone(datetime.timezone.utc))
    text = koerper(zeilen, jetzt)
    if '--trocken' in sys.argv:
        sys.stdout.write(text)
        return 0
    schreiben(text + '---\n' + signieren(text) + '\n')
    print('nodeplacer.manifest: %d Knoten%s' % (
        len(zeilen), ''.join('\n  %s -> %s' % z for z in zeilen)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
