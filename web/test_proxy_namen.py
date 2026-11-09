# SPDX-License-Identifier: BSD-3-Clause
"""namen.conf (Namen, die map6 kennt) gegen den Proxy davor pruefen.

TLS endet auf dem PVE vor der Karten-VM. Dessen vhosts stehen im Ansible-Repo
in vorbau/vms/spacemap.yml (Rolle pve_vorbau, abgestimmt mit der
Operations-Session 09.11.2026). Die Namen stehen damit zweimal: hier fuer die
vhosts auf map6, dort fuer server_name und Zertifikat. Dieser Test merkt,
wenn beide auseinanderlaufen. Er liest das Ansible-Repo aus ANSIBLE_REPO,
sonst aus dem Nachbarverzeichnis ../ansible, und wird uebersprungen, wenn es
fehlt.

Geprueft wird:
- jeder Name aus namen.conf erreicht den Proxy (genau oder per Wildcard im
  server_name eines Karten-vhosts),
- jeder genaue Name aus namen.conf steht in einem Zertifikat (domains ohne
  Wildcards plus zert_namen_extra); Wildcards kann das Webroot-Verfahren nicht,
- kein Name steht in zwei Karten-vhosts.
"""
import os

import pytest

yaml = pytest.importorskip('yaml')

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get('ANSIBLE_REPO', os.path.join(HIER, '..', '..', 'ansible'))
SPACEMAP = os.path.join(REPO, 'vorbau', 'vms', 'spacemap.yml')
NAMEN = os.path.join(HIER, 'namen.conf')


def namen_conf():
    alle = []
    for zeile in open(NAMEN, encoding='utf-8'):
        t = zeile.split('#', 1)[0].split()
        if len(t) >= 2:
            alle.extend(t[2:] if t[1] == 'umleiten' else t[1:])
    return alle


@pytest.fixture(scope='module')
def vhosts():
    if not os.path.exists(SPACEMAP):
        pytest.skip('Ansible-Repo nicht da: ' + SPACEMAP)
    return yaml.safe_load(open(SPACEMAP, encoding='utf-8'))['vhosts']


def passt(name, server_name):
    """Wie nginx: genau, oder "*.x" passt auf jede Subdomain von x."""
    if server_name.startswith('*.'):
        return name.endswith(server_name[1:]) or name == server_name
    return name == server_name


def test_jeder_name_erreicht_den_proxy(vhosts):
    alle = [d for v in vhosts for d in v['domains'] + v.get('zert_namen_extra', [])]
    fehlt = [n for n in namen_conf() if not any(passt(n, s) for s in alle)]
    assert not fehlt, 'in namen.conf, aber nicht in spacemap.yml: %s' % fehlt


def test_genaue_namen_im_zertifikat(vhosts):
    zert = {d for v in vhosts for d in v['domains'] + v.get('zert_namen_extra', [])
            if not d.startswith('*')}
    fehlt = [n for n in namen_conf() if not n.startswith('*') and n not in zert]
    assert not fehlt, 'ohne Zertifikat auf dem Proxy (zert_namen_extra): %s' % fehlt


def test_kein_name_doppelt(vhosts):
    gesehen, doppelt = set(), []
    for v in vhosts:
        for d in v['domains'] + v.get('zert_namen_extra', []):
            if d in gesehen:
                doppelt.append(d)
            gesehen.add(d)
    assert not doppelt, doppelt
