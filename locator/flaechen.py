#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Domainflaechen fuer die HVB-Ortung berechnen (Teil 2, Konzept 4.4 Schritt 3).

  locator-flaechen          (woechentlich per locator-flaechen.timer)

Statisches Datenmodell: je Ortsdomain das Kerngebiet aus den Positionen
ihrer Online-Knoten (ortung.kern, Ballungen wie der Community-Finder von
Mitfunken). Die Auswertung rechnet daraus je Position das Feld
(ortung.position_ziel). Woechentlich reicht (adorfer 21.11.2026).

Quelle ist die Gesamtausgabe von yanic (meshviewer.json aller Domains),
Ziel eine JSON-Datei, die nur der Dienstnutzer schreibt. Domains ohne
Ballung ab drei Knoten haben keine Flaeche und sind ueber die Position
nie Ziel.
"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auswertung  # noqa: E402
import ortung  # noqa: E402

QUELLE = os.environ.get('LOCATOR_KARTE', '/var/www/karte-en/sites/neander/alle/data/meshviewer.json')
ZIEL = os.environ.get('LOCATOR_FLAECHEN', '/var/lib/locator/flaechen/flaechen.json')


def berechnen(knoten, ziele):
    """knoten: nodes aus meshviewer.json. Gibt {domain: [[lat, lon], ...]}
    mit den Kerngebieten, Koordinaten auf etwa 100 m gerundet."""
    je_domain = {}
    for n in knoten:
        loc = n.get('location') or {}
        lat, lon = loc.get('latitude'), loc.get('longitude')
        d = ortung.karten_domain(n)
        if n.get('is_online') and not n.get('is_gateway') and d in ziele and ortung.ort_gueltig(lat, lon):
            je_domain.setdefault(d, []).append((round(lat, 3), round(lon, 3)))
    return {d: [list(p) for p in ortung.kern(pk)] for d, pk in sorted(je_domain.items())
            if ortung.kern(pk)}


def main():
    ziele = ortung.positionsziele(ortung.meshids_lesen(auswertung.MESHIDS))
    knoten = json.load(open(QUELLE, encoding='utf-8'))['nodes']
    flaechen = berechnen(knoten, ziele)
    inhalt = {'erzeugt': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
              'domains': flaechen}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ZIEL), prefix='.flaechen-')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(inhalt, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ZIEL)
    ohne = [d for d in ziele if d not in flaechen]
    print('Flaechen: %d Domains, %d Kernknoten; ohne Flaeche: %s' % (
        len(flaechen), sum(len(v) for v in flaechen.values()), ', '.join(ohne) or '-'))
    return 0


def lesen(pfad=ZIEL):
    """{domain: [(lat, lon)]} oder None, wenn noch nicht berechnet."""
    try:
        d = json.load(open(pfad, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return {k: [tuple(p) for p in v] for k, v in d['domains'].items()}


if __name__ == '__main__':
    sys.exit(main())
