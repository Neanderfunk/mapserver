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



def knoten(nid, vpn, nexthop=None, macs=(), domain='25_hvb'):
    u = {'vpn': vpn, 'gw_via': 'mesh-vpn' if vpn else 'mesh1', 'mesh_macs': list(macs)}
    if nexthop:
        u['gw_nexthop'] = nexthop
    return meldung(node_id=nid, domain=domain, uplink=u)


A = knoten('aaaaaaaaaaaa', True, '02:ca:ff:ee:21:00', ['aa:00:00:00:00:01', 'aa:00:00:00:00:02'])


def test_e12_ohne_vpn_nein():
    assert ortung.darf_gehen(knoten('bbbbbbbbbbbb', False, 'a6:f7:ba:13:fd:09'), [])[0] is False


def test_e12_vpn_allein_ja():
    assert ortung.darf_gehen(A, [A])[0] is True


def test_e12_haengt_jemand_dran_nein():
    b = knoten('bbbbbbbbbbbb', False, 'AA:00:00:00:00:02')
    ok, grund = ortung.darf_gehen(A, [A, b])
    assert ok is False and 'bbbbbbbbbbbb' in grund


def test_e12_andere_domain_zaehlt_nicht():
    b = knoten('bbbbbbbbbbbb', False, 'aa:00:00:00:00:02', domain='21_dias')
    assert ortung.darf_gehen(A, [A, b])[0] is True


def test_e12_zwei_vpn_blockieren_sich_nicht():
    c = knoten('cccccccccccc', True, '02:ca:ff:ee:21:00', ['cc:00:00:00:00:01'])
    assert ortung.darf_gehen(A, [A, c])[0] is True


def test_e12_unklar():
    assert ortung.darf_gehen(meldung(), [])[0] is None
    assert ortung.darf_gehen(knoten('dddddddddddd', True, None, ['dd:00:00:00:00:01']), [])[0] is None
    assert ortung.darf_gehen(knoten('dddddddddddd', True, '02:ca:ff:ee:21:00'), [])[0] is None


LM = [{'iface': 'br-mesh_other', 'node_id': 'aabbccddeeff', 'domain': '21_dias'}]


@pytest.mark.parametrize('m', [
    meldung(lan_mesh=LM), meldung(lan_mesh={}), meldung(lan_mesh=[]), meldung(wifi={}),
    meldung(lan_mesh=[{'iface': 'br-mesh_other', 'node_id': 'aabbccddeeff'}], lan_switch='21_dias'),
])
def test_lan_mesh_gut(m):
    ortung.pruefen(m)


@pytest.mark.parametrize('m', [
    meldung(lan_mesh='x'), meldung(lan_mesh={'a': 1}), meldung(lan_mesh=['x']), meldung(lan_switch=21),
])
def test_lan_mesh_schlecht(m):
    with pytest.raises(ortung.Ungueltig):
        ortung.pruefen(m)


def test_lan_mesh_leer_als_objekt():
    assert ortung.lan_mesh(meldung(lan_mesh={})) == []
    assert ortung.lan_mesh(meldung()) == []
    assert ortung.lan_mesh(meldung(lan_mesh=LM)) == LM


def test_lan_switch_ohne_e11_e12_und_umgeschaltet():
    import auswertung
    vorher = {'empfangen': '2026-11-20T10:00:00', 'meldung': meldung(lan_mesh=LM, lan_switch='21_dias', wifi={})}
    k = {'meldungen': 1, 'letzte': vorher, 'lan_switch': {'ziel': '21_dias', 'zeit': vorher['empfangen']}}
    a = auswertung.auswerten({'0123456789ab': k}, MESHIDS)[0]
    assert a['darf_gehen'] is None and a['wuerde_verschieben'] is None
    assert not a['lan_umgeschaltet'] and a['lan_mesh'] == LM
    k['letzte'] = {'empfangen': '2026-11-20T11:00:00', 'meldung': meldung(domain='21_dias')}
    k['meldungen'] = 2
    a = auswertung.auswerten({'0123456789ab': k}, MESHIDS)[0]
    assert a['lan_umgeschaltet'] and a['darf_gehen'] is not None
