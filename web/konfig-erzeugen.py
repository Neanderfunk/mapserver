#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt aus der Domaintabelle die neun meshviewer-Konfigurationen und die
nginx-Site.

Ein gemeinsamer meshviewer-Build wird neunmal ausgeliefert, jeder Vhost
bekommt nur seine eigene config.json und sein eigenes data/. Das spart neun
Kopien desselben Javascript.

Kacheln kommen vom Cache in Duesseldorf, nicht direkt von OSM oder CARTO:
sonst erfuehre ein fremder Server die Adresse jeder Besucherin. Geraetebilder
liefern wir ebenfalls selbst aus statt von github.io.
"""
import json
import os
import sys

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en'
BASIS = 'en.map.freifunk.space'
KACHEL = 'https://tiles.ffdus.de'
OSM_ATTR = ('&copy; <a href="https://www.openstreetmap.org/copyright">'
            'OpenStreetMap</a>-Mitwirkende')


def domains():
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if not z or z.startswith('#'):
            continue
        t = z.split(None, 7)
        if len(t) >= 8:
            yield {'code': t[0], 'host': t[4], 'name': t[7]}


def rahmen(datei, rand=0.02):
    """Eckpunkte aus den vorhandenen Knotenkoordinaten, sonst das EN-Gebiet."""
    vorgabe = [[51.52, 7.05], [51.20, 7.55]]
    try:
        with open(datei, encoding='utf-8') as f:
            knoten = json.load(f).get('nodes', [])
    except (OSError, ValueError):
        return vorgabe
    orte = [k['location'] for k in knoten if k.get('location')]
    lat = [o['latitude'] for o in orte if -90 < o.get('latitude', 0) < 90]
    lon = [o['longitude'] for o in orte if -180 < o.get('longitude', 0) < 180]
    if len(lat) < 3:
        return vorgabe
    return [[round(max(lat) + rand, 4), round(min(lon) - rand, 4)],
            [round(min(lat) - rand, 4), round(max(lon) + rand, 4)]]


def konfig(titel, host, alle):
    return {
        'dataPath': ['./data/'],
        'siteName': titel,
        'maxAge': 21,
        'nodeZoom': 19,
        'mapLayers': [
            {'name': 'OpenStreetMap (deutsch)',
             'url': KACHEL + '/tile.openstreetmap.de/tiles/osmde/{z}/{x}/{y}.png',
             'config': {'type': 'osm', 'maxZoom': 19, 'start': 6,
                        'attribution': OSM_ATTR + ', Kacheln: <a href="https://www.openstreetmap.de/">OpenStreetMap Deutschland</a>'}},
            {'name': 'CARTO hell',
             'url': KACHEL + '/carto/light_all/{z}/{x}/{y}.png',
             'config': {'maxZoom': 19, 'start': 6,
                        'attribution': OSM_ATTR + ', &copy; <a href="https://carto.com/attributions">CARTO</a>'}},
        ],
        'fixedCenter': rahmen(f'{WEB}/sites/{host}/data/meshviewer.json'),
        'siteNames': [{'site': d['code'], 'name': d['name']} for d in alle],
        'devicePictures': '/pictures-svg/{MODEL_NORMALIZED}.svg',
        'devicePicturesSource': ("<a href='https://github.com/freifunk/device-pictures'>"
                                 "freifunk/device-pictures</a>"),
        'devicePicturesLicense': 'CC-BY-NC-SA 4.0',
        'deprecation_enabled': False,
    }


VHOST = """
# %(titel)s
server {
	listen 80;
	listen [::]:80;
	server_name %(fqdn)s;

	root %(web)s/meshviewer;
	index index.html;
	charset utf-8;

	access_log /var/log/nginx/karte-en.access.log;
	error_log  /var/log/nginx/karte-en.error.log;

	# Eigene Konfiguration und eigene Daten je Vhost, gemeinsamer Build.
	location = /config.json {
		alias %(web)s/sites/%(host)s/config.json;
		add_header Cache-Control "no-cache";
	}
	location /data/ {
		alias %(web)s/sites/%(host)s/data/;
		add_header Cache-Control "no-cache";
	}
	location /pictures-svg/ {
		alias %(web)s/pictures-svg/;
		expires 30d;
	}
	location /assets/ {
		expires 30d;
	}
	location / {
		try_files $uri $uri/ /index.html;
		add_header Cache-Control "no-cache";
	}
}
"""


def main():
    alle = list(domains())
    if not alle:
        print(f'keine Domains in {KONF}', file=sys.stderr)
        return 1
    ziele = [('alle', f'Freifunk EN, alle {len(alle)} Domains')]
    ziele += [(d['host'], d['name']) for d in alle]

    site = ['# Erzeugt von konfig-erzeugen.py. Nicht von Hand aendern.']
    for host, titel in ziele:
        verz = f'{WEB}/sites/{host}'
        os.makedirs(verz, exist_ok=True)
        with open(f'{verz}/config.json', 'w', encoding='utf-8') as f:
            json.dump(konfig(titel, host, alle), f, ensure_ascii=False, indent=1)
        fqdn = BASIS if host == 'alle' else f'{host}.{BASIS}'
        site.append(VHOST % {'titel': titel, 'fqdn': fqdn, 'host': host, 'web': WEB})
        print(f'  {fqdn:38} {titel}')

    with open('/etc/nginx/sites-available/karte-en.conf', 'w', encoding='utf-8') as f:
        f.write('\n'.join(site) + '\n')
    print(f'\n  /etc/nginx/sites-available/karte-en.conf mit {len(ziele)} Vhosts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
