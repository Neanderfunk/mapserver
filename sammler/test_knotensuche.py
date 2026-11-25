#!/usr/bin/env python3
"""Tests fuer knotensuche.py:  python3 -m pytest sammler/test_knotensuche.py"""
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

spec = importlib.util.spec_from_file_location('ks', os.path.join(os.path.dirname(__file__), 'knotensuche.py'))
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)

# Erfundene Knoten, MACs aus dem lokal verwalteten Bereich
ZIELE = {'community': 'neander', 'generated': '2026-11-25T08:00:00Z', 'source': 'test', 'nodes': {
    '02aabb000001': {'hostname': 'eins', 'site_code': 'nef-10_wlf', 'domain': '10_wlf', 'online': True,
                     'last_seen': '2026-11-25T07:59:00Z',
                     'addresses': ['2001:db8:1:715:aa:bbff:fe00:1', 'fd00:1::aa:bbff:fe00:1']},
    '02aabb000002': {'hostname': 'zwei', 'site_code': 'nef-21_dias', 'domain': '21_dias', 'online': False,
                     'last_seen': '2026-11-20T10:00:00Z', 'addresses': []},
    '02aabb0000aa': {'hostname': 'supernode', 'domain': '10_wlf', 'online': True,
                     'last_seen': '2026-11-25T07:59:00Z', 'addresses': ['2001:db8:1:715::1']},
}}


@pytest.fixture
def bestand(tmp_path):
    (tmp_path / 'neander').mkdir()
    (tmp_path / 'neander' / 'targets.json').write_text(json.dumps(ZIELE))
    return ks.Bestand(str(tmp_path))


@pytest.mark.parametrize('text,erwartet', [
    ('02:aa:bb:00:00:01', '02aabb000001'),
    ('02-AA-BB-00-00-01', '02aabb000001'),
    ('02aa.bb00.0001', '02aabb000001'),
    (' 02AABB000001 ', '02aabb000001'),
    ('02:aa:bb:00:00', None),
    ('zz:aa:bb:00:00:01', None),
])
def test_hex12(text, erwartet):
    assert ks.hex12(text) == erwartet


@pytest.mark.parametrize('text,ok', [
    ('2001:db8:1:315:aa:bbff:fe00:1', True),
    ('[2001:db8:1:315:aa:bbff:fe00:1]', True),
    ('fe80::aa:bbff:fe00:1%bat-10_wlf', True),
    ('2001:db8:1:315:aa:bbff:fe00:1/64', True),
    ('10.10.0.1', False),
    ('kein', False),
])
def test_ipv6(text, ok):
    assert (ks.ipv6(text) is not None) == ok


def test_eui64_mac():
    iid = int(ks.ipv6('fe80::aa:bbff:fe00:2')) & ks.MASKE64
    assert ks.eui64_mac(iid) == '02aabb000002'
    assert ks.eui64_mac(1) is None


def test_altes_praefix_findet_knoten(bestand):
    s, o = ks.antwort(bestand, 'neander', 'ip=2001:db8:9:315:aa:bbff:fe00:1')
    assert s == 200
    assert [n['node_id'] for n in o['nodes']] == ['02aabb000001']
    assert o['nodes'][0]['match'] == 'interface-id'
    assert o['nodes'][0]['addresses'][0].startswith('2001:db8:1:715:')


def test_von_hand_vergeben_nur_genau(bestand):
    s, o = ks.antwort(bestand, 'neander', 'ip=2001:db8:1:715::1')
    assert s == 200 and o['nodes'][0]['hostname'] == 'supernode' and o['nodes'][0]['match'] == 'address'
    assert ks.antwort(bestand, 'neander', 'ip=2001:db8:9:315::1')[0] == 404


def test_genaue_adresse_zuerst(bestand):
    o = ks.antwort(bestand, 'neander', 'ip=2001:db8:1:715:aa:bbff:fe00:1')[1]
    assert [(n['node_id'], n['match']) for n in o['nodes']] == [('02aabb000001', 'address')]


def test_ohne_adresse_ueber_eui64(bestand):
    s, o = ks.antwort(bestand, 'neander', 'ip=2001:db8:9:1:aa:bbff:fe00:2')
    assert s == 200 and o['nodes'][0]['node_id'] == '02aabb000002'
    assert o['nodes'][0]['match'] == 'eui64' and o['nodes'][0]['online'] is False


def test_node_id_und_mac(bestand):
    assert ks.antwort(bestand, 'neander', 'node_id=02aabb000001')[1]['nodes'][0]['hostname'] == 'eins'
    assert ks.antwort(bestand, 'neander', 'mac=02-AA-BB-00-00-02')[1]['nodes'][0]['hostname'] == 'zwei'


@pytest.mark.parametrize('q,status', [
    ('', 400), ('ip=10.0.0.1', 400), ('node_id=123', 400), ('mac=x', 400),
    ('ip=2001:db8::1', 404), ('node_id=02aabb0000ff', 404),
])
def test_fehler(bestand, q, status):
    assert ks.antwort(bestand, 'neander', q)[0] == status


def test_unbekannte_community(bestand):
    assert ks.antwort(bestand, 'essen', 'node_id=02aabb000001')[0] == 404
    assert ks.antwort(bestand, '../etc', 'node_id=02aabb000001')[0] == 404


def test_datei_wird_neu_gelesen(bestand, tmp_path):
    assert ks.antwort(bestand, 'neander', 'node_id=02aabb000003')[0] == 404
    neu = json.loads(json.dumps(ZIELE))
    neu['nodes']['02aabb000003'] = {'hostname': 'drei', 'addresses': []}
    p = tmp_path / 'neander' / 'targets.json'
    p.write_text(json.dumps(neu))
    os.utime(p, (1, 2))
    assert ks.antwort(bestand, 'neander', 'node_id=02aabb000003')[0] == 200


def test_server(bestand):
    ks.Handler.bestand = bestand
    srv = ThreadingHTTPServer(('127.0.0.1', 0), ks.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = 'http://127.0.0.1:%d' % srv.server_port
        req = urllib.request.Request(url + '/nf/lookup?node_id=02aabb000001',
                                     headers={'X-Karte-Community': 'neander'})
        with urllib.request.urlopen(req) as r:
            assert r.status == 200 and r.headers['Access-Control-Allow-Origin'] == '*'
            assert json.load(r)['nodes'][0]['hostname'] == 'eins'
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + '/anders')
        assert e.value.code == 404
    finally:
        srv.shutdown()
