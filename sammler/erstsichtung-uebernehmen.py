#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Uebernimmt die Erstsichtung aus einer aelteren Karte derselben Community.

  erstsichtung-uebernehmen.py --zeigen          # nur rechnen, nichts aendern
  erstsichtung-uebernehmen.py                   # eintragen (yanic anhalten!)
  erstsichtung-uebernehmen.py --quelle <config.json|nodes.json|Datei>
  erstsichtung-uebernehmen.py --quelle <Datei> --zustand /var/lib/yanic/essen.json

Unsere Karte kennt jeden Knoten erst, seit wir messen. Im Knotenfenster steht
dann als Erstsichtung der Tag, an dem dieser Server aufgebaut wurde, und nicht
der Tag, an dem der Knoten ans Netz ging. Die aeltere Karte derselben
Community weiss es besser, und sie gibt es in ihrer nodes.json heraus.

Uebernommen wird nur, was aelter ist. Der Zustand wird also nie juenger, und
ein zweiter Lauf aendert nichts mehr. Knoten, die nur die andere Karte kennt,
werden nicht erfunden: was wir nicht selbst gesehen haben, steht auch nicht in
unseren Daten.

yanic haelt den Zustand im Speicher und schreibt ihn jede Minute. Deshalb muss
der Sammler waehrenddessen stehen, sonst ueberschreibt er die Aenderung:

  systemctl stop yanic@neander
  erstsichtung-uebernehmen.py
  systemctl start yanic@neander
"""
import datetime
import json
import os
import shutil
import sys
import urllib.request

ZUSTAND = '/var/lib/yanic/neander.json'
# Die Karte der Community setzt sich aus einer Quelle je Domain zusammen; die
# Liste steht in ihrer config.json unter dataPath. Die Sammeldatei
# /data/nodes.json daneben ist ein Ueberbleibsel und unvollstaendig: Knoten
# stehen dort mehrfach und teils mit juengerem Datum (24.09.2026 gemessen).
QUELLE = 'https://map.eulenfunk.de/config.json'


def zeit(s):
    """Beide Schreibweisen lesen: mit Z und Millisekunden oder mit Offset."""
    if not s:
        return None
    s = s.strip()
    if s.endswith('Z'):
        s = s[:-1] + '+0000'
    for form in ('%Y-%m-%dT%H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S%z',
                 '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            t = datetime.datetime.strptime(s, form)
        except ValueError:
            continue
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    return None


def hole(quelle):
    if quelle.startswith(('http://', 'https://')):
        with urllib.request.urlopen(quelle, timeout=60) as r:
            return json.load(r)
    return json.load(open(quelle, encoding='utf-8'))


def quellen(start):
    """Eine config.json nennt ihre Datenquellen selbst, sonst ist es die Datei."""
    if not start.endswith('config.json'):
        return [start]
    try:
        pfade = hole(start).get('dataPath') or []
    except (OSError, ValueError):
        return [start]
    return [p.rstrip('/') + '/nodes.json' for p in pfade]


def sammeln(daten, z):
    """Erstsichtung einsammeln, je Knoten die aelteste.

    Knoten stehen in solchen Dateien mehrfach: in mehreren Domains, oder
    doppelt in derselben Datei. Wer einfach den letzten Eintrag nimmt,
    bekommt ein zufaelliges Datum (24.09.2026: so blieb ein Knoten bei elf
    Tagen statt zehn Monaten).
    """
    knoten = daten.get('nodes')
    if isinstance(knoten, dict):
        knoten = list(knoten.values())
    for n in knoten or []:
        nid = ((n.get('nodeinfo') or {}).get('node_id')
               or n.get('node_id') or n.get('nodeid'))
        t = zeit(n.get('firstseen') or n.get('first_seen'))
        if not nid or not t:
            continue
        nid = nid.lower()
        if nid not in z or t < z[nid]:
            z[nid] = t
    return z


def main():
    zeigen = '--zeigen' in sys.argv
    quelle = QUELLE
    if '--quelle' in sys.argv:
        quelle = sys.argv[sys.argv.index('--quelle') + 1]
    # Andere Community als neander, etwa /var/lib/yanic/essen.json
    zustand_pfad = ZUSTAND
    if '--zustand' in sys.argv:
        zustand_pfad = sys.argv[sys.argv.index('--zustand') + 1]

    fremd, gelesen, fehler = {}, 0, []
    for q in quellen(quelle):
        try:
            sammeln(hole(q), fremd)
            gelesen += 1
        except (OSError, ValueError) as e:
            fehler.append(f'{q}: {str(e)[:60]}')
    if not fremd:
        print('keine Quelle lesbar', file=sys.stderr)
        for f in fehler:
            print('  ' + f, file=sys.stderr)
        return 1
    print(f'{len(fremd)} Knoten aus {gelesen} Quellen'
          + (f', {len(fehler)} nicht erreichbar' if fehler else ''))

    try:
        zustand = json.load(open(zustand_pfad, encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'{zustand_pfad}: {e}', file=sys.stderr)
        return 1

    unsere = zustand.get('nodes') or {}
    geaendert, unbekannt, aelteste = 0, 0, None
    beispiele = []
    for nid, eintrag in unsere.items():
        alt = fremd.get(nid.lower())
        if not alt:
            unbekannt += 1
            continue
        jetzt = zeit(eintrag.get('firstseen'))
        if jetzt and alt >= jetzt:
            continue
        neu = alt.astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')
        if len(beispiele) < 5:
            beispiele.append((eintrag.get('nodeinfo', {}).get('hostname'),
                              eintrag.get('firstseen'), neu))
        eintrag['firstseen'] = neu
        geaendert += 1
        if aelteste is None or alt < aelteste:
            aelteste = alt

    print(f'{geaendert} Knoten bekommen eine aeltere Erstsichtung, '
          f'{unbekannt} kennt die Quelle nicht')
    if aelteste:
        print(f'aelteste uebernommene Sichtung: {aelteste.date()}')
    for name, vorher, nachher in beispiele:
        print(f'  {name:34} {vorher} -> {nachher}')

    if zeigen or not geaendert:
        return 0

    shutil.copy2(zustand_pfad, zustand_pfad + '.vor-erstsichtung')
    neu_pfad = zustand_pfad + '.neu'
    with open(neu_pfad, 'w', encoding='utf-8') as f:
        json.dump(zustand, f, ensure_ascii=False)
    shutil.copymode(zustand_pfad, neu_pfad)
    os.replace(neu_pfad, zustand_pfad)
    print(f'geschrieben, Sicherung unter {zustand_pfad}.vor-erstsichtung')
    return 0


if __name__ == '__main__':
    sys.exit(main())
