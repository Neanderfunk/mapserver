# mapserver

Aufbau eines eigenen Freifunk-Kartenservers, erster Anwendungsfall ist
**Freifunk EN** (Ennepe-Ruhr-Kreis und Umgebung).

Freifunk EN betreibt acht getrennte Gluon-Domains, hat aber seit dem Ende von
`map.ff-en.de` keine Karte mehr und nach eigener Aussage niemanden, der das
ändern könnte. Respondd ist so gebaut, dass jeder Knoten einer Domain fragen
darf und die Antwort per Unicast zurückkommt: mehrere Karten nebeneinander
sind im Freifunk der Normalfall, nicht der Sonderfall. Also bauen wir eine.

Zugleich ist das der Probelauf für einen aktuellen Kartenstapel, bevor wir
unsere eigene Karte erneuern.

## Stapel

| Schicht | Wahl | Bemerkung |
| --- | --- | --- |
| Tunnel | `wlanslovenija/tunneldigger`, C-Client | acht Instanzen, eine je Domain |
| Mesh | batman-adv aus dem Kernel (compat 15) | `bat-<code>`, `gw_mode off` |
| Sammler | yanic, `codeberg.org/FreifunkBremen/yanic` | ein Prozess, acht Abfrage-Schnittstellen |
| Karte | `github.com/freifunk/meshviewer`, Branch `main` | `ffrgb/meshviewer` ist seit 2023 archiviert |

Referenz für den Aufbau ist `github.com/ffac/ff-supernode`, die Ansible-Rollen
von Freifunk Aachen. Dort steht produktiv, wie yanic und meshviewer aktuell
zusammengesetzt werden.

## Haltung

Wir sind in ihren Domains ein Knoten, der fragt, und sonst nichts:

- kein `gw_mode`, keine Clients, kein DHCP, kein Forwarding,
- keine Adresse aus ihren Präfixen, Link-Local genügt für respondd,
- `accept_ra` und `autoconf` aus, damit uns ihre Gateways nichts zuweisen,
- feste, lokal verwaltete MACs und ein sprechender Name am Broker
  (`map-neanderfunk-<code>`), damit wir zuzuordnen sind,
- `no_owner = true` in allen yanic-Ausgaben: die Kontaktdaten ihrer
  Knotenbetreiber sind nicht für unsere Veröffentlichung gedacht.

## Dokumentation

- [docs/einrichtung.md](docs/einrichtung.md) - von der leeren VM zur Karte
- [docs/betrieb.md](docs/betrieb.md) - was läuft, wie man prüft, was schiefgeht
- [docs/neue-community.md](docs/neue-community.md) - von ihren Images zur
  Domaintabelle, samt Übergabeformat
- [docs/kartenausfall-diagnose.md](docs/kartenausfall-diagnose.md) - wenn die Karte einer
  Community leer bleibt: Schicht für Schicht, mit den Fallen, die uns Zeit
  gekostet haben
- [docs/hintergrund.md](docs/hintergrund.md) - Entscheidungen und Besonderheiten
- [docs/uebergabe.md](docs/uebergabe.md) - Zugänge, Abhängigkeiten, offene Punkte

## Verzeichnisse

- `tunnel/` - Tunnelschicht: Domaintabelle, Hook, Starter, Unit-Vorlage,
  Einrichtungsskript für root
- `sammler/` - yanic: Konfigurationsgenerator, Unit, Einrichtungsskript
- `web/` - meshviewer: Konfigurations- und Vhost-Generator, Einrichtungsskript
- `werkzeug/` - Werkzeuge ohne Installation: `site-lesen.py` liest die
  site.json aus fremden Images, `domains-erzeugen.py` macht daraus die
  Domaintabelle, `broker-probe.py` und `respondd-probe.py` prüfen die beiden
  Schichten einzeln

## Zielnamen

Die VM ist `map6.freifunk.space`, extern später über twin2 erreichbar:

- `en.map.freifunk.space` - alle acht Domains in einer Karte
- `enkreis`, `ennepetal`, `sprockhoevel`, `hattingen`, `witten`, `wetter`,
  `hagen`, `refugee` jeweils als `<name>.en.map.freifunk.space`

`map.freifunk.space` zeigt derzeit auf `map.eulenfunk.de`, also auf die
bestehende Neanderfunk-Karte, und bleibt hier unangetastet.
