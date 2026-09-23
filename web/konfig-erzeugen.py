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
# Eine Community je Ebene unter map.freifunk.space, darunter ihre Orte.
# Kommt eine zweite dazu, aendert sich hier ein Wort, und der Vorgabe-Vhost
# listet sie mit auf (adorfer 20.09.2026: Platz fuer weitere Communities).
SUFFIX = 'map.freifunk.space'
# Klarname je Community, fuer den Titel der Gesamtkarte.
NAMEN = {'en': 'Freifunk EN', 'neander': 'Neanderfunk'}
EIGEN = 'map6.freifunk.space'
INDEX = '/var/www/karte-index'
KACHEL = 'https://tiles.ffdus.de'
OSM_ATTR = ('&copy; <a href="https://www.openstreetmap.org/copyright">'
            'OpenStreetMap</a>-Mitwirkende')


FELDER = ('community', 'code', 'ordner', 'port', 'id', 'host', 'mtu', 'broker',
          'prefix6', 'prefix4', 'name')


def domains():
    for z in open(KONF, encoding='utf-8'):
        z = z.strip()
        if not z or z.startswith('#'):
            continue
        t = z.split(None, len(FELDER) - 1)
        if len(t) == len(FELDER):
            yield dict(zip(FELDER, t))


STANDBY_KONF = '/etc/karte-en/standby.conf'


def standby():
    """Community -> Umleitungsziel, fuer Communities, die wir nicht mehr messen."""
    z = {}
    try:
        for zeile in open(STANDBY_KONF, encoding='utf-8'):
            zeile = zeile.strip()
            if zeile and not zeile.startswith('#'):
                t = zeile.split(None, 2)
                if len(t) >= 2:
                    z[t[0]] = t[1]
    except OSError:
        pass
    return z


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


# Geraete mit 4 MB Flash und 32 MB RAM. Sie laufen bei uns auf den
# _EOL-Domains, das ist die verlaessliche Quelle: was dort steht, hat unsere
# Firmware selbst als Altgeraet einsortiert. Die Liste unten ist nur der
# Anfangsbestand vom 22.09.2026, damit die Warnung auch dann steht, wenn
# gerade kein Geraet eines Typs online ist; altgeraete() ergaenzt sie um das,
# was in den Daten wirklich auftaucht.
#
# meshviewer bringt eine eigene Liste mit (config_default.ts, eol), die 18
# unserer 19 Modelle kennt, aber nicht "Ubiquiti UniFi". Unsere eigenen Daten
# sind genauer als eine gepflegte Fremdliste.
ALTGERAETE = [
    'TP-Link TL-WA801N/ND v2', 'TP-Link TL-WA850RE v1', 'TP-Link TL-WA860RE v1',
    'TP-Link TL-WA901N/ND v3', 'TP-Link TL-WR1043N/ND v1',
    'TP-Link TL-WR740N/ND v4', 'TP-Link TL-WR741N/ND v1',
    'TP-Link TL-WR741N/ND v4', 'TP-Link TL-WR841N/ND v8',
    'TP-Link TL-WR841N/ND v9', 'TP-Link TL-WR841N/ND v10',
    'TP-Link TL-WR841N/ND v11', 'TP-Link TL-WR940N v4', 'TP-Link TL-WR940N v6',
    'TP-Link TL-WR941N/ND v6', 'Ubiquiti NanoStation M2',
    'Ubiquiti NanoStation loco M2', 'Ubiquiti PicoStation M2', 'Ubiquiti UniFi',
]

# Steht im Infofenster eines solchen Knotens. Vorerst nur ein Hinweis mit
# Link, keine Abschaltung (adorfer 23.09.2026).
ALTGERAETE_TEXT = (
    'Dieses Gerät hat nur 4 MB Flash und 32 MB RAM. Es bekommt keine neuen '
    'Funktionen mehr und sollte ersetzt werden. '
    '<a href="https://neanderfunk.de/freifunk-router-austausch-aktion/" '
    'target="_blank" rel="noopener">Zur Router-Austauschaktion</a>'
)


# Zeitreihen im Knotenfenster. meshviewer zeichnet sie selbst mit d3 als SVG
# im Browser; kein iframe, kein PNG aus einem Grafana. Upstream holt die Daten
# ueber die Grafana-API, unser Patch patches/meshviewer-chart.patch kann sie
# auch direkt aus einer Prometheus-API lesen, also aus unserem
# VictoriaMetrics. Damit brauchen wir kein Grafana als Uebersetzer.
#
# $node ersetzt meshviewer durch die node_id.
# Eigenheiten der Abfragesprache, beide gemessen am 23.09.2026:
#   - keine Backslash-Escapes in den Namensmustern, der Punkt darf hier fuer
#     sich stehen
#   - rate() wirft den Metriknamen weg, danach sind rx und tx nicht mehr
#     unterscheidbar ("duplicate output timeseries"); keep_metric_names haelt
#     ihn fest, das ist eine Erweiterung von VictoriaMetrics
ZEITREIHE_URL = 'https://neander.map.freifunk.space/nf/prom'

# Alle Abfragen fassen zusammen (max by / sum by): yanic haengt Labels wie die
# Frequenz oder die Firmwareversion an jeden Punkt, und jede Aenderung daran
# waere sonst eine neue Reihe mit eigener Farbe und eigenem Eintrag in der
# Legende. Bei einem Knoten, der mehrfach neu startet, wird daraus eine sehr
# lange Legende (adorfer 23.09.2026).
DIAGRAMME = [
    {'name': 'Clients',
     'query': 'max(last_over_time({__name__="node_clients.total", nodeid="$node"}[10m]))',
     'legendFormat': 'Clients', 'format': ',.0f', 'integer': True},
    {'name': 'Bandbreite',
     'query': 'sum by (richtung) (label_replace('
              'rate({__name__=~"node_traffic.(rx|tx).bytes", nodeid="$node"}[15m])'
              ' keep_metric_names, "richtung", "$1", "__name__",'
              ' "node_traffic.(rx|tx).bytes")) * 8',
     'legendFormat': '{{richtung}}', 'unitSuffix': 'bit/s', 'format': '.2~s',
     # Senden nach unten, Empfangen nach oben
     'series': [{'name': 'tx', 'negate': True}]},
    {'name': 'Airtime',
     'query': 'max by (band) (label_replace('
              '{__name__=~"node_airtime11(g|a).chan_util", nodeid="$node"},'
              ' "band", "$1", "__name__", "node_airtime11(g|a).chan_util"))',
     'legendFormat': '{{band}}', 'unitSuffix': '%', 'format': '.0f', 'integer': True},
    {'name': 'Ausfälle laut Knoten',
     # Zaehler des SSID-Changers seit dem letzten Start: wie oft der Knoten
     # sich selbst als offline gesehen hat. Der Wert ueberlebt den Ausfall,
     # weil er danach hoeher dasteht; der Knoten selbst kann waehrenddessen
     # nichts melden (adorfer 23.09.2026). Nur Knoten mit dem Paket
     # neanderfunk-respondd.
     'query': 'max by (was) (label_replace('
              '{__name__=~"node_nf.ssid_changer.(offline|gateway_losses|switches)",'
              ' nodeid="$node"}, "was", "$1", "__name__",'
              ' "node_nf.ssid_changer.(offline|gateway_losses|switches)"))',
     'legendFormat': '{{was}}', 'format': ',.0f', 'integer': True},
    {'name': 'Laufzeit',
     'query': 'max({__name__="node_time.up", nodeid="$node"}) / 86400',
     'legendFormat': 'Tage', 'unitSuffix': ' d', 'format': '.1f'},
    {'name': 'Freier Speicher',
     'query': 'max({__name__="node_memory.available", nodeid="$node"}) * 1024',
     'legendFormat': 'verfügbar', 'unitSuffix': 'B', 'format': '.2~s'},
]


# Waehlbare Zeitraeume ueber den Diagrammen. 400 Tage haelt die Datenbank,
# ein Jahr ist also die sinnvolle Obergrenze.
ZEITRAEUME = [
    {'name': '24 h', 'from': 'now-24h'},
    {'name': '7 Tage', 'from': 'now-7d'},
    {'name': '30 Tage', 'from': 'now-30d'},
    {'name': '1 Jahr', 'from': 'now-1y'},
]


# Vertiefung hinter einem Link: ein Grafana auf derselben Maschine, mit
# denselben Zeitreihen. Dort gibt es Tagesbilanzen als Balken, freie
# Zeitraeume und die Werte aus neanderfunk-respondd. meshviewer setzt
# {NODE_ID} ein; ohne "image" wird daraus ein reiner Textlink, also kein
# iframe und kein gerendertes Bild.
VERTIEFUNG = [{
    'name': 'Grafana',
    'title': 'Ausführliche Statistik (Grafana)',
    'href': 'https://neander.map.freifunk.space/grafana/d/nf-knoten/knoten'
            '?var-node={NODE_ID}&from=now-30d&to=now',
}]


def diagramme():
    return [dict(d, datasourceType='prometheus-direct', datasourceUid='vm',
                 **{'from': 'now-7d', 'to': 'now', 'maxDataPoints': 300})
            for d in DIAGRAMME]


def altgeraete(datei):
    """Modelle, die in den Daten auf einer _EOL-Domain stehen."""
    gefunden = set(ALTGERAETE)
    try:
        with open(datei, encoding='utf-8') as f:
            for k in json.load(f).get('nodes', []):
                if (k.get('domain') or '').endswith('_EOL') and k.get('model'):
                    gefunden.add(k['model'])
    except (OSError, ValueError):
        pass
    return sorted(gefunden)


def konfig(titel, pfad, alle):
    community = pfad.split('/')[0]
    daten = f'{WEB}/sites/{pfad}/data/meshviewer.json'
    # Nur in der eigenen Community warnen. Wessen Geraet bei Freifunk EN zu
    # klein ist, entscheiden die selbst, und unsere Austauschaktion gilt dort
    # nicht.
    # Bis 23.09.2026 stand am Ende dieser Konfiguration ein pauschales
    # deprecation_enabled False. Es kam nach dieser Stelle und hat den Hinweis
    # ueberall abgeschaltet, auch dort, wo die Liste gesetzt war.
    alt = ({'deprecation_enabled': True,
            'eol': altgeraete(daten), 'eol_text': ALTGERAETE_TEXT,
            'prometheus': {'url': ZEITREIHE_URL}, 'nodeCharts': diagramme(),
            'chartRanges': ZEITRAEUME, 'nodeInfos': VERTIEFUNG}
           if community == 'neander' else {'deprecation_enabled': False})
    return {
        **alt,
        'dataPath': ['./data/'],
        'siteName': titel,
        'maxAge': 21,
        # Beschriftung der Knoten. Im Dunkelmodus nimmt meshviewer sonst die
        # Farben des Seitenkoerpers: helle Schrift mit dunklem Saum. Unsere
        # Grundkarte bleibt dabei hell (CARTO wird nicht umgedreht), und das
        # ist dann unlesbar. Deshalb fest dunkle Schrift auf weissem Saum,
        # in beiden Modi. Braucht patches/meshviewer-label.patch.
        'map': {
            'labelShadowColor': 'rgba(255, 255, 255, 0.85)',
            'labelColor': '#1c1c1c',
            # etwa eine Leerzeichenbreite mehr Luft zum Knotenpunkt
            'labelOffset': 4,
        },
        'nodeZoom': 19,
        # Reihenfolge entscheidet: meshviewer nimmt die erste Ebene als
        # Vorgabe (lib/map.ts sortiert nach config.order, das ohne start/end
        # dem Listenindex entspricht). CARTO steht deshalb vorn und hat
        # bewusst kein "start", sonst haengt die Vorgabe an der Tageszeit
        # (adorfer 20.09.2026).
        'mapLayers': [
            {'name': 'CARTO hell',
             'url': KACHEL + '/carto/light_all/{z}/{x}/{y}.png',
             'config': {'maxZoom': 19, 'className': 'karte-dunkel',
                        'attribution': OSM_ATTR + ', &copy; <a href="https://carto.com/attributions">CARTO</a>'}},
            {'name': 'OpenStreetMap (deutsch, blass)',
             'url': KACHEL + '/tile.openstreetmap.de/tiles/osmde/{z}/{x}/{y}.png',
             # className landet auf der Kachelebene; die Regeln dazu stehen in
             # web/eigenes.css und werden beim Bau in die index.html
             # eingefuegt. karte-dunkel wirkt nur im Dunkelmodus und macht
             # aus denselben Kacheln eine dunkle Karte.
             'config': {'type': 'osm', 'maxZoom': 19, 'className': 'entsaettigt karte-dunkel',
                        'attribution': OSM_ATTR + ', Kacheln: <a href="https://www.openstreetmap.de/">OpenStreetMap Deutschland</a>'}},
        ],
        'fixedCenter': rahmen(daten),
        'siteNames': [{'site': d['code'], 'name': d['name']} for d in alle],
        'domainNames': [{'domain': d['code'], 'name': d['name']} for d in alle],
        'devicePictures': '/pictures-svg/{MODEL_NORMALIZED}.svg',
        'devicePicturesSource': ("<a href='https://github.com/freifunk/device-pictures'>"
                                 "freifunk/device-pictures</a>"),
        'devicePicturesLicense': 'CC-BY-NC-SA 4.0',
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
%(api)s	location / {
		try_files $uri $uri/ /index.html;
		add_header Cache-Control "no-cache";
	}
}
"""


# Nur auf der Gesamtkarte einer Community: maschinenlesbare Auszuege fuer
# Sammler ausserhalb, etwa das Adressbuch node_id -> Adressen
# (sammler/adressbuch.py). Lesend, ohne Anmeldung, dieselben Daten wie die Karte.
API = """	location /nf/ {
		alias %(web)s/api/%(community)s/;
		default_type application/json;
		add_header Cache-Control "no-cache";
		add_header Access-Control-Allow-Origin "*";
	}
	# Zeitreihen, falls fuer diese Community eingerichtet (zeitreihe/). Das
	# Muster mit Stern macht das include optional.
	include /etc/nginx/karte-en/prom-%(community)s*.conf;
"""


UMLEITUNG = """
# %(titel)s: Standby, %(grund)s
server {
	listen 80;
	listen [::]:80;
	server_name %(fqdn)s;

	access_log /var/log/nginx/karte-en.access.log;

	# Dauerhaft, nicht nur fuer diesen Aufruf: wir messen dieses Netz nicht
	# mehr. Wer die Karte verlinkt hat, soll bei der Community landen.
	location / {
		return 301 %(ziel)s;
	}
}
"""


VORGABE = """
# Vorgabe: alles, was keinen eigenen Vhost hat, landet hier. Die Karte einer
# Community soll nicht zufaellig unter dem Namen der VM erscheinen.
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

    # Je Community eine Gesamtkarte und je Domain eine Ortskarte. Der Pfad
    # unter sites/ spiegelt den Namen: sites/<community>/alle und sites/<community>/<ort>.
    ziele = []
    for g in sorted({d['community'] for d in alle}):
        seine = [d for d in alle if d['community'] == g]
        # Titel der Gesamtkarte. Wie eine Community heissen will, laesst
        # sich aus den Domainnamen nicht ableiten: "Freifunk Hagen" und
        # "Freifunk Witten" ergaeben "Freifunk", nicht "Freifunk EN".
        kopf = NAMEN.get(g, g)
        ziele.append((f'{g}/alle', f'{kopf}, alle {len(seine)} Domains',
                      f'{g}.{SUFFIX}', seine))
        for d in seine:
            ziele.append((f'{g}/{d["host"]}', d['name'],
                          f'{d["host"]}.{g}.{SUFFIX}', seine))

    ruht = standby()
    site = ['# Erzeugt von konfig-erzeugen.py. Nicht von Hand aendern.']
    for pfad, titel, fqdn, seine in ziele:
        g, _, ort = pfad.partition('/')
        # Community im Standby: nur eine Umleitung, keine Karte. Die Daten
        # unter sites/ bleiben liegen, eine Zeile weniger in standby.conf
        # holt alles zurueck.
        if g in ruht:
            site.append(UMLEITUNG % {'titel': titel, 'fqdn': fqdn,
                                     'ziel': ruht[g], 'grund': f'Umleitung auf {ruht[g]}'})
            print(f'  {fqdn:38} -> {ruht[g]}')
            continue
        verz = f'{WEB}/sites/{pfad}'
        # data/ gleich mit anlegen: yanic legt fehlende Verzeichnisse nicht
        # selbst an und schreibt dann still nichts (20.09.2026). Die Rechte
        # setzt das Einrichtungsskript danach auf yanic:www-data.
        os.makedirs(f'{verz}/data', exist_ok=True)
        with open(f'{verz}/config.json', 'w', encoding='utf-8') as f:
            json.dump(konfig(titel, pfad, seine), f, ensure_ascii=False, indent=1)
        api = API % {'web': WEB, 'community': g} if ort == 'alle' else ''
        site.append(VHOST % {'titel': titel, 'fqdn': fqdn, 'host': pfad,
                             'web': WEB, 'vorgabe': '', 'api': api})
        print(f'  {fqdn:38} {titel}')

    site.append(VORGABE % {'eigen': EIGEN, 'index': INDEX})
    with open('/etc/nginx/sites-available/karte-en.conf', 'w', encoding='utf-8') as f:
        f.write('\n'.join(site) + '\n')
    print(f'\n  /etc/nginx/sites-available/karte-en.conf mit {len(ziele)} Vhosts')

    os.makedirs(INDEX, exist_ok=True)
    with open(f'{INDEX}/index.html', 'w', encoding='utf-8') as f:
        f.write(startseite([z for z in ziele if z[0].split('/')[0] not in ruht]))
    print(f'  {INDEX}/index.html als Vorgabe-Vhost')
    return 0


if __name__ == '__main__':
    sys.exit(main())
