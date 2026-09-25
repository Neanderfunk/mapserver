# Uebergabe

Was jemand wissen muss, der dieses Projekt uebernimmt oder fortfuehrt.

## Was es ist

Ein Kartenserver, der das Netz einer fremden Community misst und darstellt,
weil sie selbst keine Karte mehr hat. Erster und bisher einziger Fall ist
Freifunk EN mit acht Domains und rund 530 Knoten. Zugleich ist es der
Probelauf fuer einen aktuellen Kartenstapel, bevor die eigene Karte erneuert
wird.

Begonnen am 20.09.2026, an einem Abend von leerer VM bis oeffentlicher Karte.

## Maschinen und Zugaenge

| Was | Wo |
| --- | --- |
| Karten-VM | `map6.freifunk.space`, nur IPv6, Debian 13 |
| Zugang, Schluessel, sudo | im Betriebs-Repo der Supernode-Session, nicht in diesem oeffentlichen Repo |
| Proxy und TLS | `twin2.ffdus.de`, gepflegt von adorfer |
| Finder-VM (anderes Projekt) | `finder6.ffnef.de`, gleicher Schluessel |

Die VM ist ein Klon der Finder-VM. Reste davon sind entfernt (Crontab,
nginx-Schnipsel); `nullmailer` und der Checkmk-Agent sind noch da und
sinnvoll, sobald die Ueberwachung kommt.

## Namen

| Name | zeigt auf |
| --- | --- |
| `en.map.freifunk.space` | Gesamtkarte, alle acht Domains |
| `<ort>.en.map.freifunk.space` | acht Ortskarten |
| `map6.freifunk.space` | die VM selbst, Vorgabeseite mit der Liste |
| `map.freifunk.space` | **nicht dieses Projekt**, zeigt auf `map.eulenfunk.de` |

Das Schema ist `<community>.map.freifunk.space` fuer die Gesamtsicht und
`<ort>.<community>.map.freifunk.space` darunter, damit weitere
Communities danebenpassen.

Alle neun Namen stehen als SANs in einem Let's-Encrypt-Zertifikat auf twin2.
Ein Wildcard ist dort nicht noetig und waere ueber DNS-01 umstaendlicher.

## Aeussere Abhaengigkeiten

| Wovon | Wofuer | Wenn es ausfaellt |
| --- | --- | --- |
| `broker1.ff-en.de` | alle acht Tunnel | Karte friert ein, Knoten laufen nach fuenf Minuten auf offline |
| `tiles.ffdus.de` | Kartenkacheln | Karte bleibt grau, Knoten weiter sichtbar |
| `twin2.ffdus.de` | Name und TLS | von aussen nicht erreichbar, VM laeuft weiter |
| github.com, codeberg.org | nur beim Bauen | Betrieb unbetroffen |

Alles, was der Browser laedt, kommt von uns oder aus Duesseldorf. Keine
Anfragen an Dritte.

## Stand der Technik im Projekt

```
Debian 13 (trixie), Kernel 6.12.107
batman-adv 2024.2 (compat 15), batctl 2025.0
tunneldigger  Commit 9a9a427
yanic         v1.9.0 (codeberg.org/FreifunkBremen/yanic)
meshviewer    freifunk/meshviewer, Zweig main
node 20.19, nginx 1.26.3
```

`ffrgb/meshviewer` ist seit August 2023 archiviert und darf nicht mehr als
Quelle genommen werden. Das gepflegte Repository ist `freifunk/meshviewer`.
Das GitHub-Repository von yanic ist ebenfalls archiviert, die Entwicklung
liegt auf Codeberg. Als Referenzaufbau taugt `github.com/ffac/ff-supernode`,
die Ansible-Rollen von Freifunk Aachen.

## Verzeichnis im Projekt

```
tunnel/     Tunnelschicht: Domaintabelle, Hook, Starter, Unit, Einrichtung
sammler/    yanic: Konfigurationsgenerator, Unit, Einrichtung
web/        meshviewer: Konfigurations- und Vhost-Generator, Einrichtung
werkzeug/   site-lesen.py, domains-erzeugen.py, broker-probe.py, respondd-probe.py
docs/       diese Dokumentation
```

Alle erzeugten Dateien auf der VM (`/etc/yanic.conf`, die nginx-Site, die
neun `config.json`) sind Ergebnis, nicht Quelle. Wer sie von Hand aendert,
verliert die Aenderung beim naechsten Lauf. Quelle ist immer
`tunnel/domains.conf` plus die Generatoren.

## Was offen ist

- **Melder.** Die Checkmk-Local-Checks stehen (siehe betrieb.md), der Host
  muss in der Checkmk-Instanz noch angelegt werden. Eine Mailbenachrichtigung
  wie bei mitfunken gibt es hier noch nicht; `nullmailer` liegt bereit.
- **Zweite Community.** Vorbereitet, aber nicht belegt. Vorher sollten
  `/etc/karte-en` und `/var/www/karte-en` je Community benannt werden.
- **Andere VPN-Arten.** Die Tunnelschicht kann nur Tunneldigger. fastd
  braucht zusaetzlich eine Schluesselfreischaltung und geht damit nicht
  einseitig.
- **Gateways als Pseudoknoten.** Wuerde die blauen Uplink-Knoten bringen,
  erfindet aber Objekte. Bewusst offen gelassen.
- **broker2.ff-en.de.** Falls er zurueckkommt, verdoppelt sich die
  Ausfallsicherheit ohne Zutun.

## Wenn Freifunk EN sich meldet

Der Stand: sie sagen selbst, dass sie keine Karte haben und niemand Zeit hat,
das zu aendern. Gefragt haben wir nicht, weil es nach eigener Aussage nichts
zu entscheiden gaebe. Wir messen mit denselben Mitteln, die jedem Knoten in
ihrer Domain offenstehen, veroeffentlichen keine Kontaktdaten und geben uns
nicht als Gateway aus.

Wenn sie die Karte nicht wollen, ist das ihre Entscheidung, und acht
`systemctl disable --now` beenden es innerhalb einer Minute. Wenn sie sie
wollen, ist der naechste sinnvolle Schritt ein `ext-respondd` auf ihren
Supernodes: dann zeigt die Karte auch die Tunnel.

## Lizenz

BSD-3-Clause, siehe `LICENSE`. Fremde Bestandteile behalten ihre eigene
Lizenz: meshviewer ist AGPL-3.0, die Geraetebilder sind CC-BY-NC-SA 4.0.
