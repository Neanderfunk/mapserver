# mapserver

Kartenserver für Freifunk, betrieben von Freifunk Neanderland.

**Worum es geht:** Die Karten-Infrastruktur wird erneuert. Die bisherige Karte
der Neanderfunk-Domains (`map.eulenfunk.de`) läuft auf einem in die Jahre
gekommenen HopGlass-Stack. Dieses Repo baut den Nachfolger mit aktuellen
Werkzeugen und bringt Dinge mit, die der alte Stack nicht kann:

- UniFi-Accesspoints als eigene Knoten auf der Karte, an ihrem Freifunk-Router
  und ohne doppelt gezählte Clients ([docs/unifi-sites.md](docs/unifi-sites.md)),
- zusätzliche respondd-Werte aus dem Gluon-Paket `neanderfunk-respondd`
  (Speicherdruck, Kanäle, Offline-Zähler und mehr),
- Zeitreihen für jeden Knoten, direkt im Knotenfenster der Karte, dazu
  Grafana für lange Zeiträume und eine Gesamtsicht der Community,
- Schnittstellen für andere, etwa die Adressen je Knoten
  (`/nf/targets.json`).

**Der Aufhänger:** eine Not-Karte für Communities, die gerade keine
funktionierende Karte haben, gedacht für
[mitfunken.freifunk.space](https://mitfunken.freifunk.space) ("Freifunk in
deiner Nähe"). respondd ist so gebaut, dass jeder Knoten einer Domain fragen
darf und die Antwort per Unicast zurückkommt: mehrere Karten nebeneinander
sind im Freifunk der Normalfall, nicht der Sonderfall. Hat eine Community
wieder eine eigene Karte, ruht unsere und leitet dorthin weiter.

## Stand

- `neander.map.freifunk.space`: alle 48 Neanderfunk-Domains in einer Karte,
  samt UniFi-APs, Diagrammen und Grafana unter `/grafana/`.
- Ortskarten `<ort>.neander.map.freifunk.space` sind gebaut und kommen mit dem
  Umzug, wenn diese Karte `map.eulenfunk.de` ablöst.
- Not-Karten: Freifunk Essen (`essen.map.freifunk.space`, per fastd).
  Einbeck und Hildesheim sind in Vorbereitung.
- `map.freifunk.space` zeigt bis dahin auf `map.eulenfunk.de` und wird hier
  nicht angefasst.

## Stack

| Schicht | Wahl | Bemerkung |
| --- | --- | --- |
| Tunnel | `wlanslovenija/tunneldigger`, C-Client, oder fastd | eine Instanz je Domain |
| Mesh | batman-adv aus dem Kernel (compat 15) | `bat-<code>`, `gw_mode off` |
| Collector | yanic, Fork [Neanderfunk/yanic](https://github.com/Neanderfunk/yanic) | ein Prozess je Community |
| Karte | meshviewer, Fork [Neanderfunk/meshviewer](https://github.com/Neanderfunk/meshviewer) | Upstream `freifunk/meshviewer` |
| UniFi | unifi_respondd, Fork [Neanderfunk/unifi_respondd](https://github.com/Neanderfunk/unifi_respondd) | Upstream `freifunkMUC/unifi_respondd` |
| Zeitreihen | VictoriaMetrics, Grafana | nur lokal erreichbar, nach außen über nginx |
| Eigene Antwort | `ffnord/mesh-announce`, wie auf den Supernodes | map6 selbst als Knoten `map-neanderfunk-<code>` in jedem Mesh |

Die Forks tragen je Funktion einen Commit auf einem Upstream-Stand, erklärt in
`NEANDERFUNK.md` im jeweiligen Fork. Referenz für den Aufbau war
`github.com/ffac/ff-supernode`, die Ansible-Rollen von Freifunk Aachen.

## Haltung

In fremden Netzen sind wir ein Knoten, der fragt, und sonst nichts:

- kein `gw_mode`, keine Clients, kein DHCP, kein Forwarding,
- keine Adresse aus ihren Präfixen, Link-Local genügt für respondd,
- `accept_ra` und `autoconf` aus, damit uns ihre Gateways nichts zuweisen,
- feste, lokal verwaltete MACs und ein sprechender Name am Broker
  (`map-neanderfunk-<code>`), damit wir zuzuordnen sind,
- `no_owner = true`: die Kontaktdaten ihrer Knotenbetreiber sind nicht für
  unsere Veröffentlichung gedacht.

Im eigenen Netz zeigen wir die Kontaktangabe, wie es das Pico Peering
Agreement vorsieht ([docs/hintergrund.md](docs/hintergrund.md)).

## Dokumentation

- [docs/einrichtung.md](docs/einrichtung.md) - von der leeren VM zur Karte
- [docs/betrieb.md](docs/betrieb.md) - was läuft, wie man prüft, was schiefgeht
- [docs/unifi-sites.md](docs/unifi-sites.md) - UniFi-Accesspoints auf der Karte
- [docs/neue-community.md](docs/neue-community.md) - von ihren Images zur
  Domaintabelle, samt Übergabeformat
- [docs/kartenausfall-diagnose.md](docs/kartenausfall-diagnose.md) - wenn die
  Karte einer Community leer bleibt: Schicht für Schicht, mit den Fallen, die
  uns Zeit gekostet haben
- [docs/hintergrund.md](docs/hintergrund.md) - Entscheidungen und Besonderheiten
- [docs/uebergabe.md](docs/uebergabe.md) - Abhängigkeiten, offene Punkte

Die Anleitung für Betreuende von UniFi-Installationen ist öffentlich in
[freifunk-docs](https://github.com/Neanderfunk/freifunk-docs/blob/main/unifi-accesspoints-freifunk-karte.md).

## Verzeichnisse

- `tunnel/` - Tunnelschicht: Domaintabelle, Hook, Starter, Wächter,
  Unit-Vorlagen, Einrichtungsskript
- `sammler/` - yanic und was daneben sammelt: Konfigurationsgeneratoren,
  Adressbuch, Clientzählung, UniFi, Units, Einrichtungsskripte
- `web/` - meshviewer: Konfigurations- und Vhost-Generator, eigenes CSS,
  Einrichtungsskript
- `zeitreihe/` - VictoriaMetrics und Grafana samt Dashboard-Generator
- `checkmk/` - Local Checks für die Überwachung
- `vm/` - Dateien der Maschine außerhalb des Projekts, die den Betrieb
  entscheiden
- `werkzeug/` - Werkzeuge ohne Installation: `site-lesen.py` liest die
  site.json aus fremden Images, `domains-erzeugen.py` macht daraus die
  Domaintabelle, `broker-probe.py` und `respondd-probe.py` prüfen die beiden
  Schichten einzeln, `unifi-offloader.py` misst den Router je UniFi-AP
