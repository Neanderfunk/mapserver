#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Liest die site.json aus den Firmware-Images einer Community.

Das ist der Weg, auf dem eine Community, die keine Karte und keinen brauchbaren
Verzeichniseintrag hat, trotzdem vollstaendig beschreibbar wird: ihre Images
tragen alles, was wir zum Mitmessen brauchen, naemlich Domainnamen, Praefixe,
VPN-Art und Brokerports.

  ./site-lesen.py https://images.freifunk-en.de/ > gemeinschaft.json

Ohne Argumente liest es Image-URLs zeilenweise von der Standardeingabe. Der
Kopf des Ergebnisses ist von Hand nachzupflegen (Name, Kuerzel), alles unter
"domains" kommt aus den Images.

Gluon legt die site.json unbehandelt ins squashfs, wir brauchen also nur
unsquashfs und kein Flashen. Ein Image je Domain genuegt, das kleinste reicht.
"""
import argparse
import json
import os
import re
import subprocess
import struct
import sys
import tempfile
import urllib.parse
import urllib.request

UA = {'User-Agent': 'Freifunk-Kartenprojekt (projekt@neanderfunk.de)'}
KLEIN = ('wr841', 'wr842', 'archer-c6-v2', 'archer-c50', 'wr1043')
MAX_MB = 30


def holen(url, max_mb=MAX_MB):
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=90) as f:
        return f.read(max_mb << 20)


def seite(url):
    try:
        return holen(url, 2).decode('utf-8', 'replace')
    except OSError as e:
        print(f'  {url}: {e}', file=sys.stderr)
        return ''


def site_json(daten):
    """site.json und domains/*.json aus einem Image."""
    with tempfile.NamedTemporaryFile(suffix='.img') as f:
        f.write(daten)
        f.flush()
        pos = 0
        for _ in range(8):
            off = daten.find(b'hsqs', pos)
            if off < 0:
                break
            pos = off + 4

            def cat(pfad):
                p = subprocess.run(['unsquashfs', '-o', str(off), '-cat', f.name, pfad],
                                   capture_output=True, timeout=120)
                return p.stdout if p.returncode == 0 and p.stdout else None

            roh = cat('lib/gluon/site.json')
            if not roh:
                continue
            doms = {}
            l = subprocess.run(['unsquashfs', '-o', str(off), '-l', f.name,
                                'lib/gluon/domains'], capture_output=True, text=True, timeout=120)
            for z in l.stdout.splitlines():
                m = re.search(r'lib/gluon/domains/([^/]+)\.json$', z)
                if m:
                    d = cat(f'lib/gluon/domains/{m.group(1)}.json')
                    if d:
                        doms[m.group(1)] = json.loads(d)
            return json.loads(roh), doms
    return None, None


def zahlen(s):
    """Versionsartige Namen numerisch, damit 2025.1.10 hinter 2025.1.9 kommt."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', s)]


def images_finden(basis, max_seiten=120, tiefe=4):
    """Imageserver durchgehen und je Domainordner ein kleines Image finden.

    Bewusst geduldig: Gluon-Imageserver sind mal schlichte Verzeichnisse, mal
    Dateibrowser mit ?dir=. Gesucht werden sysupgrade-Images; der Ordner
    darueber gilt als Domain, die Ebene darueber als Version.
    """
    dirbrowser = '?dir=' in seite(basis)
    gesehen, warteschlange, funde = set(), [''], {}
    while warteschlange and len(gesehen) < max_seiten:
        pfad = warteschlange.pop(0)
        if pfad in gesehen or pfad.count('/') > tiefe:
            continue
        gesehen.add(pfad)
        url = f'{basis}?dir={pfad}' if dirbrowser else urllib.parse.urljoin(basis, pfad)
        roh = seite(url)
        bins = re.findall(r'href="([^"]*sysupgrade[^"]*\.bin)"', roh)
        if bins:
            klein = [b for b in bins if any(k in b for k in KLEIN)] or sorted(bins)
            funde[pfad] = urllib.parse.urljoin(basis, klein[0].lstrip('/'))
            continue                       # tiefer muss hier niemand suchen
        if dirbrowser:
            unter = [u for u in re.findall(r'href="\?dir=([^"&]+)"', roh)
                     if u and u != pfad and u.startswith(pfad)]
        else:
            unter = [pfad + u for u in re.findall(r'href="([^"/?#]+/)"', roh)
                     if u not in ('../', './')]
        warteschlange += sorted(set(unter), key=zahlen, reverse=True)

    # Je Domain nur die neueste Version. Der Ordner ueber "sysupgrade" ist die
    # Domain, alles davor die Version.
    je_domain = {}
    for pfad, url in funde.items():
        teile = [t for t in pfad.strip('/').split('/') if t and t != 'sysupgrade']
        schluessel = teile[-1] if teile else pfad
        version = teile[:-1]
        if schluessel not in je_domain or zahlen('/'.join(version)) > je_domain[schluessel][0]:
            je_domain[schluessel] = (zahlen('/'.join(version)), url)
    return {k: v[1] for k, v in je_domain.items()}


def eintrag(ordner, url, site, doms):
    vpn = site.get('mesh_vpn') or {}
    art = next((a for a in ('tunneldigger', 'fastd', 'wireguard') if a in vpn), None)
    broker, port = [], None
    if art == 'tunneldigger':
        for b in (vpn['tunneldigger'] or {}).get('brokers') or []:
            host, _, p = b.rpartition(':')
            broker.append(host or b)
            port = int(p) if p.isdigit() else port
    elif art == 'fastd':
        for g in ((vpn.get('fastd') or {}).get('groups') or {}).values():
            for peer in (g.get('peers') or {}).values():
                for r in peer.get('remotes') or []:
                    m = re.search(r'"([^"]+)"\s+port\s+(\d+)', r)
                    if m:
                        broker.append(m.group(1))
                        port = int(m.group(2))
    return {
        'code': site.get('site_code'),
        'name': site.get('site_name'),
        'ordner': ordner,
        'port': port,
        'prefix6': site.get('prefix6'),
        'prefix4': site.get('prefix4'),
        'next_node': ((site.get('next_node') or {}).get('name')
                      or (site.get('next_node') or {}).get('name6')),
        'domain_seed': site.get('domain_seed'),
        'routing_algo': ((site.get('mesh') or {}).get('batman_adv') or {}).get('routing_algo'),
        'mtu': (vpn.get(art) or {}).get('mtu') if art else None,
        'vpn': art,
        'broker': sorted(set(broker)),
        'ntp': site.get('ntp_servers'),
        'ssid': ((site.get('wifi24') or {}).get('ap') or {}).get('ssid'),
        'autoupdater': sorted(((site.get('autoupdater') or {}).get('branches') or {}).keys()),
        'spiegel': [m for b in ((site.get('autoupdater') or {}).get('branches') or {}).values()
                    for m in (b.get('mirrors') or [])],
        'weitere_domains': sorted(doms) if doms else [],
        'image': url,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('basis', nargs='?', help='Startseite des Imageservers')
    p.add_argument('--kuerzel', default='?', help='Kuerzel der Gemeinschaft, z.B. en')
    p.add_argument('--name', default='?', help='Klarname der Gemeinschaft')
    a = p.parse_args()

    if a.basis:
        gefunden = images_finden(a.basis)
        if not gefunden:
            print('Keine sysupgrade-Images gefunden. Bitte Image-URLs auf der '
                  'Standardeingabe uebergeben.', file=sys.stderr)
            return 1
    else:
        gefunden = {os.path.basename(u).split('-')[1] if '-' in u else str(i): u.strip()
                    for i, u in enumerate(sys.stdin) if u.strip()}

    domains = []
    for ordner, url in sorted(gefunden.items()):
        print(f'  {ordner}: {url}', file=sys.stderr)
        try:
            site, doms = site_json(holen(url))
        except OSError as e:
            print(f'    Fehler: {e}', file=sys.stderr)
            continue
        if not site:
            print('    keine site.json im Image', file=sys.stderr)
            continue
        domains.append(eintrag(ordner, url, site, doms))
        print(f'    {domains[-1]["code"]}  {domains[-1]["name"]}', file=sys.stderr)

    json.dump({'gemeinschaft': a.kuerzel, 'name': a.name,
               'quelle': a.basis, 'domains': domains},
              sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
