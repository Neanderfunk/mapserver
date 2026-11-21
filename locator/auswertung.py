#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Auswertung der abgelegten HVB-Ortungsmeldungen je node_id (Prototyp).

  sudo locator-auswertung [--json]

Je Knoten die letzte Meldung: Zeit, Domain, Release, Zahl der Netze,
exit_ip neben der Absenderadresse am Proxy (X-Forwarded-For), je gesehener
Mesh-ID staerkster Pegel und Zahl der BSSIDs, dazu die Domain, in die die
Regel E11 verschieben wuerde (-75 dBm, adorfer 20.11.2026), und ob er nach
Regel E12 gehen darf (aus den Meldungen, ohne Kartendaten). Nach aussen
geht hier nichts.

Ohne E11-Ziel kommt in 25_hvb die Position dazu (Teil 2, adorfer
21.11.2026): eingetragene Koordinaten des Knotens, sonst das Ergebnis von
locator-orten. Genauigkeitsradius ueber 5000 m oder keiner: Klaerung von
Hand. Sonst entscheidet das Feld der Domainflaechen (locator-flaechen),
ohne Feld bis zur 20-km-Stufe 21_dias.

Meldet ein Knoten lan_switch, schaltet er selbst per LAN-Mesh um (adorfer
20.11.2026): dann keine E11/E12-Auswertung, nur der Hinweis. Taucht seine
letzte Meldung danach aus der Zieldomain auf, gilt er als umgeschaltet.

Der Absender ist oft nicht die Exit-IP: Ein Knoten schickt eigenen Verkehr
per IPv6 ueber das Mesh (Freifunk-Prefix am Supernode), die exit_ip meldet
dagegen den WAN-Uplink. Verglichen wird deshalb nur bei gleicher
Adressfamilie.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortung  # noqa: E402

ABLAGE = os.environ.get('LOCATOR_ABLAGE', '/var/lib/locator/eingang')
POSITIONEN = os.environ.get('LOCATOR_POSITIONEN', '/var/lib/locator/position')
KARTE = os.environ.get('LOCATOR_KARTE', '/var/www/karte-en/sites/neander/alle/data/meshviewer.json')
MESHIDS = os.environ.get('LOCATOR_MESHIDS', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshids.conf'))
SCHWELLE = -75  # E11, adorfer 20.11.2026


def lesen(ablage):
    je_knoten = {}
    for pfad in sorted(glob.glob(os.path.join(ablage, '*', '*.json'))):
        try:
            e = json.load(open(pfad, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        nid = e['meldung']['node_id']
        e['datei'] = os.path.basename(pfad)
        k = je_knoten.setdefault(nid, {'meldungen': 0, 'letzte': None, 'lan_switch': None})
        k['meldungen'] += 1
        if e['meldung'].get('lan_switch') and (
                k['lan_switch'] is None or e['empfangen'] >= k['lan_switch']['zeit']):
            k['lan_switch'] = {'ziel': e['meldung']['lan_switch'], 'zeit': e['empfangen']}
        if k['letzte'] is None or e['empfangen'] >= k['letzte']['empfangen']:
            k['letzte'] = e
    return je_knoten


def position_lesen(ordner, nid):
    try:
        return json.load(open(os.path.join(ordner, nid + '.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return None


def position(e, nid, flaechen, positionen):
    """Schritte 2 bis 4 fuer einen Knoten ohne E11-Ziel: (position,
    position_ziel, klaerung). Genau eins von position_ziel und klaerung ist
    gesetzt."""
    m = e['meldung']
    c = m.get('coordinates')
    pos = None
    if c:
        if not (isinstance(c, dict) and ortung.ort_gueltig(c.get('lat'), c.get('lon'))):
            return None, None, 'eingetragene Koordinaten ungueltig'
        lat, lon = ortung.vergroebern(c['lat'], c['lon'])
        pos = {'quelle': 'Knoten', 'lat': lat, 'lon': lon, 'genauigkeit': 0}
    elif positionen:
        p = position_lesen(positionen, nid)
        if p and p.get('datei') == e.get('datei'):
            pos = p
    if pos is None:
        return None, None, 'noch nicht geortet'
    if pos.get('lat') is None:
        return pos, None, 'keine Position (%s)' % pos.get('grund', '?')
    g = pos.get('genauigkeit')
    if not isinstance(g, (int, float)) or g > ortung.MAX_GENAUIGKEIT:
        return pos, None, 'Genauigkeit %s m (Grenze %d m)' % (g, ortung.MAX_GENAUIGKEIT)
    if not flaechen:
        return pos, None, 'Domainflaechen noch nicht berechnet'
    return pos, ortung.position_ziel((pos['lat'], pos['lon']), g, flaechen), None


def absender_passt(xff, exit_ip):
    """True/False bei gleicher Adressfamilie, sonst None."""
    if not xff:
        return None
    familie = 'ipv6' if ':' in xff else 'ipv4'
    if familie not in exit_ip:
        return None
    return exit_ip[familie] == xff


def karte_lesen(pfad=KARTE):
    """{node_id: domain} aus der Gesamtausgabe von yanic."""
    d = json.load(open(pfad, encoding='utf-8'))
    return {n['node_id']: ortung.karten_domain(n) for n in d['nodes'] if n.get('node_id')}


def auswerten(je_knoten, meshids, flaechen=None, positionen=None, karte=None):
    """flaechen/positionen: fuer den Weg ueber die Position (Teil 2); ohne
    beides wie Teil 1, nur E11. karte: {node_id: domain}; damit gilt ein
    Knoten mit lan_switch als umgeschaltet, sobald er in der Zieldomain auf
    der Karte steht (dort meldet er nicht mehr)."""
    aus = []
    letzte = [k['letzte']['meldung'] for k in je_knoten.values()]
    for nid, k in sorted(je_knoten.items()):
        e = k['letzte']
        m = e['meldung']
        exit_ip = m.get('exit_ip') or {}
        xff = (e.get('x_forwarded_for') or '').split(',')[0].strip()
        wifi = m.get('wifi') if isinstance(m.get('wifi'), list) else []
        partner = ortung.mesh_partner(wifi, meshids)
        ls = k.get('lan_switch')
        selbst = bool(m.get('lan_switch'))
        e11 = None if selbst else ortung.zieldomain(partner, SCHWELLE)
        pos = pz = klaerung = None
        if not selbst and not e11 and m.get('domain') == '25_hvb' and (flaechen is not None or positionen):
            pos, pz, klaerung = position(e, nid, flaechen, positionen)
        aus.append({
            'node_id': nid,
            'meldungen': k['meldungen'],
            'letzte': e['empfangen'],
            'domain': m.get('domain'),
            'release': m.get('release'),
            'netze': len(wifi),
            'scan': m.get('scan'),
            'koordinaten': bool(m.get('coordinates')),
            'exit_ip': exit_ip,
            'absender': xff,
            'absender_passt': absender_passt(xff, exit_ip),
            'mesh': {mid: p for mid, p in sorted(partner.items(), key=lambda x: -x[1]['staerkster'])},
            'lan_mesh': ortung.lan_mesh(m),
            'lan_switch': ls,
            'karte': (karte or {}).get(nid),
            'lan_umgeschaltet': bool(ls) and ls['ziel'] in (m.get('domain'), (karte or {}).get(nid)),
            'wuerde_verschieben': e11,
            'position': pos,
            'position_ziel': pz,
            'ziel': e11 or (pz['ziel'] if pz else None),
            'weg': 'E11' if e11 else ('Position' if pz else None),
            'klaerung': klaerung,
            'uplink': m.get('uplink'),
            'darf_gehen': None if selbst else ortung.darf_gehen(m, letzte),
        })
    return aus


def text(aus):
    for a in aus:
        print('%s  %d Meldung(en), letzte %s' % (a['node_id'], a['meldungen'], a['letzte']))
        print('  Domain %s (Karte: %s), Release %s, %d Netze, Koordinaten %s' % (
            a['domain'], a['karte'] or '-', a['release'], a['netze'], 'ja' if a['koordinaten'] else 'nein'))
        print('  exit_ip %s, Absender %s (%s)' % (
            a['exit_ip'] or '-', a['absender'] or '-',
            {True: 'passt', False: 'passt NICHT', None: 'nicht vergleichbar'}[a['absender_passt']]))
        for mid, p in a['mesh'].items():
            print('  Mesh %-12s %-10s staerkster %4s dBm, %d BSSID(s)' % (
                mid, p['domain'] or 'unbekannt', p['staerkster'], p['bssids']))
        for n in a['lan_mesh']:
            if n.get('node_id'):
                wer = '%s %s' % (n['node_id'], n.get('domain') or 'Domain unbekannt')
            else:
                wer = 'schweigt (keine respondd-Antwort in 60 s)'
            print('  LAN-Mesh %-14s %-17s %s' % (n.get('iface', '?'), n.get('mac', '?'), wer))
        ls = a['lan_switch']
        if ls:
            print('  schaltet selbst um nach %s (LAN-Mesh, gemeldet %s): %s' % (
                ls['ziel'], ls['zeit'],
                'umgeschaltet, steht in der Zieldomain' if a['lan_umgeschaltet'] else 'noch nicht in der Zieldomain'))
        if a['darf_gehen'] is None:
            print('  E11/E12: entfaellt, Umschaltung per LAN-Mesh')
        else:
            print('  wuerde verschieben nach (E11, %d dBm): %s' % (SCHWELLE, a['wuerde_verschieben'] or '-'))
            p, pz = a.get('position'), a.get('position_ziel')
            if p and p.get('lat') is not None:
                print('  Position (%s, 200-m-Raster) %s,%s, Genauigkeit %s m' % (
                    p['quelle'], p['lat'], p['lon'], p['genauigkeit']))
            if pz:
                print('  Position ergibt: %s (%s)%s' % (
                    pz['ziel'], 'Stufe %d km, Feld %s' % (pz['stufe_km'], pz['feld'])
                    if pz['stufe_km'] else 'ausserhalb unseres Gebiets',
                    ', unklar neben %s' % pz['unklar'] if pz['unklar'] else ''))
            if a.get('klaerung'):
                print('  Klaerung von Hand: ' + a['klaerung'])
            ok, grund = a['darf_gehen']
            print('  darf gehen (E12): %s (%s)' % ({True: 'ja', False: 'nein', None: 'unklar'}[ok], grund))
        print()


if __name__ == '__main__':
    import flaechen
    aus = auswerten(lesen(ABLAGE), ortung.meshids_lesen(MESHIDS), flaechen.lesen(), POSITIONEN, karte_lesen())
    if '--json' in sys.argv:
        json.dump(aus, sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif not aus:
        print('keine Meldungen in ' + ABLAGE)
    else:
        text(aus)
