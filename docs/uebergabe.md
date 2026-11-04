# Uebergabe

Was jemand wissen muss, der dieses Projekt uebernimmt oder fortfuehrt.

## Was es ist

Der Nachfolger der Neanderfunk-Karte `map.eulenfunk.de` (HopGlass, abgeloest
am 04.11.2026) auf einem
aktuellen Stack, mit UniFi-APs, zusaetzlichen respondd-Werten und
Zeitreihen; dazu Not-Karten fuer Communities, die gerade keine
funktionierende Karte haben (fuer mitfunken.freifunk.space). Siehe README.

Begonnen am 20.09.2026 als Not-Karte fuer Freifunk EN, an einem Abend von
leerer VM bis oeffentlicher Karte. Freifunk EN hat eine eigene Karte
(`map.ff-en.de`), vermutlich schon zu diesem Zeitpunkt wieder; unsere ruht
und leitet dorthin um (`web/standby.conf`). Im Mittelpunkt steht
inzwischen die Karte der 48 Neanderfunk-Domains.

## Maschinen und Zugaenge

| Was | Wo |
| --- | --- |
| Karten-VM | `map6.freifunk.space`, nur IPv6, Debian 13 |
| Zugang, Schluessel, sudo | internes Repo `neanderfunk/ansible`, `docs/mapserver-interna/` (Supernode-Session), nicht in diesem oeffentlichen Repo |
| Proxy und TLS | `twin2.ffdus.de`, gepflegt von adorfer |
| Finder-VM (anderes Projekt) | `finder6.ffnef.de`, gleicher Schluessel |

Die VM ist ein Klon der Finder-VM. Reste davon sind entfernt (Crontab,
nginx-Schnipsel); `nullmailer` und der Checkmk-Agent sind noch da und
sinnvoll, sobald die Ueberwachung kommt.

## Namen

Eine Karte, ein Name (adorfer 04.11.2026): alles andere leitet per `301` um,
Pfad und Parameter bleiben erhalten. Ortskarten zum Ansehen gibt es fuer
Neanderfunk nicht mehr; ausgenommen sind nur LVR und die Ersatzkarten
(Essen, ruhend EN).

| Name | zeigt auf |
| --- | --- |
| `karte.neanderfunk.de` | Gesamtkarte der 48 Neanderfunk-Domains, kanonisch |
| `lvr.karte.neanderfunk.de` | Sammelkarte LVR-HPH, Domains 11 und 31 bis 36 |
| `map.ffnef.de` (bis 04.11.2026 abends kanonisch), `map.neanderfunk.de`, `karte.ffdus.de`, `map.ffdus.de`, `karte.ffnef.de`, `map1.ffdus.de`, `map.eulenfunk.de`, `map.freifunk-siegerland.de`, `map.gl.wupper.ffrl.de`, `map.leichlingen.freifunk.net` und alle Subdomains darunter | `301` auf `karte.neanderfunk.de` |
| `lvr.map.ffnef.de` (bis 05.11.2026 kanonisch), `lvr.karte.ffnef.de`, `lvr.map.eulenfunk.de`, `nef11lvr` und `nef31lvrno` bis `nef36lvrsw` unter `karte.neanderfunk.de`, `lvr.neander.map.freifunk.space` | `301` auf `lvr.karte.neanderfunk.de` |
| `<ort>.neander.map.freifunk.space` | fruehere Ortskarten, `301` auf `karte.neanderfunk.de` |
| `neander.map.freifunk.space` | seit 05.11.2026 `301` auf `karte.neanderfunk.de`, fuer `/nf/` und `/grafana/` `308`; Grafana, `/nf/` und das Service-Menue liegen unter `karte.neanderfunk.de` |
| `essen.map.freifunk.space` | Not-Karte Freifunk Essen |
| `en.map.freifunk.space`, `<ort>.en.map.freifunk.space` | ruhend, `301` auf `map.ff-en.de` |
| `map.freifunk.space`, `map6.freifunk.space` | Vorgabeseite mit der Kartenliste, darunter `/data/<community>/` |

Quelle der Namen und Umleitungen ist `web/namen.conf`, Sammelkarten stehen in
`sammler/gruppen.conf` (siehe betrieb.md).

Die alten Ortsnamen im Firmware-Bestand und in Verzeichnissen haengen an der
Domainnummer im ersten Namensteil (`nef06han`, `dusuk12`). Fuer
`/data/nodelist.json`, `nodes.json` und `graph.json` leiten sie deshalb auf
die Daten ihrer Domain um (`karte.neanderfunk.de/data/06_han/...`), nicht auf das ganze
Netz; sonst zaehlte jeder Ort bei den Freifunk-Aggregatoren alle Knoten.

**Proxy twin2** (adorfer), TLS endet dort:

| Datei auf twin2 | Namen | Zertifikat |
| --- | --- | --- |
| `map.conf` | `map.freifunk.space` und `*.map.freifunk.space` | `tiles.eulenfunk.de` (Sammelzertifikat) |
| `karte.conf` | die alten Namen oben, Subdomains per Wildcard | `karte.neanderfunk.de`, 84 Namen |
| `ortskarten.conf` | die 49 frueheren `<ort>.neander.map.freifunk.space` | `ortskarten-neander` |

- Zertifikate per HTTP-Pruefung (webroot `/var/www/letsencrypt`), ein
  Wildcard-Zertifikat ginge nur ueber DNS und ist bewusst nicht eingerichtet.
  Subdomains, die nicht im Zertifikat stehen, enden bei HTTPS im
  Zertifikatsfehler. Hoechstens 100 Namen je Zertifikat.
- Neue Namen findet `/var/log/nginx/karte-hosts.log` auf twin2 (Host in
  Spalte 3, Format `karte_host`); auswerten mit
  `awk '{print $3}' /var/log/nginx/karte-hosts.log | sort | uniq -c | sort -rn`,
  Namen mit nennenswert vielen Aufrufen per `certbot certonly --expand` dazu.
  Vorher pruefen, ob der Weg traegt: Probedatei unter
  `/.well-known/acme-challenge/` und von aussen ueber IPv4 und IPv6 abrufen;
  Staging von Let's Encrypt war am 04.11.2026 nicht erreichbar.
- `server_names_hash_bucket_size 128` in `conf.d/server-names-hash.conf`,
  sonst lehnt nginx die langen Ortsnamen ab.

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

## Was offen ist (Roadmap)

Naechste Schritte, die feststehen:

- **Host-Log auf twin2 auswerten**, ein paar Tage nach dem 04.11.2026. Namen
  mit nennenswert vielen Aufrufen ins Zertifikat `karte.neanderfunk.de`
  (84 von 100). Die vier `www.`-Namen vom 04.11. waren Scanner und bleiben
  draussen.
- **Verzeichnisse der abgeschalteten Ortskarten** (`sites/neander/<host>/`)
  liegen noch auf der VM, werden aber nicht mehr ausgeliefert. Loeschen nur
  auf Zuruf.
- **Essen:** der Finder liest kuenftig `map.freifunk.space/data/essen/`
  statt der Subdomain (Mitfunken-Session).
- **Multidomain-Firmware:** Grafana waehlt Domains heute ueber `site`; mit
  der Multidomain-Firmware kommen `domain_as_site` und `domainNames` nach den
  site_codes.

Bekannt und bewusst so:

- **Wuppertal** (`wup.map.eulenfunk.de`, `map.freifunk-wuppertal.net`) faellt
  weg, bis Freifunk Wuppertal sich meldet; die Namen haben kein Zertifikat.
- **Melder.** Die Checkmk-Local-Checks stehen (siehe betrieb.md), der Host
  muss in der Checkmk-Instanz noch angelegt werden. Eine Mailbenachrichtigung
  wie bei mitfunken gibt es hier noch nicht; `nullmailer` liegt bereit.
- **Mehrere Communities** laufen seit 22.09.2026 nebeneinander (neander,
  essen; en ruhend). Die Pfade heissen weiter `/etc/karte-en` und
  `/var/www/karte-en`, gemeint ist aber alles; umbenennen waere nur Kosmetik.
- **VPN-Arten:** Tunneldigger und fastd (seit 25.09.2026, `tunnel/fastd.conf`).
  WireGuard fehlt noch. fastd geht einseitig nur, wenn die Gegenseite jeden
  Schluessel annimmt (Essen); sonst per Anmeldung (Hildesheim, 26.09.2026
  beantragt).
- **Gateways als Pseudoknoten.** Wuerde die blauen Uplink-Knoten bringen,
  erfindet aber Objekte. Bewusst offen gelassen.
- **broker2.ff-en.de.** Falls er zurueckkommt, verdoppelt sich die
  Ausfallsicherheit ohne Zutun.

## Freifunk EN (ruhend)

Freifunk EN betreibt eine eigene Karte, `map.ff-en.de`. Unsere EN-Karte
ruht: Tunnel und `yanic@en` sind abgeschaltet, aber nicht deinstalliert, und
alle EN-Namen leiten per `301` dorthin um (`web/standby.conf`, siehe
`docs/betrieb.md`). Die Zeile dort zu entfernen holt alles zurueck.

Gemessen hatten wir mit denselben Mitteln, die jedem Knoten in ihrer Domain
offenstehen, ohne Kontaktdaten zu veroeffentlichen und ohne uns als Gateway
auszugeben.

## Lizenz

BSD-3-Clause, siehe `LICENSE`. Fremde Bestandteile behalten ihre eigene
Lizenz: meshviewer ist AGPL-3.0, die Geraetebilder sind CC-BY-NC-SA 4.0.
