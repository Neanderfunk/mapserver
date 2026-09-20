#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt /etc/yanic.conf aus der Domaintabelle.

Ein yanic-Prozess fragt alle acht batman-Instanzen ab und schreibt neun
Datensaetze: einmal alles zusammen fuer en.map.freifunk.space und je Domain
einen gefilterten Satz fuer <ort>.en.map.freifunk.space.

no_owner steht ueberall auf true. Die Knoten gehoeren nicht uns; was ihre
Betreiberinnen an Kontaktdaten eingetragen haben, ist nicht fuer unsere
Veroeffentlichung gedacht.
"""
import os
import sys

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en/sites'
# Abfragetakt und Offline-Schwelle. Bewusst schonender als ueblich, siehe
# Begruendung im erzeugten Kopf.
TAKT = '5m'
OFFLINE = '20m'

# Abfrageadresse je Gemeinschaft. Vorgabe ist ff05::2:1001, die Gruppe, die
# Stock-Gluon auf br-client bedient.
#
# Im eigenen Netz antwortet darauf gemessen nur der Supernode, eine Antwort je
# Domain. Auf ff02::1 antworten dagegen alle Knoten: genau diese Gruppe oeffnet
# unser Patch fix-respondd-rsk zusaetzlich, die Rueckkehr zum Verhalten von
# Gluon 2016. Ueber batman ist ff02::1 kein Nachteil, das ganze Mesh ist eine
# Broadcast-Domain (gemessen 20.09.2026: ff05 eine Antwort, ff02::1 alle).
ABFRAGE = {'neander': 'ff02::1'}


FELDER = ('gem', 'code', 'ordner', 'port', 'id', 'host', 'mtu', 'broker',
          'prefix6', 'prefix4', 'name')


def domains(pfad):
    for z in open(pfad, encoding='utf-8'):
        z = z.strip()
        if not z or z.startswith('#'):
            continue
        t = z.split(None, len(FELDER) - 1)
        if len(t) == len(FELDER):
            yield dict(zip(FELDER, t))


def ausgabe(pfad, sites=None, titel=''):
    f = f'\n# {titel}\n' if titel else '\n'
    f += '[[nodes.output.meshviewer-ffrgb]]\n'
    f += 'enable = true\n'
    f += f'path = "{pfad}/meshviewer.json"\n'
    f += '[nodes.output.meshviewer-ffrgb.filter]\n'
    f += 'no_owner = true\n'
    if sites:
        f += 'sites = ["%s"]\n' % '", "'.join(sites)
    return f


def main():
    d = list(domains(KONF))
    if not d:
        print(f'keine Domains in {KONF}', file=sys.stderr)
        return 1

    # Eine einzige fehlende Schnittstelle beendet yanic mit einem Panic
    # ("route ip+net: no such network interface"). Bei 56 Domains heisst das:
    # ein Broker, der nicht antwortet, nimmt die ganze Karte mit. Deshalb
    # kommen nur Domains in die Konfiguration, deren bat-Instanz es auch gibt.
    # Die Ausgaben bleiben vollstaendig, eine Domain ohne Tunnel ist dann eine
    # leere Karte statt gar keiner (20.09.2026).
    fehlen = [x for x in d if not os.path.isdir(f'/sys/class/net/bat-{x["code"]}')]
    if fehlen and '--alle' not in sys.argv:
        print('# ohne Tunnel, deshalb nicht abgefragt: '
              + ', '.join(x['code'] for x in fehlen))
        for x in fehlen:
            print(f'#   {x["code"]:12} {x["name"]}')

    t = ['# Erzeugt von yanic-conf.py aus /etc/karte-en/domains.conf.',
         '# Nicht von Hand aendern, sondern die Domaintabelle pflegen.',
         '',
         '[respondd]',
         'enable = true',
         '# Wir sind Gast in fremden Domains. Die verbreitete Minute waere fuer',
         '# eine eigene Karte in Ordnung, hier heisst sie: acht Multicast-Rufe je',
         '# Minute in fremde Netze, dazu die Unicast-Nachfragen an Knoten, die',
         f'# nicht geantwortet haben. Deshalb {TAKT} statt einer Minute',
         '# (adorfer 20.09.2026). Eine Karte, die alle paar Minuten nachfuehrt,',
         '# ist immer noch aktueller als die meisten Freifunk-Karten.',
         f'synchronize = "{TAKT}"',
         f'collect_interval = "{TAKT}"',
         '']
    for x in d:
        t.append(f'[respondd.sites.{x["code"]}]')
        t.append("domains = ['']")
    t.append('')
    t.append('# Je batman-Instanz eine Abfrage. Ohne multicast_address nimmt yanic')
    t.append('# ff05::2:1001, und genau darauf antwortet Stock-Gluon auf br-client.')
    vorhanden = [x for x in d if x not in fehlen] if '--alle' not in sys.argv else d
    for x in vorhanden:
        t.append('')
        t.append(f'# {x["name"]}')
        t.append('[[respondd.interfaces]]')
        t.append(f'ifname = "bat-{x["code"]}"')
        if x['gem'] in ABFRAGE:
            t.append(f'multicast_address = "{ABFRAGE[x["gem"]]}"')

    t.append('')
    t.append('[webserver]')
    t.append('enable = false')
    t.append('')
    t.append('[nodes]')
    t.append('state_path = "/var/lib/yanic/state.json"')
    t.append('# Offline-Knoten bleiben ein Vierteljahr sichtbar, danach fallen sie raus.')
    t.append('prune_after = "90d"')
    t.append('save_interval = "1m"')
    t.append('# Muss deutlich groesser sein als collect_interval, sonst flackern')
    t.append('# Knoten nach einer einzigen verpassten Runde auf offline.')
    t.append(f'offline_after = "{OFFLINE}"')

    # Je Gemeinschaft eine Gesamtansicht und je Domain eine Ortsansicht. Die
    # Gesamtansicht filtert auf die site_codes genau dieser Gemeinschaft,
    # sonst lägen zwei Netze in einer Datei.
    for g in sorted({x['gem'] for x in d}):
        seine = [x for x in d if x['gem'] == g]
        t.append(ausgabe(f'{WEB}/{g}/alle/data', [x['code'] for x in seine],
                         f'{g}: alle {len(seine)} Domains, {g}.map.freifunk.space'))
        for x in seine:
            t.append(ausgabe(f'{WEB}/{g}/{x["host"]}/data', [x['code']],
                             f'{x["name"]}: {x["host"]}.{g}.map.freifunk.space'))

    # nodes.json/graph.json und nodelist.json nur fuer die Gesamtsicht: das
    # sind die Formate, die andere Karten und Verzeichnisse einlesen.
    # nodes.json/graph.json und nodelist.json je Gemeinschaft: das sind die
    # Formate, die andere Karten und Verzeichnisse einlesen.
    for g in sorted({x['gem'] for x in d}):
        codes = [x['code'] for x in d if x['gem'] == g]
        liste = '", "'.join(codes)
        t.append('')
        t.append('[[nodes.output.meshviewer]]')
        t.append('enable = true')
        t.append('version = 2')
        t.append(f'nodes_path = "{WEB}/{g}/alle/data/nodes.json"')
        t.append(f'graph_path = "{WEB}/{g}/alle/data/graph.json"')
        t.append('[nodes.output.meshviewer.filter]')
        t.append('no_owner = true')
        t.append(f'sites = ["{liste}"]')
        t.append('')
        t.append('[[nodes.output.nodelist]]')
        t.append('enable = true')
        t.append(f'path = "{WEB}/{g}/alle/data/nodelist.json"')
        t.append('[nodes.output.nodelist.filter]')
        t.append('no_owner = true')
        t.append(f'sites = ["{liste}"]')
    t.append('')
    t.append('[database]')
    t.append('delete_after = "90d"')
    t.append('delete_interval = "1d"')
    t.append('')
    t.append('[[database.connection.logging]]')
    t.append('enable = false')
    t.append('path = "/var/log/yanic.log"')
    t.append('')
    print('\n'.join(t))
    return 0


if __name__ == '__main__':
    sys.exit(main())
