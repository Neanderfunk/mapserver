#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Annahme der HVB-Ortung auf map6 (Prototyp): POST /hvb/locate.

Legt jede gueltige Meldung roh ab, eine Datei je Meldung unter
<ablage>/<JJJJ-MM-TT>/, nur fuer den Dienstnutzer lesbar (0600). Nach 14
Tagen raeumt locator-aufraeumen.timer sie weg. Nichts wird ausgewertet oder
weitergegeben. Antwort 202 mit {"angenommen": true, "netze": n}; der Knoten
wertet sie nicht aus.

Hinter nginx (web/nginx-locator.conf), nur an der Loopback-Adresse.
"""
import datetime
import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortung  # noqa: E402

ABLAGE = os.environ.get('LOCATOR_ABLAGE', '/var/lib/locator/eingang')
ADRESSE = os.environ.get('LOCATOR_ADRESSE', '127.0.0.1')
PORT = int(os.environ.get('LOCATOR_PORT', '8781'))


def ablegen(meldung, xff, ua):
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    ordner = os.path.join(ABLAGE, jetzt.strftime('%Y-%m-%d'))
    os.makedirs(ordner, mode=0o700, exist_ok=True)
    name = '%s-%s-%s.json' % (jetzt.strftime('%H%M%S'), meldung['node_id'], secrets.token_hex(3))
    inhalt = {'empfangen': jetzt.isoformat(timespec='seconds'),
              'x_forwarded_for': xff, 'user_agent': ua, 'meldung': meldung}
    fd = os.open(os.path.join(ordner, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(inhalt, f, ensure_ascii=False)


class Annahme(BaseHTTPRequestHandler):
    server_version = 'locator'
    sys_version = ''

    def antwort(self, status, daten):
        body = json.dumps(daten).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/hvb/locate':
            return self.antwort(404, {'fehler': 'unbekannter Pfad'})
        try:
            laenge = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.antwort(411, {'fehler': 'Content-Length fehlt'})
        if laenge > ortung.MAX_BYTES:
            return self.antwort(413, {'fehler': 'zu gross'})
        try:
            meldung = json.loads(self.rfile.read(laenge))
            netze = ortung.pruefen(meldung)
        except (ValueError, ortung.Ungueltig) as e:
            return self.antwort(400, {'fehler': str(e)[:200]})
        ablegen(meldung, self.headers.get('X-Forwarded-For', ''), self.headers.get('User-Agent', ''))
        self.antwort(202, {'angenommen': True, 'netze': netze})

    def log_message(self, *a):
        # nginx loggt schon (ohne Inhalt); hier nichts doppelt
        pass


if __name__ == '__main__':
    ThreadingHTTPServer((ADRESSE, PORT), Annahme).serve_forever()
