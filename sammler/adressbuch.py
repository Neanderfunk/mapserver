#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Adressbuch: node_id -> aktuelle Adressen, fuer Sammler ausserhalb.

  adressbuch.py [community]        # Vorgabe neander

Die node_id eines Knotens ist stabil, seine oeffentliche Adresse nicht: sie
haengt am Supernode, und beim Supernode- oder Praefixwechsel wandert das /64
der ganzen Domain (20.09.2026, u.a. wlf 300e:412 -> 100c:612). Wer Knoten per
Adresse abfragt, haelt danach veraltete Adressen. Dieser Server hat die
Adressen ohnehin, er bekommt sie alle paar Minuten per respondd.

Ausgabe /var/www/karte-en/api/<community>/targets.json, oeffentlich unter
https://<community>.map.freifunk.space/nf/targets.json. Nur, was die Karte
ohnehin zeigt: keine Besitzerangaben.

last_seen unterscheidet "umgezogen" von "wirklich weg". Damit ein Knoten, den
yanic nach prune_after vergisst, nicht einfach aus der Liste faellt, fuehrt das
Skript einen eigenen Bestand in /var/lib/karte/adressbuch/<community>.json.
"""
import datetime
import json
import os
import sys

WEB = '/var/www/karte-en/sites'
API = '/var/www/karte-en/api'
BESTAND = '/var/lib/karte/adressbuch'
SITE_KONF = '/etc/karte-en/sitecodes.conf'


def domain_nach_code():
    """Gemeldeter site_code (nef-10_wlf, ..._EOL) -> Domain (10_wlf)."""
    z = {}
    try:
        for zeile in open(SITE_KONF, encoding='utf-8'):
            zeile = zeile.strip()
            if zeile and not zeile.startswith('#'):
                code, _, liste = zeile.partition(' ')
                z[code] = code
                for c in liste.replace(' ', '').split(','):
                    if c:
                        z[c] = code
    except OSError:
        pass
    return z


def reihenfolge(adresse):
    # oeffentlich zuerst, dann ULA; Link-Local nuetzt von aussen nichts
    a = adresse.lower()
    if a.startswith('fe80'):
        return None
    return 1 if a.startswith(('fc', 'fd')) else 0


def zeit(s):
    # yanic schreibt 2026-09-22T18:02:31+0200, ausgegeben wird UTC mit Z
    try:
        t = datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S%z')
    except (TypeError, ValueError):
        return None
    return t.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def schreibe(pfad, daten):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    neu = pfad + '.neu'
    with open(neu, 'w', encoding='utf-8') as f:
        json.dump(daten, f, ensure_ascii=False, separators=(',', ':'),
                  sort_keys=True)
    os.chmod(neu, 0o644)
    os.replace(neu, pfad)


def main():
    community = sys.argv[1] if len(sys.argv) > 1 else 'neander'
    quelle = f'{WEB}/{community}/alle/data/nodes.json'
    try:
        daten = json.load(open(quelle, encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'{quelle}: {e}', file=sys.stderr)
        return 1

    codes = domain_nach_code()
    bestand_pfad = f'{BESTAND}/{community}.json'
    try:
        bestand = json.load(open(bestand_pfad, encoding='utf-8'))
    except (OSError, ValueError):
        bestand = {}

    for n in daten.get('nodes') or []:
        ni = n.get('nodeinfo') or {}
        nid = ni.get('node_id')
        if not nid:
            continue
        sc = (ni.get('system') or {}).get('site_code')
        dc = (ni.get('system') or {}).get('domain_code')
        adr = [a for a in (ni.get('network') or {}).get('addresses') or []
               if reihenfolge(a) is not None]
        adr.sort(key=reihenfolge)
        alt = bestand.get(nid, {})
        eintrag = {
            'hostname': ni.get('hostname'),
            'site_code': sc or dc,
            'domain': codes.get(sc or '', None) or codes.get(dc or '', None)
                      or dc or sc,
            'addresses': adr or alt.get('addresses', []),
            'last_seen': zeit(n.get('lastseen')) or alt.get('last_seen'),
            'online': bool((n.get('flags') or {}).get('online')),
        }
        # Eine Adresse, die der Knoten nicht mehr meldet, ist Geschichte; die
        # letzte bekannte bleibt dafuer stehen, bis er wieder antwortet.
        if eintrag['last_seen'] and alt.get('last_seen', '') > eintrag['last_seen']:
            continue
        bestand[nid] = eintrag

    # Wen yanic schon vergessen hat, der steht nur noch im Bestand
    gesehen = {(n.get('nodeinfo') or {}).get('node_id')
               for n in daten.get('nodes') or []}
    for nid, e in bestand.items():
        if nid not in gesehen:
            e['online'] = False

    schreibe(bestand_pfad, bestand)
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    schreibe(f'{API}/{community}/targets.json', {
        'generated': jetzt.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': zeit(daten.get('timestamp')),
        'community': community,
        'nodes': bestand,
    })
    return 0


if __name__ == '__main__':
    sys.exit(main())
