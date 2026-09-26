#!/usr/bin/env python3
"""Tests fuer service.py:  python3 -m pytest service/"""
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

spec = importlib.util.spec_from_file_location('service', os.path.join(os.path.dirname(__file__), 'service.py'))
svc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc)


@pytest.mark.parametrize('text,erwartet', [
    ('51.2506, 6.9746', (51.2506, 6.9746)),
    ('51,2506 6,9746', (51.2506, 6.9746)),
    ('  ?51.2506;6.9746& ', (51.2506, 6.9746)),
    ('51.2506 N, 6.9746 E', (51.2506, 6.9746)),
    ('6.9746 E 51.2506 N', None),          # vertauscht nur mit Richtung vorn/hinten je Zahl
    ('https://www.google.com/maps/@51.2506,6.9746,17z', (51.2506, 6.9746)),
    ('https://maps.google.com/?q=51.2506,6.9746', (51.2506, 6.9746)),
    ('0, 0', None), ('51, 6', None), ('Mettmann', None), ('', None), (None, None),
    ('51.2 S, 6.9 W', (-51.2, -6.9)), ('-51.2 S, 6.9', None),
])
def test_koordinaten(text, erwartet):
    assert svc.koordinaten(text) == erwartet


def test_ort_setzen_und_aufheben_laesst_anderes_stehen(tmp_path):
    p = str(tmp_path / 'a.json')
    json.dump({'aaaaaaaaaaaa': {'nodeinfo': {'hostname': 'x'}}}, open(p, 'w'))
    svc.ort_setzen('aaaaaaaaaaaa', (51.0, 7.0), p)
    assert json.load(open(p))['aaaaaaaaaaaa']['nodeinfo'] == {
        'hostname': 'x', 'location': {'latitude': 51.0, 'longitude': 7.0}}
    svc.ort_setzen('aaaaaaaaaaaa', None, p)
    assert json.load(open(p))['aaaaaaaaaaaa']['nodeinfo']['location'] is None
    svc.ort_setzen('aaaaaaaaaaaa', 'aufheben', p)
    assert json.load(open(p))['aaaaaaaaaaaa']['nodeinfo'] == {'hostname': 'x'}
    svc.ort_setzen('bbbbbbbbbbbb', (51.0, 7.0), p)
    svc.ort_setzen('bbbbbbbbbbbb', 'aufheben', p)
    assert 'bbbbbbbbbbbb' not in json.load(open(p))
    assert oct(os.stat(p).st_mode & 0o777) == '0o644'


@pytest.fixture
def server(tmp_path, monkeypatch):
    daten = tmp_path / 'meshviewer.json'
    daten.write_text(json.dumps({'nodes': [
        {'node_id': 'aaaaaaaaaaaa', 'hostname': 'weg', 'is_online': False, 'lastseen': 'x'},
        {'node_id': 'bbbbbbbbbbbb', 'hostname': 'da', 'is_online': True,
         'location': {'latitude': 1.0, 'longitude': 2.0}},
    ]}))
    (tmp_path / 'remove').mkdir()
    monkeypatch.setattr(svc, 'DATEN', str(daten))
    monkeypatch.setattr(svc, 'ALIASES', str(tmp_path / 'aliases.json'))
    monkeypatch.setattr(svc, 'REMOVE_DIR', str(tmp_path / 'remove'))
    monkeypatch.setattr(svc, 'PROTOKOLL', str(tmp_path / 'protokoll.jsonl'))
    s = ThreadingHTTPServer(('127.0.0.1', 0), svc.Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{s.server_address[1]}', tmp_path
    s.shutdown()



class KeinUmleiten(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def anfrage(url, daten=None, kopf=None):
    r = urllib.request.Request(url, data=daten.encode() if daten else None, headers=kopf or {})
    try:
        with urllib.request.build_opener(KeinUmleiten).open(r) as a:
            return a.status, a.read().decode(), dict(a.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


ANGEMELDET = {'X-Service-User': 'adorfer', 'Origin': svc.KARTE}


def test_ohne_anmeldung_nichts(server):
    url, _ = server
    assert anfrage(url + '/nf/service/?node=aaaaaaaaaaaa')[0] == 403
    assert anfrage(url + '/nf/service/entfernen', 'node=aaaaaaaaaaaa', {'Origin': svc.KARTE})[0] == 403


def test_fremde_herkunft(server):
    url, tmp = server
    code, _, _ = anfrage(url + '/nf/service/entfernen', 'node=aaaaaaaaaaaa',
                         {'X-Service-User': 'a', 'Origin': 'https://boese.example'})
    assert code == 403
    assert os.listdir(tmp / 'remove') == []


def test_seite_zeigt_knoten(server):
    url, _ = server
    code, text, _ = anfrage(url + '/nf/service/?node=aaaaaaaaaaaa', kopf={'X-Service-User': 'adorfer'})
    assert code == 200 and 'weg' in text and 'Jetzt aus der Karte entfernen' in text
    code, text, _ = anfrage(url + '/nf/service/?node=bbbbbbbbbbbb', kopf={'X-Service-User': 'adorfer'})
    assert 'ist online und kann nicht entfernt werden' in text
    assert anfrage(url + '/nf/service/?node=<script>', kopf={'X-Service-User': 'a'})[0] == 400


def test_entfernen_nur_offline(server):
    url, tmp = server
    code, _, kopf = anfrage(url + '/nf/service/entfernen', 'node=aaaaaaaaaaaa', ANGEMELDET)
    assert code == 303 and 'warte=1' in kopf['Location']
    assert os.listdir(tmp / 'remove') == ['aaaaaaaaaaaa']
    code, _, kopf = anfrage(url + '/nf/service/entfernen', 'node=bbbbbbbbbbbb', ANGEMELDET)
    assert 'gut=0' in kopf['Location']
    assert os.listdir(tmp / 'remove') == ['aaaaaaaaaaaa']
    zeilen = [json.loads(z) for z in open(tmp / 'protokoll.jsonl')]
    assert zeilen[0]['benutzer'] == 'adorfer' and zeilen[0]['aktion'] == 'entfernen'


def test_ort_override(server):
    url, tmp = server
    anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=setzen&koordinaten=51%2C2506+6%2C9746', ANGEMELDET)
    assert json.load(open(tmp / 'aliases.json'))['bbbbbbbbbbbb']['nodeinfo']['location'] == \
        {'latitude': 51.2506, 'longitude': 6.9746}
    code, _, kopf = anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=setzen&koordinaten=Mettmann', ANGEMELDET)
    assert 'gut=0' in kopf['Location']
    anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=ausblenden', ANGEMELDET)
    assert json.load(open(tmp / 'aliases.json'))['bbbbbbbbbbbb']['nodeinfo']['location'] is None
    anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=aufheben', ANGEMELDET)
    assert json.load(open(tmp / 'aliases.json')) == {}


def test_rueckmeldung_nach_dem_loeschen(server):
    url, tmp = server
    anfrage(url + '/nf/service/entfernen', 'node=aaaaaaaaaaaa', ANGEMELDET)
    kopf = {'X-Service-User': 'adorfer'}
    # Auftrag liegt: Hinweis, Knopf weg, Seite laedt sich neu
    code, text, _ = anfrage(url + '/nf/service/?node=aaaaaaaaaaaa&warte=1', kopf=kopf)
    assert 'Löschung erfolgt' in text and 'http-equiv="refresh"' in text
    assert 'Jetzt aus der Karte entfernen' not in text
    # auch ohne warte, solange der Auftrag liegt
    assert 'Löschung erfolgt' in anfrage(url + '/nf/service/?node=aaaaaaaaaaaa', kopf=kopf)[1]
    # yanic hat erledigt, Karte noch alt: weiter warten
    os.remove(tmp / 'remove' / 'aaaaaaaaaaaa')
    assert 'Löschung erfolgt' in anfrage(url + '/nf/service/?node=aaaaaaaaaaaa&warte=1', kopf=kopf)[1]
    # Karte neu geschrieben, Knoten weg
    d = json.load(open(tmp / 'meshviewer.json'))
    d['nodes'] = [n for n in d['nodes'] if n['node_id'] != 'aaaaaaaaaaaa']
    json.dump(d, open(tmp / 'meshviewer.json', 'w'))
    code, text, _ = anfrage(url + '/nf/service/?node=aaaaaaaaaaaa&warte=1', kopf=kopf)
    assert 'ist entfernt' in text and 'refresh' not in text


def test_rueckmeldung_wenn_er_wiederkommt(server):
    url, _ = server
    code, text, _ = anfrage(url + '/nf/service/?node=bbbbbbbbbbbb&warte=1', kopf={'X-Service-User': 'a'})
    assert 'wieder gemeldet' in text and 'refresh' not in text


def test_verlauf_auf_der_seite(server):
    url, _ = server
    anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=setzen&koordinaten=51.25+6.97', ANGEMELDET)
    anfrage(url + '/nf/service/ort', 'node=bbbbbbbbbbbb&was=aufheben', ANGEMELDET)
    text = anfrage(url + '/nf/service/?node=bbbbbbbbbbbb', kopf={'X-Service-User': 'adorfer'})[1]
    assert 'Verlauf' in text
    assert text.index('Override aufgehoben') < text.index('Ort gesetzt (51.25, 6.97)')
    assert 'adorfer' in text
