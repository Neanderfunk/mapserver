#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Macht aus dem Uebergabeformat (community.json) eine domains.conf.

  ./site-lesen.py https://images.example.net/ --kuerzel xy > community.json
  ./domains-erzeugen.py community.json > ../tunnel/domains.conf

Die Namensteile fuer die Hostnamen sind ein Vorschlag aus dem Ordnernamen und
gehoeren vor dem Einsatz durchgesehen: sie stehen spaeter in den oeffentlichen
Adressen. Die IDs werden fortlaufend vergeben und duerfen sich spaeter nicht
mehr aendern, sie stecken in den MACs und in den Tunnel-IDs.
"""
import json
import re
import sys

UMLAUTE = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
                         'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue'})


def hostteil(d):
    s = (d.get('ordner') or d.get('code') or '').lower().translate(UMLAUTE)
    s = re.sub(r'^(images?|firmware|gluon)[_-]', '', s)
    return re.sub(r'[^a-z0-9]', '', s) or (d.get('code') or 'x')


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    g = json.load(open(sys.argv[1], encoding='utf-8'))
    d = g.get('domains') or []
    if not d:
        print('keine Domains in der Datei', file=sys.stderr)
        return 1

    arten = {x.get('vpn') for x in d}
    if arten != {'tunneldigger'}:
        print(f'Achtung: VPN-Arten {arten}. Die Tunnelschicht dieses Projekts '
              f'kann bisher nur Tunneldigger.', file=sys.stderr)

    zeilen = [(x.get('code') or '?', x.get('ordner') or '?', str(x.get('port') or '?'),
               str(i), hostteil(x), x.get('prefix6') or '-', x.get('prefix4') or '-',
               x.get('name') or '?')
              for i, x in enumerate(sorted(d, key=lambda y: str(y.get('code'))), 1)]
    breite = [max(len(z[s]) for z in zeilen) for s in range(7)]

    print(f'# Domains von {g.get("name") or g.get("community")}, gelesen aus den '
          f'site.json ihrer Images.')
    print(f'# Quelle: {g.get("quelle") or "?"}')
    print('# Erzeugt von werkzeug/domains-erzeugen.py, Hostnamen bitte durchsehen.')
    print('#')
    print('# code   ordner        port   id host          prefix6                    '
          'prefix4       name')
    for z in zeilen:
        print(' '.join([z[0].ljust(max(breite[0], 8)), z[1].ljust(breite[1]),
                        z[2].rjust(breite[2]), z[3].rjust(2), z[4].ljust(max(breite[4], 12)),
                        z[5].ljust(breite[5]), z[6].ljust(breite[6]), z[7]]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
