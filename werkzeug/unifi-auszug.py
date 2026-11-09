#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Liest einen UniFi-Controller (UniFi OS: UDM, Cloud Gateway) nur lesend aus
und legt Geraete, Ports, Netze, WLANs und Clients als CSV und als gesaeuberte
Rohdaten ab, etwa fuer ein IT-Inventar. Geheimnisse (WLAN-Schluessel,
Passwoerter, RADIUS-Secrets, WireGuard-Schluessel, Tokens) werden vor dem
Speichern durch "<entfernt>" ersetzt, SSID-Namen bleiben.

Der Controller ist meist nur von der Karten-VM aus erreichbar (WireGuard-Tunnel,
siehe docs/unifi-sites.md). Dieses Skript laeuft deshalb lokal, schickt sich
selbst per ssh auf die VM, fragt dort den Controller ab und bekommt nur das
gesaeuberte JSON zurueck. Auf der VM bleibt nichts liegen, root braucht es nicht.

    werkzeug/unifi-auszug.py LOGINDATEI ZIELVERZEICHNIS [--url URL] [--ssh ZIEL]

    LOGINDATEI      drei Zeilen: Benutzer, Passwort, URL (Konto "View Only")
    ZIELVERZEICHNIS wird mit Rechten 700 angelegt, Dateien 600
    --url           statt der URL aus der Datei, etwa die Tunneladresse
                    https://172.31.253.2, wenn in der Datei die LAN-Adresse steht
    --ssh           ssh-Ziel, Vorgabe ad-claude@map6.freifunk.space -p 62954;
                    "-" fragt direkt von hier ab, ohne ssh

Weitere ssh-Optionen (etwa -i SCHLUESSEL) ueber die Umgebung SSH_OPTS.
Intern: "holen" (Zugang auf stdin, JSON auf stdout) und "csv ROH ZIEL".
"""
import csv
import datetime
import http.cookiejar
import json
import os
import re
import shlex
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

SSH_VORGABE = 'ad-claude@map6.freifunk.space -p 62954'
GEHEIM = re.compile(r'(pass|secret|psk|private|token|cert|^x_|_key$|^key$|keys$|^key_|_keys?_)', re.I)
ABFRAGEN = [('device', 'stat/device'), ('networkconf', 'rest/networkconf'),
            ('wlanconf', 'rest/wlanconf'), ('portconf', 'rest/portconf'),
            ('sta', 'stat/sta'), ('user', 'rest/user')]


def saeubern(o):
    if isinstance(o, dict):
        return {k: ('<entfernt>' if GEHEIM.search(k) else saeubern(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [saeubern(v) for v in o]
    return o


def holen():
    """Auf der VM: Zugang von stdin, gesaeubertes JSON auf stdout."""
    benutzer, passwort, url = [z.strip() for z in sys.stdin.read().splitlines()[:3]]
    url = url.rstrip('/')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                     urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = [None]

    def anfrage(pfad, daten=None):
        h = {'Content-Type': 'application/json'}
        if csrf[0]:
            h['X-CSRF-Token'] = csrf[0]
        req = urllib.request.Request(url + pfad, headers=h,
                                     data=json.dumps(daten).encode() if daten else None,
                                     method='POST' if daten else 'GET')
        for versuch in range(5):
            try:
                with op.open(req, timeout=15) as r:
                    csrf[0] = r.headers.get('X-CSRF-Token') or csrf[0]
                    return json.load(r)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if getattr(e, 'code', None):
                    raise
                print('Versuch %d %s: %s' % (versuch + 1, pfad, e), file=sys.stderr)
        raise SystemExit('Controller nicht erreichbar: %s%s' % (url, pfad))

    anfrage('/api/auth/login', {'username': benutzer, 'password': passwort})
    del passwort
    n = '/proxy/network/api'
    aus = {'sites': saeubern(anfrage(n + '/self/sites')['data'])}
    for s in aus['sites']:
        d = {}
        for name, pfad in ABFRAGEN:
            try:
                d[name] = saeubern(anfrage('%s/s/%s/%s' % (n, s['name'], pfad))['data'])
            except urllib.error.HTTPError as e:
                d[name] = []
                print('%s/%s: %s' % (s['name'], pfad, e), file=sys.stderr)
        aus['site:' + s['name']] = d
    json.dump(aus, sys.stdout)


def zeit(t):
    return datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M') if t else ''


STATUS = {0: 'offline', 1: 'online', 2: 'pending', 4: 'upgrading', 5: 'provisioning',
          6: 'heartbeat missed', 7: 'adopting', 9: 'adoption failed', 10: 'isolated', 11: 'isolated'}


def site_csv(d, ziel, vor):
    dev, net, wlan, sta, user, pconf = (d.get(k) or [] for k in
                                        ('device', 'networkconf', 'wlanconf', 'sta', 'user', 'portconf'))
    netz = {x['_id']: x for x in net}
    profil = {x['_id']: x for x in pconf}
    gname = {g['mac']: g.get('name') or g['mac'] for g in dev}

    def nname(i):
        x = netz.get(i)
        return '%s (VLAN %s)' % (x['name'], x.get('vlan') or 1) if x else (i or '')

    def schreibe(datei, kopf, zeilen):
        p = os.path.join(ziel, vor + datei)
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(kopf)
            w.writerows(zeilen)
        os.chmod(p, 0o600)

    def uplink(g):
        return g.get('uplink') or g.get('last_uplink') or {}

    schreibe('geraete.csv',
             ['name', 'typ', 'modell', 'mac', 'ip', 'firmware', 'seriennr', 'status', 'last_seen', 'uptime_h',
              'snmp_location', 'snmp_contact', 'uplink_geraet', 'uplink_port', 'uplink_lokaler_port',
              'uplink_art', 'uplink_speed'],
             [[g.get('name', ''), g.get('type'), g.get('model'), g['mac'], g.get('ip', ''), g.get('version', ''),
               g.get('serial', ''), STATUS.get(g.get('state'), g.get('state')), zeit(g.get('last_seen')),
               round(g['uptime'] / 3600, 1) if g.get('uptime') else '', g.get('snmp_location', ''),
               g.get('snmp_contact', ''), uplink(g).get('uplink_device_name', ''),
               uplink(g).get('uplink_remote_port', ''), uplink(g).get('port_idx', ''), uplink(g).get('type', ''),
               (g.get('uplink') or {}).get('speed', '')]
              for g in sorted(dev, key=lambda g: (g.get('type', ''), g.get('name', '')))])

    # Was an einem Port haengt: LLDP, Uplinks anderer Geraete, Kabel-Clients
    dran = {}
    for g in dev:
        for l in g.get('lldp_table') or []:
            dran.setdefault((g['mac'], l.get('local_port_idx')), set()).add(
                'LLDP %s %s' % (gname.get(l.get('chassis_id'), l.get('chassis_id')), l.get('port_id', '')))
        u = uplink(g)
        if u.get('uplink_mac') and u.get('uplink_remote_port'):
            dran.setdefault((u['uplink_mac'], u['uplink_remote_port']), set()).add(
                'Geraet %s' % (g.get('name') or g['mac']))
    for c in sta:
        if c.get('is_wired') and c.get('sw_mac'):
            dran.setdefault((c['sw_mac'], c.get('sw_port')), set()).add(
                'Client %s %s' % (c.get('name') or c.get('hostname') or '', c['mac']))

    def getaggt(p):
        if p.get('tagged_vlan_mgmt') == 'block_all':
            return 'keine'
        if p.get('excluded_networkconf_ids'):
            return 'alle ausser ' + ', '.join(nname(i) for i in p['excluded_networkconf_ids'])
        return 'alle' if p.get('tagged_vlan_mgmt') == 'custom' else p.get('tagged_vlan_mgmt') or ''

    schreibe('ports.csv',
             ['geraet', 'geraet_mac', 'port', 'portname', 'aktiviert', 'link', 'speed', 'vollduplex', 'medium',
              'uplink', 'op_mode', 'poe_mode', 'poe_watt', 'natives_netz', 'getaggte_netze', 'portprofil', 'stp',
              'aggregiert_von', 'angeschlossen'],
             [[g.get('name', ''), g['mac'], p.get('port_idx'), p.get('name', ''), p.get('enable', p.get('enabled')),
               'up' if p.get('up') else 'down', p.get('speed', ''), p.get('full_duplex', ''), p.get('media', ''),
               p.get('is_uplink', ''), p.get('op_mode', ''), p.get('poe_mode', '') if p.get('port_poe') else '',
               p.get('poe_power', '') if p.get('port_poe') else '', nname(p.get('native_networkconf_id')),
               getaggt(p), profil.get(p.get('portconf_id'), {}).get('name', ''), p.get('stp_state', ''),
               p.get('aggregated_by') or '', ' | '.join(sorted(dran.get((g['mac'], p.get('port_idx')), [])))]
              for g in sorted(dev, key=lambda g: g.get('name', '')) for p in g.get('port_table') or []])

    schreibe('netze.csv',
             ['name', 'zweck', 'vlan', 'subnetz', 'netzgruppe', 'aktiv', 'dhcp_server', 'dhcp_von', 'dhcp_bis',
              'dns', 'ipv6', 'internet', 'isoliert', 'wan_typ', 'domain'],
             [[x.get('name'), x.get('purpose'), x.get('vlan', '1' if x.get('purpose') == 'corporate' else ''),
               x.get('ip_subnet', ''), x.get('networkgroup', ''), x.get('enabled'), x.get('dhcpd_enabled', ''),
               x.get('dhcpd_start', ''), x.get('dhcpd_stop', ''), x.get('dhcpd_dns_1', ''),
               x.get('ipv6_interface_type', ''), x.get('internet_access_enabled', ''),
               x.get('network_isolation_enabled', ''), x.get('wan_type', ''), x.get('domain_name', '')]
              for x in sorted(net, key=lambda x: (x.get('purpose', ''), int(x.get('vlan') or 0)))])

    aps = {}
    for g in dev:
        for v in g.get('vap_table') or []:
            aps.setdefault(v.get('wlanconf_id') or v.get('essid'), set()).add(
                '%s (%s)' % (g.get('name') or g['mac'], v.get('radio')))
    schreibe('wlans.csv',
             ['ssid', 'aktiv', 'versteckt', 'gast', 'netz', 'baender', 'sicherheit', 'wpa_mode', 'wpa3',
              'wpa3_transition', 'pmf', 'ap_gruppen_modus', 'ausgestrahlt_von'],
             [[w.get('name'), w.get('enabled'), w.get('hide_ssid'), w.get('is_guest'), nname(w.get('networkconf_id')),
               '+'.join(w.get('wlan_bands') or [w.get('wlan_band', '')]), w.get('security'), w.get('wpa_mode'),
               w.get('wpa3_support'), w.get('wpa3_transition'), w.get('pmf_mode'), w.get('ap_group_mode', ''),
               ' | '.join(sorted(aps.get(w['_id'], set()) | aps.get(w.get('name'), set())))]
              for w in wlan])

    schreibe('clients.csv',
             ['mac', 'name', 'hostname', 'hersteller', 'ip', 'netz', 'vlan', 'kabel', 'ap', 'ssid', 'radio',
              'signal', 'switch', 'switchport', 'last_seen', 'first_seen'],
             [[c['mac'], c.get('name', ''), c.get('hostname', ''), c.get('oui', ''), c.get('ip') or c.get('last_ip', ''),
               c.get('network', ''), c.get('vlan', ''), c.get('is_wired'), gname.get(c.get('ap_mac'), c.get('ap_mac', '')),
               c.get('essid', ''), c.get('radio', ''), c.get('signal', ''), gname.get(c.get('sw_mac'), c.get('sw_mac', '')),
               c.get('sw_port', ''), zeit(c.get('last_seen')), zeit(c.get('first_seen'))]
              for c in sorted(sta, key=lambda c: (c.get('network', ''), c.get('ip') or c.get('last_ip') or ''))])

    # Bekannte Clients, auch offline; nur mit Namen, fester IP oder Notiz
    schreibe('clients-bekannt.csv',
             ['mac', 'name', 'hostname', 'hersteller', 'feste_ip', 'netz_fest', 'zuletzt_ip', 'zuletzt_netz',
              'zuletzt_an', 'last_seen', 'first_seen', 'notiz'],
             [[u['mac'], u.get('name', ''), u.get('hostname', ''), u.get('oui', ''),
               u.get('fixed_ip', '') if u.get('use_fixedip') else '',
               nname(u.get('network_id')) if u.get('use_fixedip') else '', u.get('last_ip', ''),
               u.get('last_connection_network_name', ''), u.get('last_uplink_name', ''), zeit(u.get('last_seen')),
               zeit(u.get('first_seen')), u.get('note', '')]
              for u in sorted(user, key=lambda u: u.get('name') or u.get('hostname') or '~')
              if u.get('name') or u.get('use_fixedip') or u.get('note')])

    for name, _ in ABFRAGEN:
        p = os.path.join(ziel, '%sroh-%s.json' % (vor, name))
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(d.get(name) or [], f, indent=1, ensure_ascii=False)
        os.chmod(p, 0o600)
    return {k: len(d.get(k) or []) for k in ('device', 'networkconf', 'wlanconf', 'sta')}


def als_csv(alles, ziel):
    os.makedirs(ziel, mode=0o700, exist_ok=True)
    os.chmod(ziel, 0o700)
    sites = [k for k in alles if k.startswith('site:')]
    for k in sites:
        vor = '' if len(sites) == 1 else k[5:] + '-'
        print(k[5:], site_csv(alles[k], ziel, vor))


def main():
    a = sys.argv[1:]
    if a[:1] == ['holen']:
        return holen()
    if a[:1] == ['csv']:
        return als_csv(json.load(open(a[1])), a[2])
    url = ssh = None
    frei = []
    while a:
        x = a.pop(0)
        if x == '--url':
            url = a.pop(0)
        elif x == '--ssh':
            ssh = a.pop(0)
        else:
            frei.append(x)
    if len(frei) != 2:
        raise SystemExit(__doc__)
    login, ziel = frei
    zeilen = open(login, encoding='utf-8').read().splitlines()[:3]
    if url:
        zeilen[2] = url
    zugang = '\n'.join(zeilen) + '\n'
    if ssh == '-':
        befehl = [sys.executable, os.path.abspath(__file__), 'holen']
    else:
        quelle = open(os.path.abspath(__file__), encoding='utf-8').read()
        befehl = (['ssh'] + shlex.split(os.environ.get('SSH_OPTS', '')) + shlex.split(ssh or SSH_VORGABE)
                  + ['python3 -c %s holen' % shlex.quote(quelle)])
    r = subprocess.run(befehl, input=zugang.encode(), capture_output=True)
    sys.stderr.write(r.stderr.decode(errors='replace'))
    if r.returncode:
        raise SystemExit(r.returncode)
    als_csv(json.loads(r.stdout), ziel)


if __name__ == '__main__':
    main()
