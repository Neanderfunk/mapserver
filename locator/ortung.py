# SPDX-License-Identifier: BSD-3-Clause
"""Gemeinsames fuer Annahme und Auswertung der HVB-Ortung (Prototyp).

Format der Meldung: Version 1, abgestimmt mit der Packages-Session
(20.11.2026), Konzept Neanderfunk/packages docs/konzept-hvb-ortung.md 4.3.
Regel fuer Mesh-Partner: Entscheidung E11 im Konzept (4.4).
lan_mesh/lan_switch: Knoten in 25_hvb mit LAN-Mesh-Nachbarn genau einer
anderen Domain schalten selbst um (adorfer 20.11.2026, Konzept 4.3/4.4);
dafuer keine Auswertung, kein Manifest, E12 gilt nicht.
"""
import re

FORMAT_VERSION = 1
NODE_ID = re.compile(r'^[0-9a-f]{12}$')
MAX_NETZE = 200   # der Knoten schickt hoechstens 50; Puffer gegen Unsinn
MAX_BYTES = 65536

# Mesh-IDs, die nichts ueber den Standort sagen
MESH_OHNE_AUSSAGE = {'hvb-mesh'}


class Ungueltig(ValueError):
    pass


def pruefen(m):
    """Wirft Ungueltig, wenn die Meldung nicht zum Format passt. Gibt die
    Zahl der Netze zurueck. Unbekannte Felder sind erlaubt (spaetere
    Versionen), fehlende optionale auch."""
    if not isinstance(m, dict):
        raise Ungueltig('kein JSON-Objekt')
    if m.get('v') != FORMAT_VERSION:
        raise Ungueltig('v muss %d sein' % FORMAT_VERSION)
    if not isinstance(m.get('node_id'), str) or not NODE_ID.match(m['node_id']):
        raise Ungueltig('node_id: 12 Hexziffern, klein')
    wifi = m.get('wifi', [])
    if wifi == {}:  # jsonc: leeres Array als {}
        wifi = []
    if not isinstance(wifi, list) or len(wifi) > MAX_NETZE:
        raise Ungueltig('wifi: Liste mit hoechstens %d Eintraegen' % MAX_NETZE)
    for w in wifi:
        if not isinstance(w, dict) or not isinstance(w.get('bssid'), str):
            raise Ungueltig('wifi: Eintraege brauchen bssid')
        if not isinstance(w.get('signal'), (int, float)):
            raise Ungueltig('wifi: Eintraege brauchen signal')
    lm = m.get('lan_mesh', [])
    if not (lm == {} or isinstance(lm, list) and len(lm) <= MAX_NETZE):
        raise Ungueltig('lan_mesh: Liste (leer auch als {})')
    for n in lan_mesh(m):
        if not isinstance(n, dict):
            raise Ungueltig('lan_mesh: Eintraege muessen Objekte sein')
    if 'lan_switch' in m and not isinstance(m['lan_switch'], str):
        raise Ungueltig('lan_switch: Domain als Zeichenkette')
    return len(wifi)


def lan_mesh(m):
    """LAN-Mesh-Nachbarn als Liste. jsonc schreibt ein leeres Array als {}."""
    lm = m.get('lan_mesh')
    return lm if isinstance(lm, list) else []


def meshids_lesen(pfad):
    z = {}
    for zeile in open(pfad, encoding='utf-8'):
        t = zeile.split('#', 1)[0].split()
        if len(t) >= 2:
            z[t[0]] = t[1]
    return z


def mesh_partner(wifi, meshids):
    """Je gesehener Mesh-ID: Domain (oder None), staerkster Pegel, Zahl der
    BSSIDs. Gibt {mesh_id: {...}} zurueck."""
    p = {}
    for w in wifi:
        mid = w.get('mesh_id') or ''
        if not mid:
            continue
        e = p.setdefault(mid, {'domain': meshids.get(mid), 'staerkster': None, 'bssids': set()})
        e['bssids'].add(w['bssid'].lower())
        s = w['signal']
        if e['staerkster'] is None or s > e['staerkster']:
            e['staerkster'] = s
    for e in p.values():
        e['bssids'] = len(e['bssids'])
    return p


def zieldomain(partner, schwelle):
    """Regel E11 als Trockenlauf: eine Domain kommt in Frage mit einem
    Mesh-Punkt ab <schwelle> dBm oder mit zwei Mesh-Punkten beliebigen
    Pegels. Mehrere Kandidaten: der staerkste Mesh-Punkt entscheidet.
    hvb-mesh und unbekannte Mesh-IDs zaehlen nicht. Gibt Domain oder None."""
    je_domain = {}
    for mid, e in partner.items():
        if mid in MESH_OHNE_AUSSAGE or not e['domain']:
            continue
        d = je_domain.setdefault(e['domain'], {'staerkster': e['staerkster'], 'bssids': 0})
        d['bssids'] += e['bssids']
        d['staerkster'] = max(d['staerkster'], e['staerkster'])
    kandidaten = [(d['staerkster'], dom) for dom, d in je_domain.items()
                  if d['staerkster'] >= schwelle or d['bssids'] >= 2]
    return max(kandidaten)[1] if kandidaten else None



def _macs(liste):
    return {x.lower() for x in liste if isinstance(x, str)} if isinstance(liste, list) else set()


def darf_gehen(m, andere):
    """Regel E12 (adorfer 20.11.2026, Konzept 4.4 "Wer darf gehen?",
    a2ac1fd) als Trockenlauf, allein aus den Meldungen; kein Abgleich mit
    Kartendaten. m: letzte Meldung des Knotens X, andere: die letzten
    Meldungen aller Knoten. Gibt (True/False/None, Grund) zurueck; None
    heisst unklar, also nicht verschieben.

    - X meldet vpn false: nein.
    - Ein Knoten derselben Domain mit vpn false meldet als gw_nexthop eine
      MAC aus den mesh_macs von X, geht also ueber X ins Netz: nein.
    - Sonst ja. Ketten erledigen sich, weil jeder Knoten ohne VPN seinen
      eigenen Next Hop meldet.
    - Fehlen uplink, gw_nexthop oder mesh_macs: unklar."""
    u = m.get('uplink')
    if not isinstance(u, dict) or 'vpn' not in u:
        return None, 'kein Feld uplink in der Meldung'
    if not u['vpn']:
        return False, 'kein eigener VPN-Uplink (gw_via %s)' % u.get('gw_via', '?')
    if not u.get('gw_nexthop'):
        return None, 'gw_nexthop fehlt'
    eigene = _macs(u.get('mesh_macs'))
    if not eigene:
        return None, 'mesh_macs fehlen'
    haengen = sorted(
        a['node_id'] for a in andere
        if a.get('node_id') != m['node_id'] and a.get('domain') == m.get('domain')
        and isinstance(a.get('uplink'), dict) and a['uplink'].get('vpn') is False
        and str(a['uplink'].get('gw_nexthop', '')).lower() in eigene)
    if haengen:
        return False, 'ueber ihn gehen ins Netz: ' + ', '.join(haengen)
    return True, 'eigener VPN-Uplink, kein Knoten ohne VPN geht ueber ihn'
