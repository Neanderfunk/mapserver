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

## Überwachung

Die Checks liegen in `~/projekte/freifunk/checkmk` und werden von dort
ausgespielt (`sudo ./installieren.sh 'mapserver*'`). Auf der VM:

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
| `mapserver-Web` | eine der neun Karten oder ihre Daten nicht mit 200 antworten |

Die aussagekräftigste Größe je Domain sind die **Originatoren**, nicht die
Knotenzahl: sie fällt in dem Moment, in dem der Tunnel abreißt, während die
Knoten noch fünf Minuten lang als online in der Datei stehen.

`mapserver-Abschottung` ist kein Betriebswert, sondern eine Zusicherung. Wenn
dort etwas anderes als OK steht, läuft möglicherweise eigener Verkehr durch
ein fremdes Netz, siehe [hintergrund.md](hintergrund.md).

Nicht überwacht wird von hier aus der Weg von außen, also Proxy und
Zertifikat auf twin2. Das gehört in einen Check dort.

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
