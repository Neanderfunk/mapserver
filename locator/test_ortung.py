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
    meldung(lan_mesh=[{'iface': 'br-mesh_other', 'mac': '02:00:00:00:00:01'}]),
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


def test_lan_mesh_schweigt_im_text(capsys):
    import auswertung
    e = {'empfangen': '2026-11-20T12:00:00', 'meldung': meldung(lan_mesh=[
        {'iface': 'br-mesh_other', 'mac': '02:00:00:00:00:01'},
        dict(LM[0], mac='02:00:00:00:00:02')])}
    auswertung.text(auswertung.auswerten({'0123456789ab': {'meldungen': 1, 'letzte': e, 'lan_switch': None}}, MESHIDS))
    t = capsys.readouterr().out
    assert '02:00:00:00:00:01 schweigt' in t
    assert '02:00:00:00:00:02 aabbccddeeff 21_dias' in t


def _a(nid, domain='25_hvb', ziel='21_dias', darf=(True, ''), letzte='2026-11-20T10:00:00+00:00'):
    return {'node_id': nid, 'domain': domain, 'wuerde_verschieben': ziel,
            'darf_gehen': darf, 'letzte': letzte}


def test_manifest_auswahl():
    import datetime
    import manifest
    jetzt = datetime.datetime(2026, 11, 20, 12, tzinfo=datetime.timezone.utc)
    aus = [_a('aaaaaaaaaaa1'),                                  # rein
           _a('aaaaaaaaaaa2', domain='21_dias'),                # nicht in 25_hvb
           _a('aaaaaaaaaaa3', ziel=None),                       # kein E11-Ziel
           _a('aaaaaaaaaaa4', ziel='25_hvb'),                   # eigene Domain
           _a('aaaaaaaaaaa5', darf=(False, 'x')),               # E12 nein
           _a('aaaaaaaaaaa6', darf=(None, 'x')),                # E12 unklar
           _a('aaaaaaaaaaa7', darf=None),                       # lan_switch
           _a('aaaaaaaaaaa8', letzte='2026-11-16T10:00:00+00:00'),  # zu alt
           _a('aaaaaaaaaaa9', ziel='31_lvrno')]                 # LVR per Mesh erlaubt
    assert manifest.auswahl(aus, jetzt) == [('aaaaaaaaaaa1', '21_dias'), ('aaaaaaaaaaa9', '31_lvrno')]


def test_manifest_koerper():
    import datetime
    import manifest
    jetzt = datetime.datetime(2026, 11, 20, 18, 5, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    t = manifest.koerper([('aaaaaaaaaaa1', '21_dias')], jetzt)
    z = t.split('\n')
    assert z[0] == 'FORMAT=1'
    assert z[1] == 'DATE=2026-11-20 18:05:00+01:00'
    assert z[2] == 'EXPIRES=2026-11-23 18:05:00+01:00'
    assert z[3].startswith('COMMENT=')
    assert z[4] == 'aaaaaaaaaaa1 domain target=21_dias'
    assert t.endswith('\n') and '---' not in t


# --- Teil 2: Position ---------------------------------------------------

def _pt(lat, lon, dkm_n=0, dkm_o=0):
    """Punkt dkm_n km noerdlich, dkm_o km oestlich von (lat, lon)."""
    import math
    return (lat + dkm_n / 111.2, lon + dkm_o / (111.2 * math.cos(math.radians(lat))))


MITTE = (51.25, 6.95)   # Mitte Domain MITTE
FL = {'01_vel': [_pt(*MITTE, i * 0.5) for i in range(5)],
      '02_met': [_pt(*MITTE, i * 0.5, 30) for i in range(5)]}


@pytest.mark.parametrize('lat,lon,ok', [
    (51.2, 6.9, True), (0, 6.9, False), (51.2, 0, False), (7.0, 7.0, False),
    (91, 6.9, False), ('51', 6.9, False), (None, None, False), (True, 6.9, False)])
def test_ort_gueltig(lat, lon, ok):
    assert ortung.ort_gueltig(lat, lon) is ok


def test_kern_ballung_nah_und_extraterritorial():
    ballung = [_pt(*MITTE, 0, i * 2) for i in range(3)]
    nah = _pt(*MITTE, 20)
    weit = _pt(*MITTE, 60)
    k = ortung.kern(ballung + [nah, weit])
    assert set(k) == set(ballung + [nah])
    assert ortung.kern([nah, weit]) == []


def test_position_im_kern():
    z = ortung.position_ziel(_pt(*MITTE, 1), 20, FL)
    assert z['ziel'] == '01_vel' and z['stufe_km'] == 3 and z['unklar'] is None


def test_position_zwischen_zwei_unklar():
    z = ortung.position_ziel(_pt(*MITTE, 1, 15), 20, FL)
    assert z['ziel'] in ('01_vel', '02_met') and z['stufe_km'] == 20
    assert z['unklar'] in ('01_vel', '02_met') and z['unklar'] != z['ziel']


def test_position_ausserhalb_diaspora():
    z = ortung.position_ziel(_pt(*MITTE, 0, -80), 20, FL)
    assert z == {'ziel': '21_dias', 'stufe_km': None, 'feld': None, 'unklar': None}


def test_genauigkeit_verbreitert():
    # Randlage 26 km neben fuenf Knoten: ohne Messfehler knapp ausserhalb,
    # mit 5 km Messfehler verschmiert der Kern und holt sie herein
    p = _pt(*MITTE, 1, -26)
    assert ortung.position_ziel(p, 0, FL)['ziel'] == '21_dias'
    assert ortung.position_ziel(p, 5000, FL)['ziel'] == '01_vel'


def test_positionsziele_ohne_lvr_unterkunft():
    z = ortung.positionsziele(ortung.meshids_lesen(os.path.join(os.path.dirname(__file__), 'meshids.conf')))
    assert '01_vel' in z and '43_bggl' in z
    for d in ('11_lvr', '31_lvrno', '36_lvrsw', '12_dusuk', '24_dusukw', '21_dias', '25_hvb'):
        assert d not in z


def test_vergroebern_200m():
    lat, lon = ortung.vergroebern(51.23456, 6.98765)
    assert ortung.abstand_km((lat, lon), (51.23456, 6.98765)) < 0.15


def _k(nid, m, datei='x.json'):
    return {nid: {'meldungen': 1, 'lan_switch': None,
                  'letzte': {'empfangen': '2026-11-21T10:00:00+00:00', 'datei': datei, 'meldung': m}}}


def _vpn():
    return {'vpn': True, 'gw_nexthop': 'aa:aa:aa:aa:aa:aa', 'mesh_macs': ['02:00:00:00:00:09']}


def test_auswertung_koordinaten_des_knotens():
    import auswertung
    m = meldung(coordinates={'lat': _pt(*MITTE, 1)[0], 'lon': MITTE[1]}, uplink=_vpn())
    a = auswertung.auswerten(_k('0123456789ab', m), MESHIDS, FL, None)[0]
    assert a['ziel'] == '01_vel' and a['weg'] == 'Position' and a['klaerung'] is None


def test_auswertung_genauigkeit_zu_gross_und_veraltet(tmp_path):
    import auswertung
    (tmp_path / '0123456789ab.json').write_text(json.dumps(
        {'datei': 'x.json', 'quelle': 'beaconDB', 'lat': MITTE[0], 'lon': MITTE[1], 'genauigkeit': 6000}))
    a = auswertung.auswerten(_k('0123456789ab', meldung()), MESHIDS, FL, str(tmp_path))[0]
    assert a['ziel'] is None and a['klaerung'].startswith('Genauigkeit 6000')
    a = auswertung.auswerten(_k('0123456789ab', meldung(), 'y.json'), MESHIDS, FL, str(tmp_path))[0]
    assert a['klaerung'] == 'noch nicht geortet'


def test_auswertung_e11_vor_position():
    import auswertung
    m = meldung(wifi=[w('1', 'met-mesh', -60)], coordinates={'lat': MITTE[0], 'lon': MITTE[1]})
    a = auswertung.auswerten(_k('0123456789ab', m), MESHIDS, FL, None)[0]
    assert a['ziel'] == '02_met' and a['weg'] == 'E11' and a['position'] is None


def test_manifest_karte_hand_klaerung():
    import datetime
    import manifest
    jetzt = datetime.datetime(2026, 11, 21, 12, tzinfo=datetime.timezone.utc)
    aus = [dict(_a('aaaaaaaaaaa1'), ziel='01_vel', klaerung=None),
           dict(_a('aaaaaaaaaaa2'), ziel=None, klaerung='noch nicht geortet'),
           _a('aaaaaaaaaaa3'),
           dict(_a('aaaaaaaaaaa4', darf=(False, 'x')))]
    karte = {'aaaaaaaaaaa1': '25_hvb', 'aaaaaaaaaaa2': '25_hvb', 'aaaaaaaaaaa3': '21_dias'}
    hand = {'aaaaaaaaaaa4': '21_dias', 'bbbbbbbbbbbb': '13_dusfl'}
    assert manifest.auswahl(aus, jetzt, karte, hand) == [
        ('aaaaaaaaaaa1', '01_vel'), ('aaaaaaaaaaa4', '21_dias'), ('bbbbbbbbbbbb', '13_dusfl')]


def test_hand_ablauf(tmp_path):
    import datetime
    import manifest
    p = tmp_path / 'hand.conf'
    p.write_text('# x\naaaaaaaaaaa1 21_dias 2026-11-21T13:00:00+00:00\n'
                 'aaaaaaaaaaa2 21_dias 2026-11-21T11:00:00+00:00\nkaputt\n')
    jetzt = datetime.datetime(2026, 11, 21, 12, tzinfo=datetime.timezone.utc)
    assert manifest.hand_gueltig(manifest.hand_lesen(str(p)), jetzt) == {'aaaaaaaaaaa1': '21_dias'}


def test_anbieter_nur_fremde_wlans():
    import orten
    wifi = [{'bssid': 'A0:00:00:00:00:01', 'ssid': 'FRITZ!Box', 'mesh_id': '', 'signal': -70},
            {'bssid': 'a0:00:00:00:00:02', 'ssid': 'Freifunk', 'mesh_id': '', 'signal': -60},
            {'bssid': 'a0:00:00:00:00:03', 'ssid': '', 'mesh_id': 'vel-mesh', 'signal': -60},
            {'bssid': 'a2:00:00:00:00:04', 'ssid': 'Handy', 'mesh_id': '', 'signal': -50}]
    assert orten.netze_fuer_anbieter(wifi) == [{'macAddress': 'a0:00:00:00:00:01', 'signalStrength': -70}]


def test_flaechen_berechnen():
    import flaechen
    k = [{'domain': '01_vel', 'is_online': True, 'location': {'latitude': p[0], 'longitude': p[1]}}
         for p in FL['01_vel']]
    k += [{'domain': '11_lvr', 'is_online': True, 'location': {'latitude': MITTE[0], 'longitude': MITTE[1]}}] * 3
    k += [{'domain': '01_vel', 'is_online': False, 'location': {'latitude': 50.0, 'longitude': 7.0}}]
    f = flaechen.berechnen(k, ['01_vel', '02_met'])
    assert list(f) == ['01_vel'] and len(f['01_vel']) == 5
