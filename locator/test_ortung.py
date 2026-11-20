# SPDX-License-Identifier: BSD-3-Clause
import json
import os
import sys
import threading
import urllib.request
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortung  # noqa: E402

MESHIDS = {'vel-mesh': '01_vel', 'met-mesh': '02_met', 'hvb-mesh': '25_hvb', 'lvrno-mesh': '31_lvrno'}


def w(bssid, mesh_id='', signal=-60):
    return {'bssid': bssid, 'ssid': '', 'mesh_id': mesh_id, 'signal': signal, 'freq': 2437}


def meldung(**k):
    m = {'v': 1, 'node_id': '0123456789ab', 'domain': '25_hvb', 'wifi': []}
    m.update(k)
    return m


def test_pruefen_gut():
    assert ortung.pruefen(meldung(wifi=[w('aa:bb:cc:dd:ee:ff')])) == 1


@pytest.mark.parametrize('m', [
    [], meldung(v=2), meldung(node_id='0123456789AB'), meldung(node_id='x'),
    meldung(wifi='x'), meldung(wifi=[{'signal': -1}]), meldung(wifi=[{'bssid': 'a'}]),
])
def test_pruefen_schlecht(m):
    with pytest.raises(ortung.Ungueltig):
        ortung.pruefen(m)


def ziel(wifi, s=-75):
    return ortung.zieldomain(ortung.mesh_partner(wifi, MESHIDS), s)


def test_ein_starker_punkt_reicht():
    assert ziel([w('1', 'vel-mesh', -70)]) == '01_vel'


def test_ein_schwacher_punkt_reicht_nicht():
    assert ziel([w('1', 'vel-mesh', -78)]) is None
    assert ziel([w('1', 'vel-mesh', -78)], -80) == '01_vel'


def test_zwei_punkte_beliebig():
    assert ziel([w('1', 'vel-mesh', -90), w('2', 'vel-mesh', -91)]) == '01_vel'


def test_dieselbe_bssid_zaehlt_einmal():
    assert ziel([w('1', 'vel-mesh', -90), w('1', 'vel-mesh', -88)]) is None


def test_staerkster_entscheidet():
    assert ziel([w('1', 'vel-mesh', -70), w('2', 'met-mesh', -60)]) == '02_met'


def test_hvb_und_unbekannt_zaehlen_nicht():
    assert ziel([w('1', 'hvb-mesh', -40), w('2', 'xyz-mesh', -40)]) is None


def test_lvr_ueber_mesh_erlaubt():
    assert ziel([w('1', 'lvrno-mesh', -60)]) == '31_lvrno'


def test_meshids_conf_eindeutig():
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshids.conf')
    ids = [z.split()[0] for z in open(pfad) if z.strip() and not z.startswith('#')]
    assert len(ids) == len(set(ids)) and 'hvb-mesh' in ids


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCATOR_ABLAGE', str(tmp_path))
    import importlib
    import annahme
    importlib.reload(annahme)
    s = annahme.ThreadingHTTPServer(('127.0.0.1', 0), annahme.Annahme)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d' % s.server_address[1], tmp_path
    s.shutdown()


def post(url, daten):
    r = urllib.request.Request(url, data=daten, method='POST',
                               headers={'Content-Type': 'application/json', 'X-Forwarded-For': '192.0.2.10'})
    try:
        with urllib.request.urlopen(r) as a:
            return a.status, json.load(a)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_annahme_legt_ab(server):
    url, ablage = server
    st, a = post(url + '/hvb/locate', json.dumps(meldung(wifi=[w('1')])).encode())
    assert (st, a) == (200, {'angenommen': True, 'netze': 1})
    dateien = list(ablage.glob('*/*.json'))
    assert len(dateien) == 1 and oct(dateien[0].stat().st_mode & 0o777) == '0o600'
    e = json.load(open(dateien[0]))
    assert e['x_forwarded_for'] == '192.0.2.10' and e['meldung']['node_id'] == '0123456789ab'


def test_annahme_verwirft_unsinn(server):
    url, ablage = server
    assert post(url + '/hvb/locate', b'{kaputt')[0] == 400
    assert post(url + '/hvb/locate', json.dumps(meldung(v=9)).encode())[0] == 400
    assert post(url + '/anderswo', b'{}')[0] == 404
    assert not list(ablage.glob('*/*.json'))


def test_absender_nur_gleiche_familie():
    import auswertung
    assert auswertung.absender_passt('192.0.2.10', {'ipv4': '192.0.2.10'}) is True
    assert auswertung.absender_passt('192.0.2.11', {'ipv4': '192.0.2.10'}) is False
    assert auswertung.absender_passt('2001:db8::1', {'ipv4': '192.0.2.10'}) is None
    assert auswertung.absender_passt('', {}) is None
