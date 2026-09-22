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
/usr/local/bin/yanic                    Sammler
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

# 4. Sammler
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
Sammler hängt an einer Schnittstelle, die es nicht mehr gibt:

```bash
ss -uanp | grep yanic | grep '%if[0-9]'
```

Jede Zeile ist eine stumme Domain. Der Wächter startet den Sammler dann
innerhalb von fünf Minuten neu; von Hand `systemctl restart yanic@<community>`.
Hintergrund in `docs/kartenausfall-diagnose.md` der Router-Werkstatt.

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

## Eine Community in den Standby nehmen

Wenn eine Community wieder selbst eine Karte betreibt, brauchen wir ihre
Domains nicht mehr mitzumessen. Der Aufbau bleibt stehen, er hört nur auf zu
arbeiten, und ein Auskommentieren macht ihn wieder lebendig.

Die Domaintabelle ist dabei der einzige Schalter: alles andere wird daraus
erzeugt. Reihenfolge, damit nichts hängen bleibt:

```bash
# 1. Dienste anhalten, solange sie noch in der Tabelle stehen
for c in $(awk '!/^#/ && NF && $1 == "en" { print $2 }' /etc/karte-en/domains.conf); do
    sudo systemctl disable --now "karte-en-tunnel@$c"
done
sudo systemctl disable --now yanic@en

# 2. Zeilen der Community in tunnel/domains.conf auskommentieren, ausspielen
sudo install -m 0644 domains.conf /etc/karte-en/domains.conf

# 3. Erzeugtes neu bauen: Vhosts und Sammlerkonfiguration verlieren sie damit
sudo /usr/local/sbin/karte-en-konfig
sudo nginx -t && sudo systemctl reload nginx
```

Vorher zu klären, weil es an einer anderen Stelle weh tut: **wer unsere Karte
als Datenquelle liest**, verliert sie. Bei mitfunken steht sie in der
`initiativen.yaml` unter `daten:`; dort gehört dann die eigene Karte der
Community unter `quellen.karte` hinein, und zwar **bevor** wir hier abschalten,
sonst steht die Community dort für einen Lauf ohne Daten da.

Die Zeitreihe in `/var/lib/karte/verlauf.csv` bleibt erhalten und ist der
Grund, warum sich das Abschalten lohnt statt des Loeschens: sie dokumentiert,
was das Netz getan hat, solange wir hingesehen haben.

## Überwachung

Die Checks liegen in `checkmk/` und werden von dort ausgespielt
(`sudo ./installieren.sh 'mapserver*'`). Auf der VM:

```
/usr/lib/check_mk_agent/local/mapserver         jeder Agentenlauf
/usr/lib/check_mk_agent/local/300/mapserver-web alle fünf Minuten
```

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
  neanderfunk-respondd) liest yanic erst durch `patches/yanic-neanderfunk.patch`:

  | Metrik | Art | Labels zusätzlich |
  | --- | --- | --- |
  | `node_nf.refault_file` | Zähler seit Start, `rate()` | |
  | `node_nf.forks` | Zähler seit Start | |
  | `node_nf.zram.ram`, `.data`, `.size` | kB | |
  | `node_nf.ssid_changer.gateway_losses`, `.offline`, `.switches` | Zähler | |
  | `nf_ethernet_carrier` (0/1), `nf_ethernet_speed`, `nf_ethernet_possible` | Mbit/s, `possible` 0 = unbekannt | `port`, `duplex` |
  | `nf_temperature_celsius` | °C | `sensor` |
  | `nf_wireless_txpower`, `nf_wireless_channel`, `nf_wireless_mesh` (0/1) | Konfiguration | `radio`, `ssid`, `htmode`, `country` |

  Fehlende Werte werden nicht als 0 geschrieben: Alt-Firmware ohne das Paket
  und Knoten ohne Sensor tauchen einfach nicht auf. `system.mem_available`
  doppelt `node_memory.available` und bleibt weg. Alarmsignal am Port ist
  `possible > speed` (2,5G-Port, der nicht hochkam), nicht `possible` allein.
  Ein ganz toter Port meldet `possible` 0 und fällt durch diesen Vergleich,
  dafür `nf_ethernet_carrier == 0`. Portnamen sind nicht einheitlich: TR3000
  meldet `eth0`/`eth1`, andere `wan`/`lan1`. Einen Alarm also nicht auf
  `port="wan"` bauen, sondern über alle Ports oder über `model`
  (gemessen 22.09.2026 an 80af: `eth0` carrier 0, der tote RTL8221B).
- `owner` wird beim Empfang verworfen (`/etc/victoria-metrics/relabel.yml`),
  yanic kennt für diesen Ausgang kein `no_owner`.
- Aufbewahrung 180 Tage, Grenzen für Abfragen in
  `/etc/default/victoria-metrics`. VictoriaMetrics lauscht nur auf
  `127.0.0.1:8428`, die Paketvorgabe wäre `0.0.0.0` gewesen.
- Einrichtung: `sudo ./zeitreihe/einrichten.sh`.
- Die `delete`-Abfrage, die yanic einmal am Tag an die Datenbank schickt,
  kennt VictoriaMetrics nicht; die Fehlermeldung im Log ist harmlos.

## Neustart der Maschine

Alles kommt von selbst hoch: Module über `modules-load.d`, acht Tunnel-Units
und yanic sind `enabled`. Der Zwischenstand in `/var/lib/yanic/state.json`
sorgt dafür, dass die Historie und die Offline-Knoten erhalten bleiben. Eine
Minute nach dem Start stehen wieder Daten.

## Aktualisieren

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
