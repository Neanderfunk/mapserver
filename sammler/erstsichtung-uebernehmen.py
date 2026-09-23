#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Uebernimmt die Erstsichtung aus einer aelteren Karte derselben Community.

  erstsichtung-uebernehmen.py --zeigen          # nur rechnen, nichts aendern
  erstsichtung-uebernehmen.py                   # eintragen (yanic anhalten!)
  erstsichtung-uebernehmen.py --quelle <URL|Datei>

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
QUELLE = 'https://map.eulenfunk.de/data/nodes.json'


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


def fremde_erstsichtung(daten):
    z = {}
    knoten = daten.get('nodes')
    if isinstance(knoten, dict):
        knoten = list(knoten.values())
    for n in knoten or []:
        nid = ((n.get('nodeinfo') or {}).get('node_id')
               or n.get('node_id') or n.get('nodeid'))
        t = zeit(n.get('firstseen') or n.get('first_seen'))
        if nid and t:
            z[nid.lower()] = t
    return z


def main():
    zeigen = '--zeigen' in sys.argv
    quelle = QUELLE
    if '--quelle' in sys.argv:
        quelle = sys.argv[sys.argv.index('--quelle') + 1]

    try:
        fremd = fremde_erstsichtung(hole(quelle))
    except (OSError, ValueError) as e:
        print(f'{quelle}: {e}', file=sys.stderr)
        return 1
    print(f'{len(fremd)} Knoten in der Quelle')

    try:
        zustand = json.load(open(ZUSTAND, encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'{ZUSTAND}: {e}', file=sys.stderr)
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

    shutil.copy2(ZUSTAND, ZUSTAND + '.vor-erstsichtung')
    neu_pfad = ZUSTAND + '.neu'
    with open(neu_pfad, 'w', encoding='utf-8') as f:
        json.dump(zustand, f, ensure_ascii=False)
    shutil.copymode(ZUSTAND, neu_pfad)
    os.replace(neu_pfad, ZUSTAND)
    print(f'geschrieben, Sicherung unter {ZUSTAND}.vor-erstsichtung')
    return 0


if __name__ == '__main__':
    sys.exit(main())
