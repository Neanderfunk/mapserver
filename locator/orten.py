#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Position aus dem WLAN-Scan beim Ortungsanbieter holen (Teil 2, Konzept 4.4
Schritt 2.3). Laeuft als Dienstnutzer locator vor jedem Manifest-Lauf.

  locator-orten

Gefragt wird nur fuer Knoten, deren letzte Meldung aus 25_hvb kommt, ohne
lan_switch, ohne E11-Ziel und ohne eingetragene Koordinaten, und nur einmal
je Meldung. An beaconDB gehen nur BSSIDs und Pegel, keine node_id, keine
SSIDs, keine Freifunk-BSSIDs; Rueckfall auf IP-Ortung ist aus. Abgelegt
wird je Knoten das Ergebnis mit Position im 200-m-Raster und
Genauigkeitsradius (0600, nach 14 Tagen weg, locator-aufraeumen).

Google Geolocation (zweite Stufe im Konzept) ist noch nicht drin: dafuer
gibt es noch keinen API-Schluessel.
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auswertung  # noqa: E402
import ortung  # noqa: E402

POSITIONEN = os.environ.get('LOCATOR_POSITIONEN', '/var/lib/locator/position')
BEACONDB = 'https://api.beacondb.net/v1/geolocate'
USER_AGENT = 'neanderfunk-locator/1 (+https://github.com/Neanderfunk/mapserver)'
FREIFUNK_SSID = re.compile(r'freifunk|neanderfunk|ffnef|eulenfunk', re.I)


def netze_fuer_anbieter(wifi):
    """Nur fremde WLANs: keine Mesh-Punkte, keine Freifunk-SSIDs, keine
    lokal verwalteten MACs (zufaellig oder abgeleitet, ohne festen Ort)."""
    aus = []
    for w in wifi:
        b = w['bssid'].lower()
        if w.get('mesh_id') or FREIFUNK_SSID.search(w.get('ssid') or ''):
            continue
        try:
            if int(b[:2], 16) & 2:
                continue
        except ValueError:
            continue
        aus.append({'macAddress': b, 'signalStrength': int(w['signal'])})
    return aus


def beacondb(netze):
    """(lat, lon, accuracy) oder None, wenn beaconDB nichts weiss."""
    body = json.dumps({'considerIp': False, 'fallbacks': {'lacf': False, 'ipf': False},
                       'wifiAccessPoints': netze}).encode()
    req = urllib.request.Request(BEACONDB, data=body, headers={
        'Content-Type': 'application/json', 'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    loc = d.get('location') or {}
    if not ortung.ort_gueltig(loc.get('lat'), loc.get('lng')):
        return None
    return loc['lat'], loc['lng'], d.get('accuracy')


def braucht_ortung(m, meshids):
    if m.get('domain') != '25_hvb' or m.get('lan_switch') or m.get('coordinates'):
        return False
    wifi = m.get('wifi') if isinstance(m.get('wifi'), list) else []
    return ortung.zieldomain(ortung.mesh_partner(wifi, meshids), auswertung.SCHWELLE) is None


def ergebnis(m):
    wifi = m.get('wifi') if isinstance(m.get('wifi'), list) else []
    netze = netze_fuer_anbieter(wifi)
    e = {'quelle': 'beaconDB', 'netze': len(netze), 'lat': None, 'lon': None, 'genauigkeit': None}
    if len(netze) < 2:
        e['grund'] = 'weniger als 2 fremde WLANs'
        return e
    r = beacondb(netze)
    if r is None:
        e['grund'] = 'beaconDB kennt die WLANs nicht'
        return e
    e['lat'], e['lon'] = ortung.vergroebern(r[0], r[1])
    e['genauigkeit'] = r[2]
    return e


def main():
    meshids = ortung.meshids_lesen(auswertung.MESHIDS)
    for nid, k in sorted(auswertung.lesen(auswertung.ABLAGE).items()):
        m = k['letzte']['meldung']
        if not braucht_ortung(m, meshids):
            continue
        pfad = os.path.join(POSITIONEN, nid + '.json')
        alt = auswertung.position_lesen(POSITIONEN, nid)
        if alt and alt.get('datei') == k['letzte']['datei']:
            continue
        try:
            e = ergebnis(m)
        except (OSError, ValueError) as x:
            print('%s: Anbieter nicht erreichbar (%s), naechster Lauf' % (nid, x))
            continue
        e['datei'] = k['letzte']['datei']
        e['zeit'] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        fd = os.open(pfad + '.neu', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(e, f)
        os.replace(pfad + '.neu', pfad)
        print('%s: %s' % (nid, e.get('grund') or 'Genauigkeit %s m' % e['genauigkeit']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
