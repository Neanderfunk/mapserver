#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Service-Menue der Karte: Aktionen fuer einen Knoten, hinter Anmeldung.

  service.py [--port 8097]

Erreichbar ueber das kleine Zahnrad neben dem Knotennamen im Knotenfenster der
neander-Karte (adorfer 26.09.2026), unter /nf/service/?node=<node_id>. Die
Anmeldung erledigt nginx per auth_request beim Authentik-Outpost; dieser
Dienst lauscht nur auf 127.0.0.1 und vertraut der Kopfzeile X-Service-User,
die nur nginx setzt (und eine mitgeschickte ueberschreibt).

Aktionen, beide fuehrt yanic aus (Fork Neanderfunk/yanic):

- Offline-Knoten sofort entfernen: eine leere Datei mit der node_id in
  REMOVE_DIR (nodes.remove_dir). yanic entfernt den Knoten beim naechsten
  Speichern, spaetestens nach einer Minute, und nur, wenn er offline ist.
- Koordinaten-Override: setzt in ALIASES (nodes.aliases_path, Format von
  hopglass-server) je Knoten nodeinfo.location auf einen Punkt oder auf null
  (von der Landkarte nehmen); "aufheben" nimmt es zurueck. Andere Felder
  eines Alias bleiben unberuehrt.

Jede Aktion steht mit Benutzer und Zeit in PROTOKOLL.

Schutz gegen fremde Seiten, die ein Formular hierher abschicken: POST nur
mit Origin (oder Referer) der Karte.
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

KARTE = 'https://neander.map.freifunk.space'
BASIS = '/nf/service/'
DATEN = '/var/www/karte-en/sites/neander/alle/data/meshviewer.json'
ORDNER = '/var/lib/karte/service'
ALIASES = ORDNER + '/aliases-neander.json'
REMOVE_DIR = ORDNER + '/remove-neander'
PROTOKOLL = ORDNER + '/protokoll.jsonl'

NODE_ID = re.compile(r'^[0-9a-f]{12}$')


# --- Koordinaten, tolerant gelesen (wie das Feld SNMP Location bei UniFi) ----

_ZAHL = r'(-?\d+(?:[.,]\d+)?)'
_PAAR = re.compile(r'^' + _ZAHL + r'(?:\s*[,;]\s*|\s+)' + _ZAHL + r'$')
_GOOGLE = [
    re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)'),
    re.compile(r'(?:^|[?&/])(?:q|query|ll|center)=(-?\d+\.\d+)(?:\s*[,;]\s*|\s+)(-?\d+\.\d+)'),
    re.compile(r'@(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)'),
]
_RICHTUNG = re.compile(r'^([NS])?\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*([NS])?\s*[,;]?\s*'
                       r'([EOW])?\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*([EOW])?$', re.I)


def koordinaten(text):
    """Breite, Laenge aus einer Eingabe; None, wenn nicht eindeutig lesbar."""
    if not isinstance(text, str):
        return None
    from urllib.parse import unquote
    t = unquote(text).replace('+', ' ').replace(' ', ' ').strip()
    for m in _GOOGLE:
        g = m.search(t)
        if g:
            return _pruefen(float(g.group(1)), float(g.group(2)))
    t = re.sub(r'^[^0-9A-Za-z-]+|[^0-9A-Za-z°]+$', '', t)
    m = _PAAR.match(t)
    if m and all(re.search(r'[.,]\d', z) for z in m.groups()):
        return _pruefen(*(float(z.replace(',', '.')) for z in m.groups()))
    m = _RICHTUNG.match(t)
    if m:
        ns = (m.group(1) or m.group(3) or '').upper()
        ew = (m.group(4) or m.group(6) or '').upper()
        lat, lon = float(m.group(2).replace(',', '.')), float(m.group(5).replace(',', '.'))
        if (m.group(1) and m.group(3)) or (m.group(4) and m.group(6)):
            return None
        if (ns and lat < 0) or (ew and lon < 0):
            return None
        if ns == 'S':
            lat = -lat
        if ew == 'W':
            lon = -lon
        if ns or ew:
            return _pruefen(lat, lon)
    return None


def _pruefen(lat, lon):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if abs(lat) < 0.5 and abs(lon) < 0.5:
        return None
    return round(lat, 7), round(lon, 7)


# --- Daten ---------------------------------------------------------------

def knoten(node_id, pfad=None):
    try:
        with open(pfad or DATEN, encoding='utf-8') as f:
            for n in json.load(f).get('nodes', []):
                if n.get('node_id') == node_id:
                    return n
    except (OSError, ValueError):
        pass
    return None


def aliases_lesen(pfad=None):
    try:
        with open(pfad or ALIASES, encoding='utf-8') as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def aliases_schreiben(daten, pfad=None):
    pfad = pfad or ALIASES
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(pfad), prefix='.aliases-')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.chmod(tmp, 0o644)
    os.replace(tmp, pfad)


def ort_setzen(node_id, ort, pfad=None):
    """ort: (lat, lon) setzen, None von der Landkarte nehmen, 'aufheben'."""
    daten = aliases_lesen(pfad)
    eintrag = daten.get(node_id) if isinstance(daten.get(node_id), dict) else {}
    ni = eintrag.get('nodeinfo') if isinstance(eintrag.get('nodeinfo'), dict) else {}
    if ort == 'aufheben':
        ni.pop('location', None)
    elif ort is None:
        ni['location'] = None
    else:
        ni['location'] = {'latitude': ort[0], 'longitude': ort[1]}
    if ni:
        eintrag['nodeinfo'] = ni
        daten[node_id] = eintrag
    else:
        eintrag.pop('nodeinfo', None)
        if eintrag:
            daten[node_id] = eintrag
        else:
            daten.pop(node_id, None)
    aliases_schreiben(daten, pfad)


def entfernen_beauftragen(node_id, ordner=None):
    with open(os.path.join(ordner or REMOVE_DIR, node_id), 'w'):
        pass


def protokoll(benutzer, aktion, node_id, **mehr):
    eintrag = {'zeit': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
               'benutzer': benutzer, 'aktion': aktion, 'node_id': node_id, **mehr}
    with open(PROTOKOLL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + '\n')


# --- Seite ---------------------------------------------------------------

STIL = '''
body{font-family:system-ui,sans-serif;max-width:40em;margin:1.5em auto;padding:0 1em;
color:#1c1c1c;background:#fff}
@media (prefers-color-scheme:dark){body{color:#e8e8e8;background:#1c1c1c}
input,button{color:#e8e8e8;background:#2a2a2a;border-color:#555}}
h1{font-size:1.4em}h2{font-size:1.1em;margin-top:1.6em}
table{border-collapse:collapse}td{padding:.15em .8em .15em 0;vertical-align:top}
.hinweis{padding:.6em .8em;border-left:4px solid #dc0067;margin:1em 0}
.ok{border-color:#1b9a3a}.leise{opacity:.7;font-size:.9em}
form{margin:.6em 0}input[type=text]{width:22em;max-width:100%;padding:.3em}
button{padding:.35em .8em;margin:.2em .4em .2em 0;cursor:pointer}
'''


def seite(titel, inhalt):
    return ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(titel)}</title><style>{STIL}</style></head>'
            f'<body>{inhalt}</body></html>')


def knotenseite(node_id, benutzer, meldung='', gut=False):
    e = html.escape
    n = knoten(node_id)
    if n is None:
        return seite('Service', f'<h1>Service</h1><p>Knoten <code>{e(node_id)}</code> '
                     'steht nicht (mehr) auf der Karte.</p>'
                     f'<p><a href="{KARTE}/">zur Karte</a></p>')
    alias = (aliases_lesen().get(node_id) or {}).get('nodeinfo') or {}
    online = bool(n.get('is_online'))
    loc = n.get('location') or {}
    ort = (f'{loc.get("latitude")}, {loc.get("longitude")}' if loc else 'keiner (nicht auf der Landkarte)')
    if 'location' in alias:
        override = ('von der Landkarte genommen' if alias['location'] is None else
                    f'gesetzt auf {alias["location"].get("latitude")}, {alias["location"].get("longitude")}')
    else:
        override = 'keiner'
    zeilen = [('Name', n.get('hostname', '')), ('node_id', node_id),
              ('Status', 'online' if online else 'offline'),
              ('zuletzt gesehen', n.get('lastseen', '')), ('zuerst gesehen', n.get('firstseen', '')),
              ('Domain', n.get('domain', '')), ('Ort auf der Karte', ort),
              ('Koordinaten-Override', override)]
    tab = ''.join(f'<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>' for k, v in zeilen)
    hinweis = (f'<div class="hinweis{" ok" if gut else ""}">{e(meldung)}</div>' if meldung else '')
    ziel = f'{BASIS}?node={quote(node_id)}'
    entfernen = ('<p class="leise">Der Knoten ist online und kann nicht entfernt werden.</p>'
                 if online else
                 f'<form method="post" action="{BASIS}entfernen"><input type="hidden" name="node" '
                 f'value="{e(node_id)}"><button>Jetzt aus der Karte entfernen</button></form>'
                 '<p class="leise">yanic entfernt ihn spätestens nach einer Minute. Meldet er '
                 'sich wieder, erscheint er ganz normal neu.</p>')
    inhalt = f'''
<h1>Service: {e(n.get("hostname", ""))}</h1>
<p class="leise">angemeldet als {e(benutzer)} · <a href="{KARTE}/#/de/map/{quote(node_id)}">zur Karte</a></p>
{hinweis}
<table>{tab}</table>
<h2>Offline-Knoten sofort entfernen</h2>
{entfernen}
<h2>Koordinaten-Override</h2>
<form method="post" action="{BASIS}ort">
<input type="hidden" name="node" value="{e(node_id)}">
<input type="text" name="koordinaten" placeholder="51.2506, 6.9746" autocomplete="off">
<button name="was" value="setzen">An diese Stelle rücken</button>
</form>
<p class="leise">Lesbar sind Dezimalzahlen mit Punkt oder Komma, Himmelsrichtungen und aus
Google Maps kopierte Links.</p>
<form method="post" action="{BASIS}ort">
<input type="hidden" name="node" value="{e(node_id)}">
<button name="was" value="ausblenden">Von der Landkarte nehmen</button>
<button name="was" value="aufheben">Override aufheben</button>
</form>
<p class="leise">Liste, Graph und Statistik zeigen den Knoten weiter. Wirkt spätestens nach
einer Minute; der Override gilt, bis er aufgehoben wird, auch wenn der Knoten selbst
andere Koordinaten meldet.</p>
<p class="leise"><a href="{ziel}">neu laden</a></p>'''
    return seite(f'Service: {n.get("hostname", "")}', inhalt)


# --- HTTP ----------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = 'karte-service'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (self.address_string(), fmt % args))

    def _benutzer(self):
        return (self.headers.get('X-Service-User') or '').strip()

    def _antwort(self, code, text, typ='text/html; charset=utf-8', ort=None):
        daten = text.encode('utf-8')
        self.send_response(code)
        if ort:
            self.send_header('Location', ort)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(len(daten)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(daten)

    def do_GET(self):
        benutzer = self._benutzer()
        if not benutzer:
            return self._antwort(403, 'nur ueber die Anmeldung', 'text/plain; charset=utf-8')
        url = urlparse(self.path)
        if url.path != BASIS:
            return self._antwort(404, 'nicht gefunden', 'text/plain; charset=utf-8')
        q = parse_qs(url.query)
        node_id = (q.get('node') or [''])[0].lower()
        if not NODE_ID.match(node_id):
            return self._antwort(400, seite('Service', '<h1>Service</h1><p>Kein gültiger Knoten. '
                                            'Das Service-Menü erreicht man über das Zahnrad im '
                                            f'Knotenfenster der <a href="{KARTE}/">Karte</a>.</p>'))
        meldung = (q.get('meldung') or [''])[0][:200]
        gut = (q.get('gut') or [''])[0] == '1'
        return self._antwort(200, knotenseite(node_id, benutzer, meldung, gut))

    def do_POST(self):
        benutzer = self._benutzer()
        if not benutzer:
            return self._antwort(403, 'nur ueber die Anmeldung', 'text/plain; charset=utf-8')
        herkunft = self.headers.get('Origin') or self.headers.get('Referer') or ''
        if not (herkunft == KARTE or herkunft.startswith(KARTE + '/')):
            return self._antwort(403, 'fremde Herkunft', 'text/plain; charset=utf-8')
        laenge = min(int(self.headers.get('Content-Length') or 0), 4096)
        felder = parse_qs(self.rfile.read(laenge).decode('utf-8', 'replace'))
        node_id = (felder.get('node') or [''])[0].lower()
        if not NODE_ID.match(node_id):
            return self._antwort(400, 'kein gueltiger Knoten', 'text/plain; charset=utf-8')
        pfad = urlparse(self.path).path
        if pfad == BASIS + 'entfernen':
            meldung, gut = self._entfernen(benutzer, node_id)
        elif pfad == BASIS + 'ort':
            meldung, gut = self._ort(benutzer, node_id, felder)
        else:
            return self._antwort(404, 'nicht gefunden', 'text/plain; charset=utf-8')
        ziel = f'{BASIS}?node={quote(node_id)}&meldung={quote(meldung)}&gut={"1" if gut else "0"}'
        return self._antwort(303, '', ort=ziel)

    def _entfernen(self, benutzer, node_id):
        n = knoten(node_id)
        if n is None:
            return 'Der Knoten steht nicht auf der Karte.', False
        if n.get('is_online'):
            return 'Der Knoten ist online und wird nicht entfernt.', False
        entfernen_beauftragen(node_id)
        protokoll(benutzer, 'entfernen', node_id, hostname=n.get('hostname'))
        return 'Auftrag angenommen: der Knoten verschwindet spätestens in einer Minute.', True

    def _ort(self, benutzer, node_id, felder):
        was = (felder.get('was') or [''])[0]
        if was == 'setzen':
            eingabe = (felder.get('koordinaten') or [''])[0][:300]
            ort = koordinaten(eingabe)
            if ort is None:
                return f'Nicht lesbar: "{eingabe}". Bitte Breite, Länge angeben.', False
            ort_setzen(node_id, ort)
            protokoll(benutzer, 'ort-setzen', node_id, latitude=ort[0], longitude=ort[1])
            return f'Override gesetzt auf {ort[0]}, {ort[1]}; wirkt spätestens in einer Minute.', True
        if was == 'ausblenden':
            ort_setzen(node_id, None)
            protokoll(benutzer, 'ort-ausblenden', node_id)
            return 'Der Knoten verschwindet spätestens in einer Minute von der Landkarte.', True
        if was == 'aufheben':
            ort_setzen(node_id, 'aufheben')
            protokoll(benutzer, 'ort-aufheben', node_id)
            return 'Override aufgehoben; es gilt wieder, was der Knoten meldet.', True
        return 'Unbekannte Aktion.', False


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--port', type=int, default=8097)
    a = p.parse_args()
    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
