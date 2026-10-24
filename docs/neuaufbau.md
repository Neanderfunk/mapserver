# Neuaufbau im Notfall

Was es braucht, um die Karten-VM auf einer frischen Debian-13-VM wieder
aufzusetzen, etwa nach Verlust der Maschine. Grundlage für eine Ansible-Rolle
als Notfallweg; sie ruft die Einrichtungsskripte dieses Repos auf, statt sie
nachzubauen. Routinepflege bleibt bei den Skripten selbst
([einrichtung.md](einrichtung.md), [betrieb.md](betrieb.md)).

Stand 24.10.2026. Wo Zugangsdaten liegen, steht hier nur als Pfad; die Werte
liegen nicht in diesem Repo.

## Reihenfolge

### 0. Maschine

- Debian 13 (trixie) mit dem **Standard-Kernel** `linux-image-amd64`. Der
  Kernel der Cloud-Images (`linux-image-cloud-amd64`) hat batman-adv nicht;
  dann `linux-image-amd64` installieren, den Cloud-Kernel entfernen, neu
  starten. `tunnel/einrichten.sh` prüft das vorab und bricht sonst ab.
- 2 CPUs, gut 2 GB RAM (Spitze beim `npm install`),
  Platte mindestens 30 GB; heute 98 GB, davon 12 GB belegt, VictoriaMetrics
  wächst (Aufbewahrung 1300 Tage).
- Hostname `map.freifunk.space`. Die ändernden Betriebsbefehle in der
  Pflege prüfen ihn vorab (`[ "$(hostname)" = map.freifunk.space ]`).
- Netz nach `vm/interfaces` (statisch, kein DHCPv6-Client, siehe
  `vm/README.md`), dazu `vm/sysctl-neighbours.conf` nach
  `/etc/sysctl.d/90-karte-neighbours.conf`.
- Benutzer `ad-claude` mit sudo (Passwort) und SSH-Schlüssel; die
  Arbeitskopie liegt in dessen Home (`~ad-claude/mapserver`). SSH lauscht auf
  Port 62954.
- Pakete vorab: `git`, `sudo`, `curl`, `rsync`. Den Rest holen die Skripte.

### 1. Repo

```bash
git clone https://github.com/Neanderfunk/mapserver ~ad-claude/mapserver
```

Zweig `main`, neuester Stand. Auf map6 ist die Kopie kein git-Checkout,
sondern ein ausgepacktes `git archive` (so wird sie gepflegt); die Skripte
rufen git nur in ihren eigenen Bauverzeichnissen unter `/usr/local/src`
auf, nie in der Arbeitskopie. Klont die Rolle mit git und läuft git dort
als root, braucht es `git config --system safe.directory
/home/ad-claude/mapserver`, sonst meldet git "dubious ownership".

Die Skripte installieren aus dem Verzeichnis,
in dem sie liegen; deshalb immer aus dieser Kopie und nach jedem
Repo-Wechsel die Kopie aktualisieren (siehe betrieb.md, "Arbeitskopie auf
der VM zuerst").

### 2. Erhaltene Dateien zurückspielen, VOR den Skripten

Einige Dateien erzeugen die Skripte nur, wenn sie fehlen. Fehlen sie beim
Neuaufbau, entstehen neue Schlüssel oder Kennungen, und Gegenstellen, die die
alten kennen, lassen uns nicht mehr herein. Also erst zurückspielen, dann die
Skripte laufen lassen. Liste und Gründe: Abschnitt "Zugangs- und
Schlüsseldateien".

### 3. Einrichtungsskripte

Alle als root aus `~ad-claude/mapserver`, unbeaufsichtigt
(`DEBIAN_FRONTEND=noninteractive`, keine Rückfragen), jeweils mit
Exit-Code ungleich 0 bei Fehlern (`set -euo pipefail`). Reihenfolge:

| # | Aufruf | Voraussetzung | Ergebnis |
| --- | --- | --- | --- |
| 1 | `sudo ./tunnel/einrichten.sh` | erhaltene Kennung und fastd-Schlüssel liegen schon | je Domain `karte-en-tunnel@<code>`, Wächter-Timer |
| 2 | `sudo ./sammler/einrichten.sh` | Tunnel laufen (sonst wartet yanic beim Start bis zu 180 s) | je Community `yanic@<community>`; Adressbuch, Clientzählung, Verlauf |
| 2a | Standby-Communities wieder anhalten | erhaltene `standby.conf` | siehe unten |
| 3 | `sudo ./web/einrichten.sh` | Schritt 2 | meshviewer-Build, Gerätebilder, alle `config.json`, nginx |
| 4 | `sudo ./zeitreihe/einrichten.sh` | | VictoriaMetrics, Grafana (Paketquelle apt.grafana.com, Hauptversion per apt-Pin festgelegt) |
| 5 | `sudo ./sammler/controller-tunnel.sh` | erhaltene `wg-ctl.conf` liegt schon | nur nötig, um `wg-quick@wg-ctl` zu aktivieren; mit vorhandener Konfiguration gibt es keine neuen Peers aus |
| 6 | `sudo ./sammler/unifi-einrichten.sh` | erhaltene Controller-Zugänge liegen schon, Schritt 5 | `unifi-respondd`, Zuordnung AP zu Router |
| 7 | `sudo ./sammler/mesh-announce-einrichten.sh` | Schritt 1 | `mesh-announce` |
| 8 | `sudo ./service/einrichten.sh` | Schritt 2 | `karte-service` (Service-Menü) |
| 9 | `sudo ./web/einrichten.sh` | Schritt 8 | noch einmal: nginx mit der Anmeldung für das Service-Menü |
| 10 | Checkmk-Agent installieren, dann `sudo ./checkmk/installieren.sh` | Agent-Paket vom Checkmk-Server | Local Checks |

Hinweise:

- Schritte 1 und 2 schalten Tunnel und Collector **aller** Communities aus
  `domains.conf` ein, auch der ruhenden. Danach je Community aus
  `/etc/karte-en/standby.conf` (heute EN) die Dienste wieder anhalten, wie in
  betrieb.md, "Eine Community in den Standby nehmen", Schritt 2:
  `karte-en-tunnel@<code>` je Domain, `yanic@<community>`, bei EN auch
  `karte-ziele.timer`, jeweils `systemctl disable --now`.
- `controller-tunnel.sh` erwartet Argumente (Name, Tunneladresse, Ziele) und
  ist für das Anlegen eines Peers gedacht. Im Neuaufbau mit zurückgespielter
  `/etc/wireguard/wg-ctl.conf` genügt `systemctl enable --now
  wg-quick@wg-ctl`; die Routen zu Zielen hinter einer Gegenstelle stehen in
  der Konfiguration.
- `sammler/unifi-einrichten.sh` bricht ab, solange `/etc/karte-en/sitecodes.conf`
  fehlt (legt Schritt 2 an).
- Schritt 2 baut yanic aus dem Fork und lässt dessen Tests laufen; Go kommt
  aus Debian. Schritt 3 braucht Netz zu GitHub und zur npm-Registry.

### 4. Daten zurückspielen

Bei gestoppten Diensten (`victoria-metrics`, `yanic@*`, `karte-service`,
`grafana-server`), Besitzer wie unten, danach starten. Liste: Abschnitt
"Daten".

## Zugangs- und Schlüsseldateien

| Pfad auf der VM | Besitzer, Rechte | Zweck | Neu erzeugen? |
| --- | --- | --- | --- |
| `/etc/karte-en/kennung` | root, 0644 | Kennungsserie: viertes Byte unserer MACs und Teil des Namens am Broker | **erhalten**: neue Serie heißt neue MACs und neuer Name in jedem fremden Mesh |
| `/etc/karte-en/fastd/<community>.secret` und `.pub` | root, 0600 / 0644 | fastd-Schlüssel je Community (Essen, Hildesheim) | **erhalten**: die Gegenstelle hat den öffentlichen Schlüssel freigeschaltet; ein neuer braucht eine neue Freischaltung |
| `/etc/karte-en/standby.conf` | root, 0644 | Communities im Standby (Betriebszustand) | erhalten, sonst gilt die Vorgabe aus dem Repo |
| `/etc/wireguard/wg-ctl.conf` | root, 0600 | WireGuard zu UniFi-Controllern hinter NAT: eigener Schlüssel, Peers, Ziele | **erhalten**: jede Gegenstelle kennt unseren öffentlichen Schlüssel und hat ihre eigene Konfiguration |
| `/etc/unifi_respondd/zugang` | root, 0600 | Zugang zum Haupt-Controller (Benutzer, Passwort, URL) | erhalten; neu nur mit neuem Konto am Controller |
| `/etc/unifi_respondd/controller/<name>` | root, 0600 | je weiterer Controller ein Zugang | erhalten, wie oben |
| `/etc/victoria-metrics/geheim.env` | root, 0600 | Schlüssel für die Verwaltungsfunktionen von VictoriaMetrics | darf neu entstehen (erzeugt `zeitreihe/einrichten.sh`); niemand außerhalb kennt ihn |
| `/etc/ssh/ssh_host_*_key` | root, 0600 | Hostschlüssel | besser erhalten, sonst warnt jeder SSH-Client |
| Grafana-Admin | in `/var/lib/grafana/grafana.db` | Anmeldung an Grafana | kommt mit der Datenbank (siehe Daten); ohne sie neu setzen |
| Checkmk-Agent | `/var/lib/cmk-agent/` | Agent im Legacy-Pull-Modus, keine Registrierung | neu installieren genügt |

Abgeleitet und nicht zu sichern: `/etc/unifi_respondd/unifi_respondd.yaml`
(aus den Zugängen erzeugt), alle `config.json`, die nginx-Site und
`/etc/yanic-*.conf`.

## Daten

| Pfad | Größe (24.10.2026) | Inhalt | Bei Verlust |
| --- | --- | --- | --- |
| `/var/lib/victoria-metrics` | 3.1 GB | Zeitreihen, Aufbewahrung 1300 Tage, mit der Vorgeschichte aus der alten Karte ab 09.07.2026 | Diagramme und Grafana beginnen neu; die Vorgeschichte ließe sich nur erneut übernehmen, solange die alte Karte läuft |
| `/var/lib/karte/verlauf.csv` | 34 MB | Verlauf der Knotenzahlen | Verlauf beginnt neu |
| `/var/lib/karte/service/` | klein | Service-Menü: Overrides (Koordinaten, Namen), Aliase, Protokoll, Löschaufträge | **Handarbeit geht verloren**: alle Korrekturen aus dem Service-Menü |
| `/var/lib/karte/adressbuch/` | klein | Adressbuch (`/nf/targets.json`), letzte bekannte Adressen | füllt sich neu, Offline-Knoten fehlen bis zum nächsten Kontakt |
| `/var/lib/karte/unifi-zuordnung.json` | klein | Zuordnung AP zu Router | erzeugt der Timer neu |
| `/var/lib/yanic/` | 11 MB | yanic-Zustand: erste und letzte Sichtung je Knoten | alle Knoten gelten als neu ("Neue Knoten"), Offline-Knoten verschwinden, bis sie wieder auftauchen |
| `/var/lib/grafana/grafana.db` | 2 MB | Benutzer, Admin-Passwort, Einstellungen; die Dashboards erzeugt das Skript | Benutzer neu anlegen |

Der Rest von `/var/lib/grafana` (rund 960 MB) sind Plugins aus dem Paket.

Gesichert wird heute nur die ganze VM über das Backup des Hypervisors; eine
eigene Sicherung dieser Pfade gibt es nicht. Für VictoriaMetrics ginge ein
Snapshot über die Verwaltungsfunktion (Schlüssel in `geheim.env`).

## Abhängigkeiten außerhalb der VM

| Was | Wo | Bei neuer IP oder neuer Maschine |
| --- | --- | --- |
| HTTPS und öffentliche Namen | Proxy davor (siehe einrichtung.md, "Proxy und Zertifikat"); die VM spricht nur HTTP auf Port 80 | Ziel des Proxys auf die neue Adresse |
| DNS `map6.freifunk.space` und die Kartennamen | Zone `freifunk.space` | AAAA anpassen |
| Tunnel zu den Communities | Broker und fastd-Server, nur ausgehend | nichts, solange Kennung und fastd-Schlüssel erhalten sind |
| UniFi-Controller hinter NAT | Gegenstellen bauen WireGuard zu uns auf (Port 51820, IPv6 direkt, IPv4 per Portweiterleitung am Proxy) | Endpoint in jeder Gegenstelle bzw. die Weiterleitung anpassen |
| UniFi-Haupt-Controller | direkt per HTTPS erreichbar | nichts |
| Checkmk | Server holt per Legacy-Pull (Port 6556) | Host-Adresse im Checkmk anpassen; Freigabe vor der VM |
| Service-Menü | Authentik (Forward auth, Name `neander.map.freifunk.space`) | nichts, solange der Name bleibt |
| Ortsnamen in der Standortwahl | `/nf/ort/` reicht an einen Nominatim-Dienst weiter | nichts |
| Filter vor der VM | Auf der VM selbst gibt es keine Firewall-Regeln, gefiltert wird davor | Freigaben für 80, 62954, 51820, 6556 (nur Checkmk) auf die neue Adresse |

## Prüfungen am Ende

```bash
systemctl --failed
systemctl list-units 'karte-en-tunnel@*' 'yanic@*' --no-legend | grep -vc running
for b in /sys/class/net/bat-*; do n=${b##*/}; echo "$n $(batctl meshif $n n -H | wc -l)"; done
sudo /usr/local/sbin/karte-en-waechter && journalctl -t karte-en --since -5min | grep Waechter
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: neander.map.freifunk.space' http://[::1]/data/meshviewer.json
curl -sf http://127.0.0.1:8428/health
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: neander.map.freifunk.space' http://[::1]/grafana/api/health
wg show wg-ctl latest-handshakes
systemctl is-active unifi-respondd mesh-announce karte-service nginx
```

- Keine fehlgeschlagenen Units; alle Tunnel und Collector laufen.
- Jede Domain außer denen in `tunnel/ruhend.conf` hat mindestens einen
  batman-Nachbarn.
- Der Wächter meldet nichts.
- Von außen: `https://neander.map.freifunk.space/` zeigt Knoten online, der
  Zeitstempel in `data/meshviewer.json` ist jünger als zwei Minuten; dasselbe
  für die übrigen Communities.
- Grafana und `/nf/prom/` antworten, die Diagramme im Knotenfenster zeigen
  die alten Daten (sonst fehlt die Rücksicherung).
- Jeder Controller-Peer hat einen Handshake jünger als drei Minuten; die
  UniFi-APs stehen auf der Karte.
- Checkmk sieht den Host und die Local Checks.
