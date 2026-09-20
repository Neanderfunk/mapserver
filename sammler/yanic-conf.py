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
import sys

KONF = '/etc/karte-en/domains.conf'
WEB = '/var/www/karte-en/sites'
# Abfragetakt und Offline-Schwelle. Bewusst schonender als ueblich, siehe
# Begruendung im erzeugten Kopf.
TAKT = '5m'
OFFLINE = '20m'


def domains(pfad):
    for z in open(pfad, encoding='utf-8'):
        z = z.strip()
        if not z or z.startswith('#'):
            continue
        t = z.split(None, 7)
        if len(t) < 8:
            continue
        yield {'code': t[0], 'ordner': t[1], 'port': t[2], 'id': t[3],
               'host': t[4], 'prefix6': t[5], 'prefix4': t[6], 'name': t[7]}


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
    for x in d:
        t.append('')
        t.append(f'# {x["name"]}')
        t.append('[[respondd.interfaces]]')
        t.append(f'ifname = "bat-{x["code"]}"')

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

    t.append(ausgabe(f'{WEB}/alle/data', None, 'Alle acht Domains zusammen: en.map.freifunk.space'))
    for x in d:
        t.append(ausgabe(f'{WEB}/{x["host"]}/data', [x['code']],
                         f'{x["name"]}: {x["host"]}.en.map.freifunk.space'))

    # nodes.json/graph.json und nodelist.json nur fuer die Gesamtsicht: das
    # sind die Formate, die andere Karten und Verzeichnisse einlesen.
    t.append('')
    t.append('[[nodes.output.meshviewer]]')
    t.append('enable = true')
    t.append('version = 2')
    t.append(f'nodes_path = "{WEB}/alle/data/nodes.json"')
    t.append(f'graph_path = "{WEB}/alle/data/graph.json"')
    t.append('[nodes.output.meshviewer.filter]')
    t.append('no_owner = true')
    t.append('')
    t.append('[[nodes.output.nodelist]]')
    t.append('enable = true')
    t.append(f'path = "{WEB}/alle/data/nodelist.json"')
    t.append('[nodes.output.nodelist.filter]')
    t.append('no_owner = true')
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
