# Betrieb

## Was läuft

| Einheit | Zweck |
| --- | --- |
| `karte-en-tunnel@<code>.service` | ein Tunneldigger-Client je Domain, acht Stück |
| `yanic.service` | fragt alle bat-Instanzen ab, schreibt die JSON-Dateien |
| `nginx.service` | liefert Build, Konfiguration und Daten aus |

Es gibt keinen Timer und keinen Cron. yanic sammelt im Takt von
`collect_interval` (eine Minute) und schreibt alle 30 Sekunden.

## Wo was liegt

```
/etc/karte-en/domains.conf              Domaintabelle, einzige Quelle
/etc/yanic.conf                         erzeugt, nicht von Hand pflegen
/etc/modules-load.d/karte-en.conf       l2tp_eth, l2tp_netlink, batman-adv
/etc/nginx/sites-available/karte-en.conf erzeugt
/usr/local/bin/tunneldigger             C-Client
/usr/local/bin/yanic                    Collector
/usr/local/sbin/karte-en-tunnel         Starter je Domain
/usr/local/sbin/karte-en-hook           Hook, hängt Tunnel an batman
/usr/local/sbin/karte-en-yanic-conf     erzeugt /etc/yanic.conf
/usr/local/sbin/karte-en-konfig         erzeugt config.json und nginx-Site
/usr/local/src/{tunneldigger,yanic,meshviewer,device-pictures}
/var/lib/yanic/state.json               Zwischenstand, überlebt Neustarts
/var/www/karte-en/meshviewer            gemeinsamer Build
/var/www/karte-en/pictures-svg          Gerätebilder
/var/www/karte-en/sites/<host>/config.json
/var/www/karte-en/sites/<host>/data/meshviewer.json
/var/www/karte-index/index.html         Vorgabeseite unter dem VM-Namen
```

Für die Gesamtsicht schreibt yanic zusätzlich `nodes.json` (Version 2),
`graph.json` und `nodelist.json` in `sites/alle/data/`. Das sind die Formate,
die andere Karten und Verzeichnisse einlesen.

## Gesundheitsprüfung

Von unten nach oben, jede Stufe einzeln:

```bash
# 1. Tunnel: acht Dienste, acht L2TP-Schnittstellen
systemctl list-units 'karte-en-tunnel@*' --no-legend
ip -br link show | grep '^td-'

# 2. Mesh: je Domain ein Nachbar (der Broker) und viele Originatoren
for c in $(awk '!/^#/ && NF {print $1}' /etc/karte-en/domains.conf); do
  printf '%-7s %4s Originatoren  %s Nachbarn\n' "$c" \
    "$(batctl meshif bat-$c originators | tail -n +3 | grep -c .)" \
    "$(batctl meshif bat-$c neighbors | tail -n +3 | grep -c .)"
done

# 3. Adressen: je Instanz eine aus ihrem Präfix, kein Standardweg von ihnen
ip -6 -br addr show | grep '^bat-'
ip -6 route show proto ra        # muss leer bleiben
ip -6 route show default         # nur die eigene Uplink-Schnittstelle

# 4. Collector
systemctl status yanic --no-pager
journalctl -u yanic -n 30

# 5. Daten: Alter und Knotenzahl
for f in /var/www/karte-en/sites/*/data/meshviewer.json; do
  printf '%-52s %3s min alt\n' "$f" "$(( ($(date +%s) - $(stat -c %Y "$f")) / 60 ))"
done
```

Eine frische Datei ist nie älter als eine Minute. Alles darüber heißt, dass
yanic nicht schreibt.

## Typische Störungen

**IPv6-Nachbartabelle voll.** Kernel: "neighbor table overflow!", Dienste
scheitern bei `sendto` mit Errno 22 (EINVAL). Mit der Debian-Vorgabe
(`gc_thresh3` 1024) geschah das am 25.09.2026 in jeder Sammelrunde,
unifi-respondd stürzte alle fünf Minuten ab. Seitdem `vm/sysctl-neighbours.conf`
(16384). Prüfen: `journalctl -k | grep -c "neighbor table overflow"`,
`sysctl net.ipv6.neigh.default.gc_thresh3`.

**Eine Domain verschwindet aus der Karte.** Meist der Tunnel. `systemctl
status karte-en-tunnel@<code>` und `journalctl -u karte-en-tunnel@<code>`.
Der Client wiederholt von selbst, `Restart=always` mit 15 Sekunden Abstand.
Bleibt es dabei, prüfen, ob der Broker auf dem Port überhaupt antwortet:

```bash
werkzeug/broker-probe.py            # liest /etc/karte-en/domains.conf
```

**Alle Domains gleichzeitig weg.** Dann ist der Broker oder unser
Internetzugang das Problem, nicht acht Tunnel auf einmal.

**Tunnel steht, aber keine Originatoren.** Das L2TP-Interface hängt nicht am
batman. Der Hook hat versagt oder wurde nicht gerufen:
`journalctl -t karte-en`. Heilt durch `systemctl restart karte-en-tunnel@<code>`.

**Originatoren da, aber keine Knoten in der Ausgabe.** Dann kommt die
respondd-Antwort nicht durch. Von Hand nachstellen:

```bash
werkzeug/respondd-probe.py bat-ffha
```

Antwortet dort etwas und yanic nicht, liegt es an `/etc/yanic.conf`
(Schnittstellenname falsch) oder an Rechten.

**Originatoren da, Probe antwortet, yanic sammelt trotzdem nichts.** Der
Collector hängt an einer Schnittstelle, die es nicht mehr gibt:

```bash
ss -uanp | grep yanic | grep '%if[0-9]'
```

Jede Zeile ist eine stumme Domain. Der Wächter startet den Collector dann
innerhalb von fünf Minuten neu; von Hand `systemctl restart yanic@<community>`.
Hintergrund in [kartenausfall-diagnose.md](kartenausfall-diagnose.md).

**Karte lädt, bleibt aber leer.** Browserkonsole ansehen. Meist ist es
`config.json` oder `data/meshviewer.json`, beide müssen unter dem Vhost-Namen
200 liefern:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: witten.en.map.freifunk.space' \
  http://[::1]/data/meshviewer.json
```

**Standardweg zeigt plötzlich in ihr Netz.** Sollte nicht vorkommen, wäre aber
ernst: dann routet eigener Verkehr durch ihr Mesh. `ip -6 route show proto ra`
und die sysctl-Werte auf den bat-Instanzen prüfen, siehe `hintergrund.md`.

## fastd-Domains

Seit 25.09.2026 kann der Tunnel-Layer außer Tunneldigger auch fastd, erste
Community ist Freifunk Essen (Not-Karte für mitfunken.freifunk.space).

- **Wo es steht:** `tunnel/fastd.conf` (je Domain Methoden und Peers mit
  Schlüssel), Port und MTU wie gehabt in `tunnel/domains.conf`. Steht eine
  Domain in beiden, startet `karte-en-tunnel@<code>` fastd statt
  Tunneldigger. Interface `td-<code>`, Hook, batman-Instanz und Watchdog sind
  dieselben.
- **Unser Schlüssel:** je Community einer, `/etc/karte-en/fastd/<community>.secret`
  (0600, von `tunnel/einrichten.sh` einmalig erzeugt), der öffentliche Teil
  in `<community>.pub`. Er ist unsere Kennung dort: eine Sperrliste (Essen)
  oder eine Freischaltung (Hildesheim) hängt daran. Nie neu erzeugen, ohne
  das mit der Community abzustimmen.
- **Konfiguration:** entsteht bei jedem Start im RuntimeDirectory der Unit,
  der geheime Schlüssel nur per `include`. Prüfen:
  `fastd --verify-config --config /run/karte-en-tunnel-<code>/fastd.conf`.
- **Verbunden?** `journalctl -u karte-en-tunnel@<code>` zeigt
  "connection with <peer> established". Das Interface `td-<code>` gibt es bei
  fastd auch ohne Verbindung; der Watchdog merkt einen stummen fastd also
  nicht, die Domain-Checks in Checkmk schon (keine Originatoren).
- **Abfragegruppe:** je Community in `sammler/yanic-conf.py` (`ABFRAGE`).
  Essen antwortet nur auf `ff02::2:1001` (36 Knoten), auf `ff05::2:1001`
  nur der Supernode.

**Auf Freischaltung warten (Hildesheim, seit 26.09.2026):** Die Domain läuft
ganz normal; fastd versucht den Handshake wie jeder Gluon-Knoten laufend von
selbst, abgelehnt werden kostet nichts. Bis zur Freischaltung steht sie in
`tunnel/ruhend.conf` mit einer Begründung, die mit `WARTET` beginnt. Checkmk
meldet dann OK, solange nichts verbunden ist, und WARN, sobald der Tunnel
einen Nachbarn hat. Dann: Zeile aus `ruhend.conf` nehmen, Abfragegruppe
messen (vorläufig `ff02::2:1001`), Erstsichtung der map6-Knoten nachziehen.

Achtung: `tunnel/einrichten.sh` schaltet am Ende die Tunnel **aller**
Domains ein, auch ruhender Communities (EN). Neue Domains deshalb einzeln
einspielen (Dateien installieren, `systemctl enable --now karte-en-tunnel@<code>`).

## Der Kartenserver als Knoten (mesh-announce)

Seit 26.09.2026 beantwortet map6 respondd in jedem Mesh, in dem er hängt,
auch für sich selbst. Vorher war er für andere Karten ein "dunkler Knoten":
batman-Originator ohne Namen und Kontakt (adorfer: "nicht dass ausgerechnet
wir für andere ein dunkler Knoten sind").

- **Dienst:** `mesh-announce.service`, ffnord/mesh-announce auf festem Commit
  in `/opt/mesh-announce` (dasselbe wie auf den Supernodes), eingerichtet mit
  `sammler/mesh-announce-einrichten.sh`. Läuft als root, weil batctl die
  Nachbarn nur root zeigt, sonst eingesperrt.
- **Was er meldet:** je aktiver batman-Instanz einen Knoten
  `map-neanderfunk-<code>`, Kontakt `projekt@neanderfunk.de`, Modell
  "Kartenserver (VM)", `vpn: false`, den Tunnel als Mesh-Interface und den
  Supernode als batman-Nachbarn. Ruhende Communities (EN) nicht.
- **Konfiguration:** bei jedem Start aus `domains.conf`
  (`karte-mesh-announce-conf`). mesh-announce tritt den Multicast-Gruppen nur
  beim Start bei; der Watchdog startet ihn neu, wenn Domains dazukommen oder
  einer batman-Instanz die Gruppe `ff02::2:1001` fehlt.
- **Port 1001** teilt er sich mit unifi-respondd, beide mit `SO_REUSEADDR`.
  Multicast-Anfragen bekommen beide, eine Unicast-Nachfrage nur einer; yanic
  fragt per Unicast nur nach, wer auf den Multicast der Runde nicht
  geantwortet hat, das kostet also höchstens eine Runde.

## Service-Menü (hinter Anmeldung)

Seit 26.09.2026, nur für die neander-Karte: ein kleines Zahnrad neben dem
Knotennamen im Knotenfenster führt auf
`https://neander.map.freifunk.space/nf/service/?node=<node_id>`, auch von den
Ortskarten aus. Ohne Anmeldung geht es zu Authentik (idm.ffnef.de,
Application `neanderfunk-mapserver`, Proxy-Provider "Neanderfunk Map",
Forward auth single application, Embedded Outpost); wer darf, regelt die
Bindung an der Application.

- **Offline-Knoten sofort entfernen:** legt einen Löschauftrag an; yanic
  entfernt den Knoten beim nächsten Speichern (spätestens nach einer Minute)
  aus seinem Zustand, nur wenn er offline ist. Kein dauerhafter Eintrag:
  meldet er sich wieder, erscheint er neu. Ein Koordinaten-Override für ihn
  bleibt dabei bestehen.
- **Koordinaten-Override:** an eine Stelle rücken, von der Landkarte nehmen
  (`location: null`), aufheben. Als Alias im Format von hopglass-server in
  `/var/lib/karte/service/aliases-neander.json`; von Hand ergänzbar, etwa um
  Namen zu überschreiben. yanic lädt die Datei jede Minute nach.
- **Protokoll:** `/var/lib/karte/service/protokoll.jsonl`, je Aktion Zeit,
  Authentik-Benutzer, Knoten.
- **Technik:** `service/service.py` (127.0.0.1:8097, `karte-service.service`,
  Benutzer `karte-service`, Gruppe `yanic`), eingerichtet mit
  `service/einrichten.sh`; nginx-Teil in `web/konfig-erzeugen.py` (`SERVICE`);
  yanic-Schlüssel `aliases_path` und `remove_dir` für neander in
  `sammler/yanic-conf.py`; Zahnrad im meshviewer-Fork (`serviceLink`).
  Den Benutzer setzt nur nginx (`X-Service-User`), POST nur mit Origin der
  Karte.

## Eine Community in den Standby nehmen

Wenn eine Community wieder selbst eine Karte betreibt, brauchen wir ihr Netz
nicht mehr mitzumessen. Der Aufbau bleibt vollständig stehen, er hört nur auf
zu arbeiten, und ihre Namen leiten dauerhaft auf ihre eigene Karte um.

Geschaltet wird das in **`web/standby.conf`**, eine Zeile je Community:

```
en   https://map.ff-en.de/   Freifunk EN betreibt eine eigene Karte
```

Daraus folgt alles Weitere: `karte-en-konfig` erzeugt für alle Namen dieser
Community statt einer Karte einen `301` auf das Ziel, die Startseite führt sie
nicht mehr auf, und beide Checks überspringen sie. Der Web-Check prüft dann,
dass die Umleitung steht; ein `200` wäre dort der Fehler.

```bash
# 1. Zeile in standby.conf eintragen und ausspielen
sudo install -m 0644 web/standby.conf /etc/karte-en/standby.conf

# 2. Dienste anhalten (Tunnel und Collector bleiben installiert)
for c in $(awk '!/^#/ && NF && $1 == "en" { print $2 }' /etc/karte-en/domains.conf); do
    sudo systemctl disable --now "karte-en-tunnel@$c"
done
sudo systemctl disable --now yanic@en
# EN hat einen eigenen Unicast-Zielsucher (karte-ziele, nur fuer en); beim
# Standby am 23.09.2026 uebersehen, scheiterte nach dem Neustart am 25.09.
sudo systemctl disable --now karte-ziele.timer

# 3. Vhosts neu erzeugen
sudo /usr/local/sbin/karte-en-konfig
sudo nginx -t && sudo systemctl reload nginx
```

Zurückholen heißt: Zeile aus `standby.conf` entfernen, `karte-en-konfig`
laufen lassen, die Dienste wieder `enable --now`. Die Domaintabelle bleibt
dabei unangetastet, und die Daten unter `sites/<community>/` liegen weiter da.

Vorher zu klären, weil es an anderer Stelle weh tut: **wer unsere Karte als
Datenquelle liest**, verliert sie. Bei mitfunken steht sie in der
`initiativen.yaml` unter `daten:`; dort gehört dann die eigene Karte der
Community unter `quellen.karte` hinein, und zwar bevor hier abgeschaltet wird,
sonst steht die Community dort für einen Lauf ohne Daten da.

Die Zeitreihe in `/var/lib/karte/verlauf.csv` bleibt erhalten und ist der
Grund, warum sich das Abschalten lohnt statt des Löschens: sie dokumentiert,
was das Netz getan hat, solange wir hingesehen haben.

**Stand 26.09.2026:** Freifunk EN ist im Standby, acht Tunnel, der Collector
`yanic@en` und `karte-ziele.timer` sind abgeschaltet, neun Namen leiten auf
`map.ff-en.de` um. Es laufen 48 Tunnel für Neanderfunk, einer für Essen und einer für Hildesheim (wartet auf Freischaltung).

## Überwachung

Die Checks liegen in `checkmk/` und werden von dort ausgespielt
(`sudo ./installieren.sh 'mapserver*'`). Auf der VM:

```
/usr/lib/check_mk_agent/local/mapserver             jeder Agentenlauf
/usr/lib/check_mk_agent/local/60/mapserver-domains  jede Minute, im Hintergrund
/usr/lib/check_mk_agent/local/300/mapserver-web     alle fünf Minuten
```

`mapserver` und `60/mapserver-domains` sind **dieselbe Datei** und erkennen am
eigenen Namen, welche Rolle sie haben. Im Repo ist die zweite ein Verweis auf
die erste, `installieren.sh` kopiert beide. Die 48 Domain-Checks kosten rund
190 `batctl`-Aufrufe und ändern sich langsam; im Vordergrund ließen sie den
Agentenlauf auf fast 8 Sekunden wachsen, und der Host flackerte im Dashboard.

Laufzeiten, gemessen am 24.09.2026:

| | vorher | nachher |
| --- | --- | --- |
| `mapserver` je Lauf | 5,8 s | 0,96 s |
| `60/mapserver-domains`, im Hintergrund | (war im Vordergrund) | 1,8 s |
| ganzer Agent | 7,8 s | 3,0 s |

Neben der Trennung wurde der Check selbst billiger: je Tunnel drei
`systemctl`-Aufrufe und je Kartendatei ein eigener Python-Start sind durch je
einen Sammelaufruf ersetzt. Wer hier etwas ergänzt: **keine Programmstarts in
Schleifen über Domains oder Tunnel**, das summiert sich bei 48 Domains
schnell auf Sekunden.

Beide lassen sich von Hand aufrufen und geben ihre Zeilen direkt aus.

| Dienst | schlägt an, wenn |
| --- | --- |
| `mapserver-Tunnel` | eine der acht Instanzen nicht aktiv ist, oder über 20 Neustarts |
| `mapserver-Sammler` | yanic steht, die Ausgabe altert oder niemand mehr online ist |
| `mapserver-Abschottung` | eine RA-Route auftaucht, ein Standardweg über bat führt oder Forwarding an ist |
| `mapserver-Batman` | weniger L2TP-Schnittstellen da sind als Domains |
| `mapserver-EN-<ort>` | kein Nachbar, keine Originatoren, kein Gateway oder alte Datei |
| `mapserver-nginx-konfig` | `nginx -t` scheitert; der laufende nginx merkt das erst beim Neustart |
| `mapserver-adressbuch-<community>` | `targets.json` älter als 7 bzw. 15 Minuten oder leer |
| `mapserver-zeitreihe` | VictoriaMetrics antwortet nicht, keine frischen Werte, oder die Platte wird knapp |
| `mapserver-kennung` | eine bat- oder td-Schnittstelle nicht die MAC aus dem Schema trägt |
| `mapserver-Web` | eine der neun Karten oder ihre Daten nicht mit 200 antworten |

Die aussagekräftigste Größe je Domain sind die **Originatoren**, nicht die
Knotenzahl: sie fällt in dem Moment, in dem der Tunnel abreißt, während die
Knoten noch fünf Minuten lang als online in der Datei stehen.

`mapserver-Abschottung` ist kein Betriebswert, sondern eine Zusicherung. Wenn
dort etwas anderes als OK steht, läuft möglicherweise eigener Verkehr durch
ein fremdes Netz, siehe [hintergrund.md](hintergrund.md).

Nicht überwacht wird von hier aus der Weg von außen, also Proxy und
Zertifikat auf twin2. Das gehört in einen Check dort.

## Schnittstellen für andere

Beides lesend, ohne Anmeldung, dual-stack über den Proxy auf twin2. Genutzt
von der Paketfeed-Session (nfcollect, Release-Abnahme).

### Adressbuch

`https://neander.map.freifunk.space/nf/targets.json`, node_id auf aktuelle
Adressen. Die node_id bleibt, das öffentliche Präfix wandert mit dem
Supernode.

```
{"generated": "...Z", "source": "...Z", "community": "neander",
 "nodes": {"<node_id>": {"hostname", "site_code", "domain",
                         "addresses": [öffentlich..., ULA...],
                         "last_seen": "...Z", "online": true}}}
```

- `site_code` wie gemeldet (`nef-10_wlf`, `..._EOL`), `domain` normalisiert
  über `sitecodes.conf`. Supernodes melden nur `domain_code` (`ffnefd01`).
- Erzeugt von `karte-adressbuch@neander.timer` alle zwei Minuten aus
  `nodes.json`. Eigener Bestand in `/var/lib/karte/adressbuch/`: wen yanic
  vergisst, der bleibt mit altem `last_seen` und `online: false` stehen.

### Zeitreihen

`https://neander.map.freifunk.space/nf/prom/api/v1/...`, Prometheus-API von
VictoriaMetrics. Freigegeben sind nur `query`, `query_range`, `series`,
`labels`, `label/<name>/values`, `export`, `status/tsdb` und `federate`, alles
andere unter `/nf/prom/` gibt 403.

- Quelle: yanic schreibt über seinen Influx-Ausgang (`ZEITREIHE` in
  `sammler/yanic-conf.py`), nur die Community neander. Metriknamen sind
  `<measurement>_<feld>`, etwa `node_memory.available`, `node_time.up`,
  `node_load`, `link_tq`; Labels u.a. `nodeid`, `hostname`, `site`, `domain`,
  `model`, `firmware_release`, `db` (= Community).
- Beispiel: `curl -s 'https://neander.map.freifunk.space/nf/prom/api/v1/query' --data-urlencode 'query={__name__="node_memory.available",nodeid="bc7ec351c4a4"}'`
  (Metriknamen mit Punkt gehen nur über `__name__`).
- **Neanderfunk-Felder** aus `statistics.neanderfunk` (Paket
  neanderfunk-respondd) liest yanic erst durch den Commit "statistics.neanderfunk" im Fork
  Neanderfunk/yanic:

  | Metrik | Art | Labels zusätzlich |
  | --- | --- | --- |
  | `node_nf.refault_file` | Zähler seit Start, `rate()` | |
  | `node_nf.forks` | Zähler seit Start | |
  | `node_nf.zram.ram`, `.data`, `.size` | kB | |
  | `node_nf.ssid_changer.gateway_losses`, `.offline`, `.switches` | Zähler | |
  | `nf_ethernet_carrier` (0/1), `nf_ethernet_speed`, `nf_ethernet_possible` | Mbit/s, `possible` 0 = unbekannt | `port`, `duplex` |
  | `nf_temperature_celsius` | °C | `sensor` |
  | `nf_wireless_txpower`, `nf_wireless_channel`, `nf_wireless_mesh` (0/1) | Konfiguration | `radio`, `ssid`, `htmode`, `country` |

  Der Zähler `node_nf.ssid_changer.offline` beantwortet eine Frage, die sonst
  niemand beantworten kann: **wie oft war dieser Knoten weg, ohne neu zu
  starten?** Ein Knoten kann nicht melden, dass er offline ist, aber der
  Zähler steht danach höher da. Er steht deshalb im Knotenfenster der Karte
  (Diagramm "Ausfälle laut Knoten") und im Grafana-Dashboard. Springt er auf
  null, hat der Knoten neu gestartet, dann zählt `node_time.up`.

  Fehlende Werte werden nicht als 0 geschrieben: Alt-Firmware ohne das Paket
  und Knoten ohne Sensor tauchen einfach nicht auf. `system.mem_available`
  doppelt `node_memory.available` und bleibt weg. Alarmsignal am Port ist
  `possible > speed` (2,5G-Port, der nicht hochkam), nicht `possible` allein.
  Ein ganz toter Port meldet `possible` 0 und fällt durch diesen Vergleich,
  dafür `nf_ethernet_carrier == 0`. Portnamen sind nicht einheitlich: TR3000
  meldet `eth0`/`eth1`, andere `wan`/`lan1`. Einen Alarm also nicht auf
  `port="wan"` bauen, sondern über alle Ports oder über `model`
  (gemessen 22.09.2026 an 80af: `eth0` carrier 0, der tote RTL8221B).
- **Eine Reihe je Sache, nicht je Zustand.** yanic hängt Labels wie die
  Frequenz oder die Firmwareversion an jeden Punkt. Wechselt ein Knoten den
  Kanal, etwa nach einem Neustart, entsteht dadurch eine neue Zeitreihe mit
  eigener Farbe und eigenem Eintrag in der Legende; ein Gerät kam so an einem
  Tag auf 16 Reihen. Zwei Gegenmaßnahmen, beide nötig:
  - die Frequenzlabels wirft VictoriaMetrics beim Empfang weg
    (`relabel.yml`). Die Frequenz bleibt als Messwert
    `node_airtime11a.frequency` erhalten.
  - alle Abfragen fassen zusammen (`max by (band)`, `sum by (richtung)`, sonst
    `max(...)`). Das deckt auch ältere Daten und Firmwarewechsel ab, bei denen
    sich `firmware_release` ändert.
- **Namen von hinten kürzen, nicht von vorn.** Unsere Hostnamen unterscheiden
  sich am Ende (`wlf-uk-Schulstr7-AP01-c4a4`), der Anfang ist über ein ganzes
  Haus gleich. Grafana schneidet auf schmalen Anzeigen aber hinten ab.
  Gemessen: von links auf 16 Zeichen gekürzt sind 397 von 1076 Namen nicht
  mehr unterscheidbar, von rechts nur fünf. Wo Hostnamen in Legenden oder
  Tabellen stehen, erzeugt `kurzname()` deshalb ein Label `kurz` mit den
  letzten beiden Namensteilen und stellt es voran; der volle Name steht
  daneben.
- `owner` wird beim Empfang verworfen (`/etc/victoria-metrics/relabel.yml`),
  yanic kennt für diesen Ausgang kein `no_owner`.
- Aufbewahrung 180 Tage, Limits für Abfragen in
  `/etc/default/victoria-metrics`. VictoriaMetrics lauscht nur auf
  `127.0.0.1:8428`, die Paketvorgabe wäre `0.0.0.0` gewesen.
- Einrichtung: `sudo ./zeitreihe/einrichten.sh`. Das Skript richtet auch
  Grafana ein.

### Diagramme im Knotenfenster

meshviewer zeichnet sie seit 13.x selbst mit d3 als SVG, ohne iframe und ohne
gerendertes Bild. Upstream holt die Daten über die Grafana-API; unser Patch
(Fork [Neanderfunk/meshviewer](https://github.com/Neanderfunk/meshviewer), Zweig `neanderfunk`) ergänzt `datasourceType: prometheus-direct`,
das liest `query_range` direkt aus VictoriaMetrics. Dazu eine Leiste, mit der
sich der Zeitraum aller Diagramme gemeinsam umschalten lässt.

Konfiguriert wird beides in `web/konfig-erzeugen.py`: `DIAGRAMME`,
`ZEITRAEUME`, `ZEITREIHE_URL`. Zwei Eigenheiten der Abfragesprache, beide
gemessen:

- keine Backslash-Escapes in den Namensmustern, der Punkt steht für sich
- `rate()` wirft den Metriknamen weg, danach sind `rx` und `tx` nicht mehr
  unterscheidbar; `keep_metric_names` hält ihn fest (VictoriaMetrics)

### Kartenebenen

Drei zur Auswahl, CARTO ist die Vorgabe: CARTO hell, OpenStreetMap deutsch
(entsättigt) und **Luftbilder NRW**, die amtlichen Orthophotos, eingebunden
wie auf `map.eulenfunk.de`.

- Die Luftbilder kommen als **WMS**, nicht als Kachelsatz. meshviewer legt von
  sich aus nur Kachelebenen an; unser Fork erkennt eine
  WMS-Ebene daran, dass `layers` gesetzt ist.
- Den WMTS-Host des Landes kennt unser Kachel-Proxy nicht (gemessen: 404),
  den WMS-Host schon. Alles läuft weiter über `tiles.ffdus.de`, aus dem
  Browser geht keine Anfrage direkt zum Land.
- Die Luftbilder tragen bewusst **kein** `karte-dunkel`: ein umgedrehtes
  Luftbild ist unbrauchbar.

### Adresse in der Standortwahl

Die Standortwahl der Karte zeigt zum gewählten Punkt die Adresse. meshviewer
fragte dafür aus dem Browser jeder Besucherin direkt bei
`nominatim.openstreetmap.org`; seit 25.09.2026 geht das über
`/nf/ort/reverse` auf jeder Karte (`web/nginx-geo.conf`, Ort in
`konfig-erzeugen.py`). Weiter gehen nur Breite und Länge auf 5
Nachkommastellen und die Sprache, Cache 30 Tage in `/var/cache/nginx/karte-geo`,
höchstens eine Anfrage je Sekunde an Nominatim. Probe:
`curl -sI 'https://neander.map.freifunk.space/nf/ort/reverse?lat=51.2506&lon=6.9746'`
(zweimal: `X-Cache-Status: HIT`).

### Erstsichtung aus der alten Karte

Unsere Karte kennt einen Knoten erst, seit wir messen; im Knotenfenster stünde
sonst überall der 20.09.2026. `sammler/erstsichtung-uebernehmen.py` holt die
Erstsichtung aus der `nodes.json` von `map.eulenfunk.de`, derselben Community,
und trägt sie in den Zustand von yanic ein.

- Übernommen wird **nur, was älter ist**. Ein zweiter Lauf ändert nichts, und
  der Zustand wird nie jünger.
- Knoten, die nur die andere Karte kennt, werden **nicht** erfunden.
- yanic hält den Zustand im Speicher und schreibt ihn jede Minute, muss für
  den Lauf also stehen:

```bash
sudo systemctl stop yanic@neander
sudo /usr/local/sbin/karte-erstsichtung
sudo systemctl start yanic@neander
```

Lauf vom 24.09.2026: 1110 von 1110 Knoten bekamen ein älteres Datum, die
älteste Sichtung stammt vom 19.07.2020. Sicherung unter
`/var/lib/yanic/neander.json.vor-erstsichtung`.

**UniFi-APs (25.09.2026, einmalig):** Die Erstsichtung kommt aus dem
Controller, genauer aus der `_id` des Geräts: eine MongoDB-ObjectId, deren
erste 4 Bytes den Zeitpunkt tragen, zu dem der Controller das Gerät angelegt
hat. Wo es `adopted_at` gibt (230 von 615 APs, erst ab 2023), stimmt beides
sekundengenau überein; für die älteren fehlt `adopted_at`, die `_id` hat
alle. Übernommen mit demselben Skript, Quelle eine Datei mit `node_id` und
`firstseen`: 544 APs, älteste Sichtung 22.06.2017. Sicherung unter
`/root/neander.json.vor-ap-erstsichtung`. APs, die damals offline waren,
bekommen beim ersten Auftauchen das heutige Datum; bei Bedarf wiederholen
(ändert nur, was älter ist).

**map6 selbst (25.09.2026, einmalig):** Die Knoten `map-neanderfunk-<code>`
aus mesh-announce bekamen als Erstsichtung den ersten Tunnelaufbau je Domain
laut Journal (`karte-en: <code>: td-<code> an bat-<code>`): Neanderfunk
20.09.2026 abends, Essen 25.09.2026 14:21. Für Essen mit
`--zustand /var/lib/yanic/essen.json`. Sicherungen unter
`/root/*.vor-map6-erstsichtung`.

### Clients und dunkle Knoten

`sammler/clients-zaehlen.py`, alle fünf Minuten als `karte-clients@neander`.
Es zählt aus der Übersetzungstabelle von batman, die uns als Mesh-Mitglied
ohnehin zugestellt wird (48 Abfragen kosten zusammen 0,13 Sekunden):

| Metrik | Bedeutung |
| --- | --- |
| `tt_clients` | Stationen der Domain, ohne die Knoten selbst |
| `tt_eintraege` | alle Einträge der Tabelle |
| `tt_originatoren` | Originatoren im Mesh, **etwa doppelt so viele wie Knoten**, weil jede Mesh-Schnittstelle einzeln zählt |
| `tt_im_mesh` | verschiedene Knoten dahinter |
| `tt_dunkel` | Originatoren, die zu keinem bekannten Knoten gehören |
| `tt_ungeklaert` | davon die, die auch nicht in `bekannte-macs.conf` stehen |

Dazu die Liste `api/<community>/dunkel.json` mit den Merkmalen je MAC.

Zwei Zählweisen für Clients, und beide sind richtig: respondd summiert, was
die antwortenden Knoten melden (unteres Limit), die Tabelle kennt jede Station
der Domain, hält sie aber noch einige Minuten nach dem Abmelden (oberes Limit).
Gemessen am 23.09.2026: 2243 gegen 2945.

**Dunkle Knoten** sind batman-Knoten ohne antwortendes respondd. Wer
Originatoren mit Knoten vergleicht, erfindet sie: 1763 Originatoren sind 1070
Knoten. Richtig gezählt wird über die Mesh-MACs aus `nodes.json`.

Was so ein Knoten ist, sagt die Zahl nicht. Vier Möglichkeiten, nach adorfer:

1. **Gestorbenes respondd.** Der Knoten lebt, redet im Mesh mit, schafft aber
   nicht einmal mehr einen Neustart.
2. **Handgebautes.** Eigenbau mit Tunneldigger und batman, früher gern ein
   Raspberry Pi. Nie ein respondd drauf gewesen.
3. **Absichtlich stumm.** Wer nicht auf der Karte stehen will, schaltet es ab.
4. **Phantom.** Kein Gerät, sondern reflektierte OGMs, typisch bei
   asymmetrischem VLAN-Tagging im lokalen Mesh. Ein Konfigurationsfehler,
   der wie ein Knoten aussieht.

Unterscheiden lassen sie sich an dem, was sie tun:

| Merkmal | Bedeutung |
| --- | --- |
| kündigt MACs an (`ankuendigungen` > 0) | echter Teilnehmer, kein Phantom; ein Phantom trägt nichts in die Tabelle ein |
| kündigt `33:33:00:02:10:01` an | hat eine Firmware mit respondd, hört sogar auf dessen Gruppe: Fall 1 oder 3, nicht 2 |
| antwortet auf ping an Link-Local | IP-Stack lebt |
| in vielen Domains zugleich | keine Ortsinstallation, sondern etwas Betriebliches |
| taucht auf und verschwindet, ohne je etwas anzukündigen | Fall 4 |

Die Liste steht unter `https://neander.map.freifunk.space/nf/dunkel.json`, mit
erster und letzter Sichtung, den Domains, der Zahl der Ankündigungen und dem
nächsten Schritt dorthin. `aktuell` sagt, ob der Eintrag gerade sichtbar ist;
die meisten sind Kurzauftritte von wenigen Stunden. Nach einem Monat ohne
Sichtung fällt ein Eintrag heraus. Stand 23.09.2026 gibt es genau zwei:

- `0a:ed:b7:74:e0:a3` in `22_dusukn`, neun Ankündigungen, **kündigt die
  respondd-Gruppe an**, antwortet aber weder auf respondd noch auf ping. Ein
  Knoten mit passender Firmware, dessen respondd steht: Fall 1.
- `02:a5:a7:99:f0:fa` in **allen 48 Domains**: das ist **eulenmap1**, der
  Collector der alten Karte `map.eulenfunk.de` (adorfer 24.09.2026, per
  `ip a` auf der Maschine bestätigt). Er hängt wie wir in allen Domains,
  anders als wir aber mit **derselben MAC auf allen 49 bat-Schnittstellen**;
  unsere tragen je Domain eine eigene (`02:45:4e:*`).

Bekannte Maschinen dieser Art stehen in `sammler/bekannte-macs.conf`
(ausgespielt nach `/etc/karte-en/bekannte-macs.conf`). Sie zählen weiter als
dunkel, gelten aber nicht als ungeklärt: dafür gibt es `tt_ungeklaert`, und
nur darauf schlägt der Check an.

### Grafana

`https://neander.map.freifunk.space/grafana/`, verlinkt aus dem Knotenfenster
(`VERTIEFUNG` in `web/konfig-erzeugen.py`, Platzhalter `{NODE_ID}`). Dort
stehen Tagesbilanzen als Balken, freie Zeiträume und die Werte aus
`neanderfunk-respondd`.

- Lesend ohne Anmeldung, Anmeldemaske aus, keine Konten. Alles kommt aus
  Dateien: `zeitreihe/grafana/` (systemd-Drop-in, Datenquelle, Dashboard).
- Die Dashboards erzeugt `grafana/dashboard-erzeugen.py`, nicht die Oberfläche:
  Knoten (`nf-knoten`, Link im Knotenfenster), Domain (`nf-domain`),
  Supernode (`nf-supernode`) und Community (`nf-community`, Gesamtsicht,
  verlinkt oben im Reiter Statistik der Karte). In der Gesamtsicht zählt
  der Verkehr nur auf Seite der Gluon-Knoten; die Gateways stehen nur in der
  Gegenprobe, zusammengezählt wäre es verdoppelt.
  Änderungen in der Oberfläche sind nicht möglich und wären beim nächsten Lauf
  weg.
- nginx reicht `/grafana/` **ohne** Schrägstrich am Ende weiter
  (`proxy_pass http://127.0.0.1:3000;`). Mit Schrägstrich fiele das Präfix
  weg und Grafana leitete endlos auf sich selbst um.
- Fällt Grafana aus, bleibt die Karte samt ihren Diagrammen heil.
- Die `delete`-Abfrage, die yanic einmal am Tag an die Datenbank schickt,
  kennt VictoriaMetrics nicht; die Fehlermeldung im Log ist harmlos.

## Sicherheit

Geprüft am 24.09.2026, von außen über IPv6 und per `ss` auf der Maschine.

**Was von außen erreichbar ist:** nginx auf Port 80, sshd auf einem eigenen Port (nur
Schlüssel, kein root) und der Checkmk-Agent auf 6556. Der Agent gibt dort ohne
Registrierung seine volle Ausgabe im Klartext heraus, Prozessliste und
Unit-Liste eingeschlossen; das ist bewusst so (adorfer). VictoriaMetrics und
Grafana lauschen nur auf `127.0.0.1`, also auf keiner Netzadresse, weder v4
noch v6.

**Das Loch, das es gab:** Grafanas Datenquellen-Proxy reichte anonyme
Anfragen an die Datenbank durch, auch an deren Verwaltung. `delete_series`
antwortete darüber mit 204; jeder im Internet hätte die Zeitreihen löschen
können. Lokal lauschen allein schützt also nicht, sobald ein Dienst davor
Anfragen weiterreicht. Geschlossen in zwei Schichten:

- nginx sperrt `/grafana/api/datasources/proxy/` und die Liste der
  Datenquellen (403). Die Dashboards brauchen beides nicht.
- VictoriaMetrics verlangt für seine zehn Verwaltungsfunktionen einen
  Schlüssel (Drop-in `victoria-metrics-schluessel.conf`, Schlüssel nur auf der
  Maschine in `/etc/victoria-metrics/geheim.env`). Das greift auch auf dem Weg
  über Grafanas Ressourcen-Schnittstelle, die offen bleiben muss: dort
  antwortet die Datenbank jetzt mit 401.

Der Schlüssel steht in der Kommandozeile des Prozesses und ist damit für
lokale Benutzer lesbar. Gegen Angriffe von außen genügt das, gegen einen
kompromittierten lokalen Dienst nicht.

**Pfad-Traversal:** alle `alias`-Orte enden mit Schrägstrich, `/data../`,
`/nf../` und Verwandte fallen auf die Startseite zurück; `..` im Pfad und
kodierte Varianten beantwortet nginx mit 400. `/nf/prom/` lässt nur die
lesenden Pfade durch, alles andere gibt 403, auch mit `..` oder `//` davor.

**Versionsangabe:** map6 verrät seine nginx-Version nicht (`server_tokens off`
steht schon in der `nginx.conf` des Pakets). Die Angabe `nginx/1.26.3`, die man
von außen sieht, kommt vom Proxy auf twin2.

## Neustart der Maschine

Alles kommt von selbst hoch: Module über `modules-load.d`, acht Tunnel-Units
und yanic sind `enabled`. Der Zwischenstand in `/var/lib/yanic/state.json`
sorgt dafür, dass die Historie und die Offline-Knoten erhalten bleiben. Eine
Minute nach dem Start stehen wieder Daten.

## Aktualisieren

**Eigene Forks (seit 25.09.2026).** yanic, meshviewer und unifi_respondd kommen aus
unseren Forks in der Neanderfunk-Organisation, jeweils Zweig `neanderfunk`:
Upstream-Stand plus unsere Änderungen, **je Funktion ein Commit**, erklärt in
`NEANDERFUNK.md` im Fork.

| Fork | Upstream | Basis |
| --- | --- | --- |
| [Neanderfunk/meshviewer](https://github.com/Neanderfunk/meshviewer) | freifunk/meshviewer | `6c68e3d` (18.09.2026) |
| [Neanderfunk/unifi_respondd](https://github.com/Neanderfunk/unifi_respondd) | freifunkMUC/unifi_respondd | `6976651` (18.09.2026) |
| [Neanderfunk/yanic](https://github.com/Neanderfunk/yanic) | FreifunkBremen/yanic (Codeberg) | `v1.9.0` |

Bis dahin waren es Patchdateien in diesem Repo. adorfers Regel: kleine
Ergänzungen als Patch, sobald bestehende Logik umgebaut wird oder
Frontend-Code dazukommt, ein eigenes Repo. Beides war erreicht. Die Forks
behalten die Lizenz des Originals (AGPL-3.0 bzw. GPL-3.0); beim meshviewer
erfüllt der öffentliche Fork zugleich die AGPL-Pflicht, den Quelltext der
ausgelieferten Fassung zugänglich zu machen.

Upstream nachziehen: im Fork `git fetch upstream`, `neanderfunk` auf den
neuen Stand rebasen, Tests laufen lassen, pushen, dann hier
`sudo ./web/einrichten.sh` bzw. `sudo ./sammler/einrichten.sh`. yanic kam
als letzter dazu, mit den Umbauten für die Accesspoints (Clients der APs
beim Router abziehen, Links von beiden Seiten); vorher zwei Patchdateien in
`sammler/patches/`, jetzt die ersten beiden Commits im Fork.

**meshviewer** neu bauen, wenn es Neues gibt:

```bash
sudo ./web/einrichten.sh
```

Das holt den aktuellen `main`, baut und ersetzt den Build. Die neun
`config.json` werden dabei neu erzeugt, die Kartenausschnitte also an die
aktuellen Knotenkoordinaten angepasst.

**yanic** auf eine neue Version: `YANIC_TAG` in `sammler/einrichten.sh`
ändern, Skript erneut laufen lassen. Die Konfiguration wird neu erzeugt, also
vorher prüfen, ob die neue Version dieselben Felder erwartet.

**Tunneldigger** ist auf einen Commit festgenagelt (`TD_COMMIT`). Der Client
ändert sich selten; ein Wechsel unterbricht alle acht Tunnel für wenige
Sekunden.

**Debian** normal per `apt`. Ein Kernelwechsel bedeutet einen Neustart und
damit eine Lücke von etwa einer Minute in den Daten.

## Ressourcen

Im Leerlauf belegt die Installation rund 370 MB Arbeitsspeicher und etwa
4,3 GB Platte, davon der größte Teil Quellen und `node_modules`. Die Last
liegt unter 1. Der Spitzenbedarf entsteht nur beim meshviewer-Build.
