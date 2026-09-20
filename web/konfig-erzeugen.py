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
# Eine Gemeinschaft je Ebene unter map.freifunk.space, darunter ihre Orte.
# Kommt eine zweite dazu, aendert sich hier ein Wort, und der Vorgabe-Vhost
# listet sie mit auf (adorfer 20.09.2026: Platz fuer weitere Communities).
SUFFIX = 'map.freifunk.space'
EIGEN = 'map6.freifunk.space'
INDEX = '/var/www/karte-index'
KACHEL = 'https://tiles.ffdus.de'
OSM_ATTR = ('&copy; <a href="https://www.openstreetmap.org/copyright">'
            'OpenStreetMap</a>-Mitwirkende')


FELDER = ('gem', 'code', 'ordner', 'port', 'id', 'host', 'mtu', 'broker',
          'prefix6', 'prefix4', 'name')


def domains():
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if not z or z.startswith('#'):
            continue
        t = z.split(None, len(FELDER) - 1)
        if len(t) == len(FELDER):
            yield dict(zip(FELDER, t))


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


def konfig(titel, pfad, alle):
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
        'fixedCenter': rahmen(f'{WEB}/sites/{pfad}/data/meshviewer.json'),
        'siteNames': [{'site': d['code'], 'name': d['name']} for d in alle],
        'domainNames': [{'domain': d['code'], 'name': d['name']} for d in alle],
        'devicePictures': '/pictures-svg/{MODEL_NORMALIZED}.svg',
        'devicePicturesSource': ("<a href='https://github.com/freifunk/device-pictures'>"
                                 "freifunk/device-pictures</a>"),
        'devicePicturesLicense': 'CC-BY-NC-SA 4.0',
        'deprecation_enabled': False,
    }


VHOST = """
# %(titel)s
server {
	listen 80%(vorgabe)s;
	listen [::]:80%(vorgabe)s;
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


VORGABE = """
# Vorgabe: alles, was keinen eigenen Vhost hat, landet hier. Die Karte einer
# Gemeinschaft soll nicht zufaellig unter dem Namen der VM erscheinen.
server {
	listen 80 default_server;
	listen [::]:80 default_server;
	server_name %(eigen)s _;

	root %(index)s;
	index index.html;
	charset utf-8;
	add_header Cache-Control "no-cache";
}
"""


def startseite(ziele):
    zeilen = []
    for _pfad, titel, fqdn, _seine in ziele:
        zeilen.append(f'    <li><a href="https://{fqdn}/">{titel}</a> '
                      f'<span class="n">{fqdn}</span></li>')
    return """<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Karten</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 42rem;
        padding: 0 1rem; color: #222; }
 h1 { font-size: 1.3rem; }
 ul { list-style: none; padding: 0; }
 li { padding: .35rem 0; border-bottom: 1px solid #eee; }
 .n { color: #888; font-size: .85em; display: block; }
 p { color: #555; }
</style>
<h1>Freifunk-Karten</h1>
<ul>
""" + chr(10).join(zeilen) + """
</ul>
<p>Betrieben vom Freifunk im Neanderland e.V.</p>
</html>
"""


def main():
    alle = list(domains())
    if not alle:
        print(f'keine Domains in {KONF}', file=sys.stderr)
        return 1

    # Je Gemeinschaft eine Gesamtkarte und je Domain eine Ortskarte. Der Pfad
    # unter sites/ spiegelt den Namen: sites/<gem>/alle und sites/<gem>/<ort>.
    ziele = []
    for g in sorted({d['gem'] for d in alle}):
        seine = [d for d in alle if d['gem'] == g]
        # Titel der Gesamtkarte: der gemeinsame Anfang der Domainnamen, sonst
        # das Kuerzel. "Freifunk Hagen" und "Freifunk Witten" ergeben so
        # "Freifunk", nicht "EN".
        teile = [d['name'].split() for d in seine]
        gemeinsam = []
        for i in range(min(len(x) for x in teile)):
            if len({x[i] for x in teile}) == 1:
                gemeinsam.append(teile[0][i])
            else:
                break
        kopf = ' '.join(gemeinsam) or g
        ziele.append((f'{g}/alle', f'{kopf}, alle {len(seine)} Domains',
                      f'{g}.{SUFFIX}', seine))
        for d in seine:
            ziele.append((f'{g}/{d["host"]}', d['name'],
                          f'{d["host"]}.{g}.{SUFFIX}', seine))

    site = ['# Erzeugt von konfig-erzeugen.py. Nicht von Hand aendern.']
    for pfad, titel, fqdn, seine in ziele:
        verz = f'{WEB}/sites/{pfad}'
        # data/ gleich mit anlegen: yanic legt fehlende Verzeichnisse nicht
        # selbst an und schreibt dann still nichts (20.09.2026). Die Rechte
        # setzt das Einrichtungsskript danach auf yanic:www-data.
        os.makedirs(f'{verz}/data', exist_ok=True)
        with open(f'{verz}/config.json', 'w', encoding='utf-8') as f:
            json.dump(konfig(titel, pfad, seine), f, ensure_ascii=False, indent=1)
        site.append(VHOST % {'titel': titel, 'fqdn': fqdn, 'host': pfad,
                             'web': WEB, 'vorgabe': ''})
        print(f'  {fqdn:38} {titel}')

    site.append(VORGABE % {'eigen': EIGEN, 'index': INDEX})
    with open('/etc/nginx/sites-available/karte-en.conf', 'w', encoding='utf-8') as f:
        f.write('\n'.join(site) + '\n')
    print(f'\n  /etc/nginx/sites-available/karte-en.conf mit {len(ziele)} Vhosts')

    os.makedirs(INDEX, exist_ok=True)
    with open(f'{INDEX}/index.html', 'w', encoding='utf-8') as f:
        f.write(startseite(ziele))
    print(f'  {INDEX}/index.html als Vorgabe-Vhost')
    return 0


if __name__ == '__main__':
    sys.exit(main())
